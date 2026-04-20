"""Portal API routes — /portal/*."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4
from typing import Any

import requests as http_requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

try:
    import psycopg2.extras
except ImportError:
    pass

from data_platform.chat_backend.infra.postgres import (
    _fetch_optional_one,
    _postgres_conn,
    _run_pg_dict_query,
)
from data_platform.chat_backend.infra.http import _success_response
from data_platform.chat_backend.infra.settings import (
    IDEMPOTENCY_KEY_HEADER_NAME,
    INTERNAL_SERVICE_NAME_HEADER_NAME,
    INTERNAL_SERVICE_SECRET,
    INTERNAL_SERVICE_SECRET_HEADER_NAME,
    PORTAL_MOCK_PAYMENT_ENABLED,
    _portal_email_verification_gate_enabled,
    _generate_id,
)
from data_platform.chat_backend.domains.portal.service import (
    _backend_base_url,
    _require_portal_user,
    _portal_base_url,
)
from data_platform.chat_backend.domains.admin.service import _build_user_account_overview
from data_platform.chat_backend.domains.billing.service import (
    _build_billing_catalog,
    _build_payment_order_snapshot,
    _ensure_user_credit_account_state,
    _fetch_billing_package,
    _grant_referral_invited_reward_if_needed,
)
from data_platform.chat_backend.domains.identity.service import (
    _bind_user_referral,
    _confirm_email_verification,
    _ensure_user_record,
    _fetch_user,
    _request_email_verification,
)
from data_platform.chat_backend.domains.notifications.service import (
    _list_notifications_for_user,
    _set_notification_read_state,
)
from data_platform.chat_backend.domains.payments.service import _fetch_payment_order_for_user
from data_platform.chat_backend.domains.site_config import _get_contact_config

from data_platform.chat_backend.api.models import (
    BindReferralCodeRequest,
    ConfirmEmailVerificationRequest,
    CreatePaymentOrderRequest,
    UpdateNotificationReadStateRequest,
)
from data_platform.api.chat_backend_portal_html import render_portal_html
from data_platform.api.chat_backend_portal_public_html import (
    render_portal_checkout_html,
    render_portal_guide_html,
    render_portal_products_html,
)

router = APIRouter()
_WECHAT_QR_IMAGE_PATH = Path(__file__).resolve().parents[3] / "微信二维码.jpg"


_PORTAL_PROVIDER_LABELS = {
    "alipay": "支付宝",
    "wechat": "微信支付",
    "manual": "线下/手工",
}

_PORTAL_LEDGER_SOURCE_LABELS = {
    "subscription": "月包积分",
    "recharge": "充值包积分",
    "other": "其他赠送积分",
}


def _normalize_portal_ledger_source(source: Any) -> str:
    normalized = str(source or "").strip().lower()
    if normalized in _PORTAL_LEDGER_SOURCE_LABELS:
        return normalized
    return "other"


def _summarize_portal_ledger_sources(row: dict[str, Any]) -> list[dict[str, Any]]:
    meta_json = dict(row.get("meta_json") or {})
    allocations = list(meta_json.get("balance_source_allocations") or [])
    totals: dict[str, int] = {}
    for allocation in allocations:
        source = _normalize_portal_ledger_source((allocation or {}).get("source"))
        points = max(0, int((allocation or {}).get("points") or 0))
        if points <= 0:
            continue
        totals[source] = totals.get(source, 0) + points

    if not totals and str(row.get("entry_type") or "").strip().lower() == "subscription_expire":
        expired_points = max(0, int(meta_json.get("expired_points") or abs(int(row.get("points_delta") or 0))))
        if expired_points > 0:
            totals["subscription"] = expired_points

    ordered_sources = ("subscription", "recharge", "other")
    return [
        {
            "source": source,
            "label": _PORTAL_LEDGER_SOURCE_LABELS[source],
            "points": totals[source],
        }
        for source in ordered_sources
        if totals.get(source, 0) > 0
    ]


def _build_portal_ledger_row(row: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(row)
    source_summary = _summarize_portal_ledger_sources(enriched)
    enriched["source_summary"] = source_summary
    enriched["source_summary_text"] = "；".join(
        f"{item['label']} {int(item.get('points') or 0)} 积分"
        for item in source_summary
    )
    return enriched


def _resolve_openwebui_session_user(request: Request) -> tuple[str, str, str] | None:
    cookie = (request.headers.get("cookie") or "").strip()
    if not cookie:
        return None

    token_value = ""
    for part in cookie.split(";"):
        k_v = part.strip().split("=", 1)
        if len(k_v) == 2 and k_v[0].strip() == "token":
            token_value = k_v[1].strip()
            break
    if not token_value:
        return None

    owui_base = _portal_base_url()
    try:
        resp = http_requests.get(
            "%s/api/v1/auths/" % owui_base,
            headers={"Authorization": "Bearer %s" % token_value},
            timeout=5,
        )
    except Exception:
        return None

    if resp.status_code != 200:
        return None

    try:
        user_data = resp.json()
    except Exception:
        return None

    user_id = str(user_data.get("id") or "").strip()
    if not user_id:
        return None
    email = str(user_data.get("email") or "").strip()
    name = str(user_data.get("name") or "").strip()
    return user_id, email, name


def _portal_user_requires_email_verification(conn, user_id: str) -> bool:
    if not _portal_email_verification_gate_enabled():
        return False
    user = _fetch_user(conn, user_id)
    return user.email_verified_at is None


def _enforce_verified_portal_user(conn, user_id: str) -> None:
    if _portal_user_requires_email_verification(conn, user_id):
        raise HTTPException(status_code=403, detail="email verification required before using portal features")


def _normalize_portal_provider(provider: str) -> str:
    normalized = str(provider or "").strip().lower() or "alipay"
    if normalized == "wxpay":
        normalized = "wechat"
    if normalized not in _PORTAL_PROVIDER_LABELS:
        raise HTTPException(status_code=400, detail=f"unsupported payment provider: {provider}")
    return normalized


def _build_portal_payment_response(conn, order_row: dict[str, Any]) -> dict[str, Any]:
    package = _fetch_billing_package(conn, order_row["package_code"])
    return {
        "order": order_row,
        "package": package,
        "pricing_snapshot": order_row.get("promotion_snapshot_json") or {},
        "mock_payment_enabled": PORTAL_MOCK_PAYMENT_ENABLED,
    }


# ---------------------------------------------------------------------------
# Session validation (called by nginx auth_request)
# ---------------------------------------------------------------------------

@router.get("/_internal/portal/validate-session")
def portal_validate_session(request: Request) -> Response:
    """Nginx auth_request subrequest: validate OpenWebUI cookie and return user identity headers."""
    resolved_user = _resolve_openwebui_session_user(request)
    if resolved_user is None:
        return Response(status_code=401)
    user_id, email, name = resolved_user
    try:
        with _postgres_conn() as conn:
            _ensure_user_record(conn, user_id=user_id, email=email, display_name=name)
    except Exception:
        pass

    return Response(
        status_code=200,
        headers={
            "X-Portal-User-Id": user_id,
            "X-Portal-User-Email": email,
            "X-Portal-User-Name": name,
        },
    )


@router.get("/_internal/openwebui/verified-user-check")
def openwebui_verified_user_check(request: Request) -> Response:
    """Nginx auth_request for Open WebUI root traffic.

    - anonymous user: 401, let nginx pass through to Open WebUI login page
    - logged-in but unverified user: 403, let nginx redirect to /portal/account
    - logged-in and verified user: 200
    """
    resolved_user = _resolve_openwebui_session_user(request)
    if resolved_user is None:
        return Response(status_code=401)

    user_id, email, name = resolved_user
    try:
        with _postgres_conn() as conn:
            _ensure_user_record(conn, user_id=user_id, email=email, display_name=name)
            if _portal_user_requires_email_verification(conn, user_id):
                return Response(status_code=403)
    except Exception:
        return Response(status_code=401)
    return Response(status_code=200)


@router.get("/portal")
def portal_page() -> HTMLResponse:
    return HTMLResponse(render_portal_html(), headers={"Cache-Control": "no-store"})


@router.get("/portal/account")
def portal_account_page() -> HTMLResponse:
    return HTMLResponse(render_portal_html(), headers={"Cache-Control": "no-store"})


@router.get("/portal/products")
def portal_products_page() -> HTMLResponse:
    return HTMLResponse(render_portal_products_html(), headers={"Cache-Control": "no-store"})


@router.get("/portal/guide")
def portal_guide_page() -> HTMLResponse:
    return HTMLResponse(render_portal_guide_html(), headers={"Cache-Control": "no-store"})


@router.get("/portal/api/public/site-contact-config")
def portal_public_site_contact_config() -> dict[str, Any]:
    with _postgres_conn() as conn:
        contact = _get_contact_config(conn)
    return _success_response(
        "/portal/api/public/site-contact-config",
        {"contact": contact},
        "portal site contact config loaded",
    )


@router.get("/portal/contact/wechat-qr")
def portal_wechat_qr_image() -> FileResponse:
    if not _WECHAT_QR_IMAGE_PATH.exists():
        raise HTTPException(status_code=404, detail="wechat qr image not found")
    return FileResponse(
        path=str(_WECHAT_QR_IMAGE_PATH),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/portal/checkout")
def portal_checkout_page(request: Request) -> HTMLResponse:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        if _portal_user_requires_email_verification(conn, user_id):
            redirect_target = "/portal/account"
            portal_token = (request.query_params.get("t") or "").strip()
            if portal_token:
                redirect_target += f"?t={portal_token}"
            return RedirectResponse(url=redirect_target, status_code=302)
    package_code = (request.query_params.get("package_code") or "").strip()
    selected_package: dict[str, Any] | None = None
    pricing_preview: dict[str, Any] | None = None
    if package_code:
        with _postgres_conn() as conn:
            selected_package = _fetch_billing_package(conn, package_code)
            pricing_preview = _build_payment_order_snapshot(
                conn,
                user_id=user_id,
                package=selected_package,
                order_id=f"preview:{package_code}",
            )
    return HTMLResponse(
        render_portal_checkout_html(
            selected_package=selected_package,
            pricing_preview=pricing_preview,
            mock_payment_enabled=PORTAL_MOCK_PAYMENT_ENABLED,
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/portal/api/account")
def portal_get_account(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        overview = _build_user_account_overview(conn, user_id, ledger_limit=50, usage_limit=50)
    return _success_response("/portal/api/account", overview, "account loaded")


@router.post("/portal/api/account/email-verification/request")
def portal_request_email_verification(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        result = _request_email_verification(conn, user_id)
    return _success_response(
        "/portal/api/account/email-verification/request",
        result,
        "email verification code sent",
    )


@router.post("/portal/api/account/email-verification/confirm")
def portal_confirm_email_verification(request: Request, payload: ConfirmEmailVerificationRequest) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        verified_user = _confirm_email_verification(conn, user_id, payload.code)
        _ensure_user_credit_account_state(conn, verified_user)
        overview = _build_user_account_overview(conn, user_id, ledger_limit=50, usage_limit=50)
    return _success_response(
        "/portal/api/account/email-verification/confirm",
        overview,
        "email verified",
    )


@router.post("/portal/api/account/referral/bind")
def portal_bind_referral_code(request: Request, payload: BindReferralCodeRequest) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        _bind_user_referral(conn, user_id, payload.invite_code)
        _grant_referral_invited_reward_if_needed(conn, user_id)
        verified_user = _fetch_user(conn, user_id)
        _ensure_user_credit_account_state(conn, verified_user)
        overview = _build_user_account_overview(conn, user_id, ledger_limit=50, usage_limit=50)
    return _success_response(
        "/portal/api/account/referral/bind",
        overview,
        "invite code bound",
    )


@router.post("/portal/api/notifications/read-state")
def portal_update_notification_read_state(
    request: Request,
    payload: UpdateNotificationReadStateRequest,
) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        updated_rows = _set_notification_read_state(
            conn,
            user_id,
            read=payload.read,
            notification_ids=payload.notification_ids,
            category=payload.category,
        )
        notifications = _list_notifications_for_user(conn, user_id, limit=100)
    return _success_response(
        "/portal/api/notifications/read-state",
        {"updated_count": len(updated_rows), "notifications": notifications},
        "notification read state updated",
    )


@router.get("/portal/api/billing/catalog")
def portal_get_billing_catalog(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        catalog = _build_billing_catalog(conn, user_id)
    return _success_response(
        "/portal/api/billing/catalog",
        {"user_id": user_id, "catalog": catalog},
        "billing catalog loaded",
    )


@router.get("/portal/api/ledger")
def portal_get_ledger(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    page = max(1, int(request.query_params.get("page", "1")))
    page_size = min(100, max(1, int(request.query_params.get("page_size", "30"))))
    offset = (page - 1) * page_size
    ledger_filter = (request.query_params.get("filter") or "").strip().lower()

    filter_clause = ""
    if ledger_filter == "topup":
        filter_clause = " AND points_delta > 0 AND entry_type <> 'refund'"
    elif ledger_filter == "spend":
        filter_clause = " AND points_delta < 0"

    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        base_query = (
            "SELECT entry_id, entry_type, event_type, units, points_delta, balance_after_points,"
            " reference_id, description, meta_json, created_at"
            " FROM app.credit_ledger_entry"
            " WHERE user_id = %s" + filter_clause +
            " ORDER BY created_at DESC, entry_id DESC"
            " LIMIT %s OFFSET %s"
        )
        rows = [
            _build_portal_ledger_row(row)
            for row in _run_pg_dict_query(conn, base_query, [user_id, page_size, offset])
        ]
        count_query = "SELECT COUNT(*) AS cnt FROM app.credit_ledger_entry WHERE user_id = %s" + filter_clause
        total_row = _fetch_optional_one(conn, count_query, [user_id])
    total = int((total_row or {}).get("cnt", 0))
    return _success_response(
        "/portal/api/ledger",
        {"rows": rows, "page": page, "page_size": page_size, "total": total},
        "ledger loaded",
    )


@router.get("/portal/api/usage-daily")
def portal_get_usage_daily(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    days = min(90, max(1, int(request.query_params.get("days", "30"))))
    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        rows = _run_pg_dict_query(
            conn,
            """
            SELECT DATE(created_at AT TIME ZONE 'Asia/Shanghai') AS day,
                   event_type,
                   COUNT(*) AS event_count,
                   COALESCE(SUM(units), 0) AS total_units
            FROM app.usage_event
            WHERE user_id = %s
              AND created_at >= NOW() - make_interval(days => %s)
            GROUP BY day, event_type
            ORDER BY day DESC, event_type
            """,
            [user_id, days],
        )
    return _success_response("/portal/api/usage-daily", {"rows": rows, "days": days}, "daily usage loaded")


@router.post("/portal/api/payments/orders")
def portal_create_payment_order(request: Request, payload: CreatePaymentOrderRequest) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    provider = _normalize_portal_provider(payload.provider)
    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        package = _fetch_billing_package(conn, payload.package_code)
        order_id = _generate_id("order")
        pricing_snapshot = _build_payment_order_snapshot(
            conn,
            user_id=user_id,
            package=package,
            order_id=order_id,
        )
        pricing = pricing_snapshot["pricing"]
        order_row = _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.payment_order (
                order_id, user_id, package_code, product_type, provider, list_amount_cents,
                discount_amount_cents, amount_cents, points_amount, status,
                promotion_snapshot_json, callback_payload_json, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s, NOW(), NOW())
            RETURNING order_id, user_id, package_code, product_type, provider, list_amount_cents,
                      discount_amount_cents, amount_cents, points_amount, status,
                      provider_order_id, provider_trade_no, promotion_snapshot_json,
                      callback_payload_json, paid_at, created_at, updated_at
            """,
            [
                order_id,
                user_id,
                package["package_code"],
                package["product_type"],
                provider,
                pricing["list_amount_cents"],
                pricing["discount_amount_cents"],
                pricing["payable_amount_cents"],
                package["points_amount"],
                psycopg2.extras.Json(pricing_snapshot),
                psycopg2.extras.Json(
                    {
                        "package_name": package["package_name"],
                        "package_meta": package.get("meta_json") or {},
                        "pricing_snapshot": pricing_snapshot,
                        "provider_label": _PORTAL_PROVIDER_LABELS.get(provider) or provider,
                        "created_via": "/portal/api/payments/orders",
                    }
                ),
            ],
        )[0]
    return _success_response(
        "/portal/api/payments/orders",
        {
            "order": order_row,
            "package": package,
            "pricing_snapshot": pricing_snapshot,
            "mock_payment_enabled": PORTAL_MOCK_PAYMENT_ENABLED,
        },
        "portal payment order created",
    )


@router.get("/portal/api/payments/orders/{order_id}")
def portal_get_payment_order(order_id: str, request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        order_row = _fetch_payment_order_for_user(conn, order_id, user_id)
        payload = _build_portal_payment_response(conn, order_row)
    return _success_response(
        f"/portal/api/payments/orders/{order_id}",
        payload,
        "portal payment order loaded",
    )


@router.post("/portal/api/payments/orders/{order_id}/simulate-paid")
def portal_simulate_payment_paid(order_id: str, request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    if not PORTAL_MOCK_PAYMENT_ENABLED:
        raise HTTPException(status_code=403, detail="portal mock payment is disabled")
    if not INTERNAL_SERVICE_SECRET:
        raise HTTPException(status_code=503, detail="internal service secret is not configured")

    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        order_row = _fetch_payment_order_for_user(conn, order_id, user_id)
        if str(order_row.get("status") or "").lower() == "paid":
            payload = _build_portal_payment_response(conn, order_row)
            return _success_response(
                f"/portal/api/payments/orders/{order_id}/simulate-paid",
                payload,
                "order already paid",
            )
        provider = _normalize_portal_provider(str(order_row.get("provider") or "alipay"))
        callback_url = _backend_base_url() + f"/internal/payments/provider-callback/{provider}"

    callback_payload = {
        "order_id": order_id,
        "provider_order_id": f"mock-order-{order_id}",
        "provider_trade_no": f"mock-trade-{uuid4().hex[:24]}",
        "paid_amount_cents": int(order_row.get("amount_cents") or 0),
        "meta": {
            "source": "portal_mock_payment",
            "triggered_via": f"/portal/api/payments/orders/{order_id}/simulate-paid",
        },
    }
    headers = {
        INTERNAL_SERVICE_SECRET_HEADER_NAME: INTERNAL_SERVICE_SECRET,
        INTERNAL_SERVICE_NAME_HEADER_NAME: "portal-mock-payment",
        IDEMPOTENCY_KEY_HEADER_NAME: f"portal-mock:{order_id}:{uuid4().hex}",
    }
    try:
        response = http_requests.post(callback_url, headers=headers, json=callback_payload, timeout=12)
    except Exception as exc:  # pragma: no cover - network failure only
        raise HTTPException(status_code=502, detail=f"mock payment callback failed: {exc}") from exc

    try:
        response_json = response.json()
    except Exception:
        response_json = {"message": response.text.strip() or response.reason}
    if response.status_code != 200 or response_json.get("success") is not True:
        raise HTTPException(
            status_code=502,
            detail=response_json.get("detail") or response_json.get("message") or "mock payment callback failed",
        )

    with _postgres_conn() as conn:
        updated_order = _fetch_payment_order_for_user(conn, order_id, user_id)
        payload = _build_portal_payment_response(conn, updated_order)
    return _success_response(
        f"/portal/api/payments/orders/{order_id}/simulate-paid",
        payload,
        "portal mock payment applied",
    )
