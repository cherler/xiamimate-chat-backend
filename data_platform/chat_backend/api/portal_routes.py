"""Portal API routes — /portal/*."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
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
    DEVICE_SESSION_ELEVATION_TTL_SECONDS,
    IDEMPOTENCY_KEY_HEADER_NAME,
    INTERNAL_SERVICE_NAME_HEADER_NAME,
    INTERNAL_SERVICE_SECRET,
    INTERNAL_SERVICE_SECRET_HEADER_NAME,
    PORTAL_MOCK_PAYMENT_ENABLED,
    _portal_email_verification_gate_enabled,
    _generate_id,
    _utc_now,
)
from data_platform.chat_backend.domains.portal.service import (
    _backend_base_url,
    _portal_internal_base_url,
    _portal_public_base_url,
    _require_portal_user,
)
from data_platform.chat_backend.domains.admin.service import _build_user_account_overview
from data_platform.chat_backend.domains.billing.service import (
    _build_billing_catalog,
    _build_payment_order_snapshot,
    _ensure_user_credit_account_state,
    _fetch_billing_package,
    _fetch_subscriptions_for_user,
    _grant_referral_invited_reward_if_needed,
    _redeem_code,
    _resolve_referral_invited_reward_points,
    _resolve_signup_gift_points,
)
from data_platform.chat_backend.domains.identity.service import (
    _bind_user_referral,
    _confirm_email_verification,
    _confirm_email_verification_link as _confirm_email_verification_link_token,
    _confirm_password_reset,
    _confirm_security_verification,
    _ensure_user_record,
    _fetch_user_by_invite_code,
    _fetch_user,
    _request_password_reset,
    _request_email_verification,
    _request_security_verification,
)
from data_platform.chat_backend.domains.device_sessions.service import (
    _bootstrap_device_session,
    _clear_device_session_cookie,
    _current_device_session_or_raise,
    _evaluate_device_session_request,
    _elevate_device_session,
    _require_elevated_device_session,
    _revoke_device_session,
    _revoke_other_device_sessions,
    _serialize_device_session,
    _set_device_session_cookie,
)
from data_platform.chat_backend.domains.notifications.service import (
    _list_notifications_for_user,
    _set_notification_read_state,
)
from data_platform.chat_backend.domains.payments.service import _fetch_payment_order_for_user
from data_platform.chat_backend.domains.site_config import (
    _get_contact_config,
    _get_email_verification_security_config,
)

from data_platform.chat_backend.api.models import (
    AdminCreateRedeemCodeBatchRequest,
    BindReferralCodeRequest,
    ConfirmPasswordResetRequest,
    ConfirmEmailVerificationRequest,
    ConfirmSecurityVerificationRequest,
    CreatePaymentOrderRequest,
    RedeemCodeRedeemRequest,
    RequestPasswordResetRequest,
    UpdateNotificationReadStateRequest,
)
from data_platform.api.chat_backend_portal_html import render_portal_html
from data_platform.api.chat_backend_portal_public_html import (
    render_portal_checkout_html,
    render_portal_guide_html,
    render_portal_email_verification_result_html,
    render_portal_invite_html,
    render_portal_password_reset_html,
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

_PORTAL_LEDGER_FILTER_CLAUSES = {
    "consume": " AND entry_type = 'consume'",
    "refund": " AND entry_type = 'refund'",
    "credit": " AND points_delta > 0 AND entry_type NOT IN ('refund', 'daily_quota_reset')",
    "daily_reset": " AND entry_type = 'daily_quota_reset'",
}

_EMAIL_VERIFICATION_IP_GUARD_LOCK = threading.Lock()
_EMAIL_VERIFICATION_IP_GUARD_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def _mask_email_for_display(email: str) -> str:
    normalized = str(email or "").strip()
    if "@" not in normalized:
        return normalized or "-"
    local, domain = normalized.split("@", 1)
    if len(local) <= 2:
        masked_local = local[:1] + "*"
    else:
        masked_local = local[:2] + "***"
    return f"{masked_local}@{domain}"


def _normalize_portal_ledger_source(source: Any) -> str:
    normalized = str(source or "").strip().lower()
    if normalized in _PORTAL_LEDGER_SOURCE_LABELS:
        return normalized
    return "other"


def _summarize_portal_ledger_sources(row: dict[str, Any]) -> list[dict[str, Any]]:
    meta_json = dict(row.get("meta_json") or {})
    entry_type = str(row.get("entry_type") or "").strip().lower()
    allocations = list(meta_json.get("balance_source_allocations") or [])
    if entry_type == "refund" and not allocations:
        allocations = list(meta_json.get("refund_allocations") or [])
    totals: dict[str, int] = {}
    for allocation in allocations:
        source = _normalize_portal_ledger_source((allocation or {}).get("source"))
        points = max(0, int((allocation or {}).get("points") or 0))
        if points <= 0:
            continue
        totals[source] = totals.get(source, 0) + points

    if not totals and entry_type == "subscription_expire":
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


def _extract_openwebui_access_token(request: Request) -> str:
    auth_header = (request.headers.get("authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return str(request.cookies.get("token") or "").strip()


def _resolve_openwebui_session_user(request: Request) -> tuple[str, str, str] | None:
    token_value = _extract_openwebui_access_token(request)
    if not token_value:
        return None

    owui_base = _portal_internal_base_url()
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


def _apply_security_verification_summary(overview: dict[str, Any]) -> dict[str, Any]:
        current_session = overview.get("current_device_session") or {}
        overview["security_verification"] = {
        "required_actions": ["redeem_code", "revoke_device_session"],
                "current_device_verified": bool(current_session.get("is_elevated")),
                "current_device_verified_until": current_session.get("elevated_until"),
                "current_device_last_verified_at": current_session.get("last_verified_at"),
                "verification_ttl_seconds": DEVICE_SESSION_ELEVATION_TTL_SECONDS,
        }
        return overview


def _find_active_monthly_subscription(subscriptions: list[dict[str, Any]]) -> dict[str, Any] | None:
    now = _utc_now()
    active_rows: list[dict[str, Any]] = []
    for row in subscriptions or []:
        if str(row.get("status") or "").strip().lower() != "active":
            continue
        period_end = row.get("current_period_end")
        if period_end is not None and period_end <= now:
            continue
        active_rows.append(row)
    if not active_rows:
        return None
    active_rows.sort(
        key=lambda row: (
            row.get("current_period_end") is None,
            row.get("current_period_end") or row.get("updated_at") or row.get("created_at"),
        ),
        reverse=True,
    )
    return active_rows[0]


def _build_monthly_package_purchase_guard(conn, user_id: str, package: dict[str, Any]) -> dict[str, Any] | None:
    if str(package.get("product_type") or "").strip().lower() != "monthly_subscription":
        return None
    active_subscription = _find_active_monthly_subscription(_fetch_subscriptions_for_user(conn, user_id))
    if not active_subscription:
        return None
    active_package_code = str(active_subscription.get("package_code") or "").strip()
    target_package_code = str(package.get("package_code") or "").strip()
    is_current_package = active_package_code == target_package_code
    return {
        "blocked": True,
        "active_subscription": active_subscription,
        "button_label": "当前订阅" if is_current_package else "套餐切换待上线",
        "message": (
            "当前套餐已经生效，本阶段不支持重复购买同一月包；当前按单月购买，到期后如需继续使用，再手动续购。"
            if is_current_package
            else "当前账号已有生效中的月包；套餐升降级切换后续再开放，本阶段先不支持新的月包下单。"
        ),
        "reason_code": "current_subscription_active" if is_current_package else "subscription_switch_not_supported",
        "is_current_package": is_current_package,
    }


def _render_portal_session_expired_html() -> str:
        home_url = _portal_public_base_url()
        return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>会话已失效</title>
    <style>
        body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: linear-gradient(135deg, #f4efe6, #dfe8ec); color: #16323a; }}
        .shell {{ min-height: 100vh; display: grid; place-items: center; padding: 24px; }}
        .card {{ width: min(560px, 100%); background: rgba(255,255,255,0.92); border-radius: 24px; padding: 32px; box-shadow: 0 24px 60px rgba(22, 50, 58, 0.12); }}
        h1 {{ margin: 0 0 12px; font-size: 2rem; }}
        p {{ margin: 0 0 14px; line-height: 1.7; }}
        .actions {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px; }}
        a {{ text-decoration: none; }}
        .primary {{ background: #114b5f; color: #fff; padding: 12px 18px; border-radius: 999px; }}
        .secondary {{ background: #fff; color: #114b5f; padding: 12px 18px; border-radius: 999px; border: 1px solid rgba(17, 75, 95, 0.18); }}
    </style>
</head>
<body>
    <div class="shell">
        <div class="card">
            <h1>当前浏览器会话已失效</h1>
            <p>这通常发生在密码刚被重置，或者你主动在另一台设备上执行了安全操作。为了保护账户安全，当前浏览器需要重新登录。</p>
            <p>页面加载时会自动清理本地登录态；如果仍然看到旧状态，直接点下面按钮重新回到首页登录即可。</p>
            <div class="actions">
                <a class="primary" href="{home_url}/">回到首页重新登录</a>
                <a class="secondary" href="{home_url}/portal/guide">查看使用指南</a>
            </div>
        </div>
    </div>
    <script>
        try {{ localStorage.removeItem('token'); }} catch (error) {{}}
        ['token', 'oui-session', 'oauth_id_token', 'xm_device_session'].forEach(function(name) {{
            document.cookie = name + '=; Max-Age=0; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Lax';
        }});
        fetch('/api/v1/auths/signout', {{ method: 'GET', credentials: 'same-origin', cache: 'no-store' }}).catch(function() {{ return null; }});
    </script>
</body>
</html>
"""


def _request_client_ip(request: Request) -> str:
    x_real_ip = (request.headers.get("x-real-ip") or "").strip()
    if x_real_ip:
        return x_real_ip
    forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if request.client and request.client.host:
        return str(request.client.host).strip()
    return "unknown"


def _build_portal_guard_response(user_id: str, email: str, name: str) -> Response:
    return Response(
        status_code=200,
        headers={
            "X-Portal-User-Id": user_id,
            "X-Portal-User-Email": email,
            "X-Portal-User-Name": name,
        },
    )


def _build_portal_guard_rate_limited_response(retry_after_seconds: int) -> Response:
    return Response(
        status_code=403,
        headers={
            "X-Portal-Guard-Result": "rate_limited",
            "X-Portal-Guard-Retry-After": str(max(1, int(retry_after_seconds))),
        },
    )


def _enforce_email_verification_ip_guard(conn, request: Request, action: str) -> Response | None:
    limits = _get_email_verification_security_config(conn)
    if action == "request":
        window_seconds = int(limits.get("request_ip_window_seconds") or 0)
        max_attempts = int(limits.get("request_ip_max_attempts") or 0)
    else:
        window_seconds = int(limits.get("confirm_ip_window_seconds") or 0)
        max_attempts = int(limits.get("confirm_ip_max_attempts") or 0)
    if window_seconds <= 0 or max_attempts <= 0:
        return None

    client_ip = _request_client_ip(request)
    bucket_key = f"{action}:{client_ip}"
    now = time.monotonic()
    with _EMAIL_VERIFICATION_IP_GUARD_LOCK:
        bucket = _EMAIL_VERIFICATION_IP_GUARD_BUCKETS[bucket_key]
        while bucket and bucket[0] <= now - window_seconds:
            bucket.popleft()
        if len(bucket) >= max_attempts:
            retry_after = int(max(1, window_seconds - (now - bucket[0]))) if bucket else window_seconds
            return _build_portal_guard_rate_limited_response(retry_after)
        bucket.append(now)
    return None


def _portal_email_verification_guard(request: Request, action: str) -> Response:
    resolved_user = _resolve_openwebui_session_user(request)
    if resolved_user is None:
        return Response(status_code=401)

    user_id, email, name = resolved_user
    try:
        with _postgres_conn() as conn:
            _ensure_user_record(conn, user_id=user_id, email=email, display_name=name)
            guard_response = _enforce_email_verification_ip_guard(conn, request, action)
            if guard_response is not None:
                return guard_response
    except Exception:
        return Response(status_code=500)
    return _build_portal_guard_response(user_id, email, name)


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
            device_session_state = _evaluate_device_session_request(conn, user_id, request, touch=True)
            if device_session_state["status"] == "invalid":
                return Response(status_code=409)
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


@router.get("/_internal/portal/email-verification/request-guard")
def portal_email_verification_request_guard(request: Request) -> Response:
    return _portal_email_verification_guard(request, "request")


@router.get("/_internal/portal/email-verification/confirm-guard")
def portal_email_verification_confirm_guard(request: Request) -> Response:
    return _portal_email_verification_guard(request, "confirm")


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
            device_session_state = _evaluate_device_session_request(conn, user_id, request, touch=True)
            if device_session_state["status"] == "invalid":
                return Response(status_code=409)
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


@router.get("/portal/invite")
def portal_invite_page() -> HTMLResponse:
    return HTMLResponse(render_portal_invite_html(), headers={"Cache-Control": "no-store"})


@router.get("/portal/recover-password", response_model=None)
def portal_password_reset_page(request: Request) -> Response:
    if _resolve_openwebui_session_user(request) is not None:
        redirect_target = "/portal/account"
        portal_token = (request.query_params.get("t") or "").strip()
        if portal_token:
            redirect_target += f"?t={portal_token}"
        return RedirectResponse(redirect_target, status_code=303, headers={"Cache-Control": "no-store"})
    return HTMLResponse(render_portal_password_reset_html(), headers={"Cache-Control": "no-store"})


@router.get("/portal/session-expired")
def portal_session_expired_page() -> HTMLResponse:
    return HTMLResponse(_render_portal_session_expired_html(), headers={"Cache-Control": "no-store"})


@router.post("/_xm/session/bootstrap")
def bootstrap_openwebui_device_session(request: Request, response: Response) -> dict[str, Any]:
    resolved_user = _resolve_openwebui_session_user(request)
    if resolved_user is None:
        raise HTTPException(status_code=401, detail="not authenticated")

    user_id, email, display_name = resolved_user
    with _postgres_conn() as conn:
        _ensure_user_record(conn, user_id=user_id, email=email, display_name=display_name)
        session_row, raw_token, created = _bootstrap_device_session(conn, user_id, request)
        if session_row is None or raw_token is None:
            raise HTTPException(status_code=409, detail="current device session expired")
        _set_device_session_cookie(response, raw_token)
    return _success_response(
        "/_xm/session/bootstrap",
        {
            "created": created,
            "session": _serialize_device_session(session_row, current_session_id=session_row.get("session_id")),
        },
        "device session ready",
    )


@router.get("/portal/api/public/site-contact-config")
def portal_public_site_contact_config() -> dict[str, Any]:
    with _postgres_conn() as conn:
        contact = _get_contact_config(conn)
    return _success_response(
        "/portal/api/public/site-contact-config",
        {"contact": contact},
        "portal site contact config loaded",
    )


@router.get("/portal/api/public/referral/preview")
def portal_public_referral_preview(invite_code: str = "") -> dict[str, Any]:
    normalized_invite_code = (invite_code or "").strip().upper()
    if not normalized_invite_code:
        raise HTTPException(status_code=400, detail="missing invite code")

    with _postgres_conn() as conn:
        inviter = _fetch_user_by_invite_code(conn, normalized_invite_code)
        signup_reward_points, _ = _resolve_signup_gift_points(conn)
        bind_reward_points, _ = _resolve_referral_invited_reward_points(conn)

    if inviter is None:
        raise HTTPException(status_code=404, detail="invite code not found")

    return _success_response(
        "/portal/api/public/referral/preview",
        {
            "invite_code": inviter.invite_code,
            "inviter_user_id": inviter.user_id,
            "inviter_display_name": inviter.display_name,
            "inviter_email_masked": _mask_email_for_display(inviter.email),
            "signup_reward_points": signup_reward_points,
            "bind_reward_points": bind_reward_points,
        },
        "invite code preview loaded",
    )


@router.post("/portal/api/public/password-reset/request")
def portal_request_password_reset(request: Request, payload: RequestPasswordResetRequest) -> dict[str, Any]:
    with _postgres_conn() as conn:
        rate_limited = _enforce_email_verification_ip_guard(conn, request, "request")
        if rate_limited is not None:
            retry_after = int(rate_limited.headers.get("X-Portal-Guard-Retry-After") or 1)
            raise HTTPException(status_code=429, detail=f"请求过于频繁，请在 {retry_after} 秒后重试")
        result = _request_password_reset(conn, payload.email)
    return _success_response(
        "/portal/api/public/password-reset/request",
        result,
        "password reset request accepted",
    )


@router.post("/portal/api/public/password-reset/confirm")
def portal_confirm_password_reset(
    request: Request,
    payload: ConfirmPasswordResetRequest,
) -> dict[str, Any]:
    with _postgres_conn() as conn:
        rate_limited = _enforce_email_verification_ip_guard(conn, request, "confirm")
        if rate_limited is not None:
            retry_after = int(rate_limited.headers.get("X-Portal-Guard-Retry-After") or 1)
            raise HTTPException(status_code=429, detail=f"请求过于频繁，请在 {retry_after} 秒后重试")
        result = _confirm_password_reset(conn, payload.email, payload.code, payload.new_password)
    return _success_response(
        "/portal/api/public/password-reset/confirm",
        result,
        "password reset completed",
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
    subscription_purchase_guard: dict[str, Any] | None = None
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
            subscription_purchase_guard = _build_monthly_package_purchase_guard(conn, user_id, selected_package)
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
            subscription_purchase_guard=subscription_purchase_guard,
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/portal/api/account")
def portal_get_account(request: Request, response: Response) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        session_row, raw_token, _created = _bootstrap_device_session(conn, user_id, request)
        if session_row is None or raw_token is None:
            raise HTTPException(status_code=409, detail="current device session expired")
        _set_device_session_cookie(response, raw_token)
        overview = _build_user_account_overview(
            conn,
            user_id,
            current_device_session_id=str(session_row.get("session_id") or "") or None,
            ledger_limit=50,
            usage_limit=50,
        )
        overview = _apply_security_verification_summary(overview)
    return _success_response("/portal/api/account", overview, "account loaded")


@router.post("/portal/api/account/security-verification/request")
def portal_request_security_verification(request: Request, response: Response) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        session_row, raw_token, _created = _bootstrap_device_session(conn, user_id, request)
        if session_row is None or raw_token is None:
            raise HTTPException(status_code=409, detail="current device session expired")
        _set_device_session_cookie(response, raw_token)
        result = _request_security_verification(conn, user_id)
    return _success_response(
        "/portal/api/account/security-verification/request",
        result,
        "security verification code sent",
    )


@router.post("/portal/api/account/security-verification/confirm")
def portal_confirm_security_verification(
    request: Request,
    response: Response,
    payload: ConfirmSecurityVerificationRequest,
) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        session_row = _current_device_session_or_raise(conn, user_id, request)
        _confirm_security_verification(conn, user_id, payload.code)
        elevated_session = _elevate_device_session(conn, str(session_row["session_id"]))
        session_check = _evaluate_device_session_request(conn, user_id, request, touch=False)
        raw_token = session_check.get("raw_token")
        if raw_token:
            _set_device_session_cookie(response, raw_token)
        overview = _build_user_account_overview(
            conn,
            user_id,
            current_device_session_id=str(elevated_session.get("session_id") or "") or None,
            ledger_limit=50,
            usage_limit=50,
        )
        overview = _apply_security_verification_summary(overview)
    return _success_response(
        "/portal/api/account/security-verification/confirm",
        overview,
        "security verification confirmed",
    )


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
        current_session = _current_device_session_or_raise(conn, user_id, request)
        verified_user = _confirm_email_verification(conn, user_id, payload.code)
        _ensure_user_credit_account_state(conn, verified_user)
        overview = _build_user_account_overview(
            conn,
            user_id,
            current_device_session_id=str(current_session.get("session_id") or "") or None,
            ledger_limit=50,
            usage_limit=50,
        )
        overview = _apply_security_verification_summary(overview)
    return _success_response(
        "/portal/api/account/email-verification/confirm",
        overview,
        "email verified",
    )


@router.get("/portal/email-verification/confirm", response_model=None)
def portal_confirm_email_verification_link(challenge_id: str = "", token: str = "") -> HTMLResponse:
    try:
        with _postgres_conn() as conn:
            verified_user = _confirm_email_verification_link_token(conn, challenge_id, token)
            _ensure_user_credit_account_state(conn, verified_user)
        html = render_portal_email_verification_result_html(
            success=True,
            title="邮箱验证成功",
            message="你的注册邮箱已完成验证，新用户权益会按账户规则自动结算。",
            email=verified_user.email,
        )
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})
    except HTTPException as exc:
        html = render_portal_email_verification_result_html(
            success=False,
            title="邮箱验证未完成",
            message=str(exc.detail),
        )
        status_code = exc.status_code if 400 <= exc.status_code < 500 else 400
        return HTMLResponse(html, status_code=status_code, headers={"Cache-Control": "no-store"})


@router.post("/portal/api/account/referral/bind")
def portal_bind_referral_code(request: Request, payload: BindReferralCodeRequest) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        current_session = _current_device_session_or_raise(conn, user_id, request)
        _bind_user_referral(conn, user_id, payload.invite_code)
        _grant_referral_invited_reward_if_needed(conn, user_id)
        verified_user = _fetch_user(conn, user_id)
        _ensure_user_credit_account_state(conn, verified_user)
        overview = _build_user_account_overview(
            conn,
            user_id,
            current_device_session_id=str(current_session.get("session_id") or "") or None,
            ledger_limit=50,
            usage_limit=50,
        )
        overview = _apply_security_verification_summary(overview)
    return _success_response(
        "/portal/api/account/referral/bind",
        overview,
        "invite code bound",
    )


@router.post("/portal/api/account/sessions/revoke-others")
def portal_revoke_other_sessions(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        current_session = _require_elevated_device_session(conn, user_id, request)
        revoked_count = _revoke_other_device_sessions(
            conn,
            user_id,
            str(current_session["session_id"]),
            "self_service_revoke_others",
        )
        overview = _build_user_account_overview(
            conn,
            user_id,
            current_device_session_id=str(current_session.get("session_id") or "") or None,
            ledger_limit=50,
            usage_limit=50,
        )
        overview["session_action"] = {"revoked_other_device_count": revoked_count}
        overview = _apply_security_verification_summary(overview)
    return _success_response(
        "/portal/api/account/sessions/revoke-others",
        overview,
        "other device sessions revoked",
    )


@router.post("/portal/api/account/sessions/{session_id}/revoke")
def portal_revoke_device_session(session_id: str, request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        raise HTTPException(status_code=400, detail="device session id is required")
    with _postgres_conn() as conn:
        current_session = _require_elevated_device_session(conn, user_id, request)
        current_session_id = str(current_session.get("session_id") or "")
        if normalized_session_id == current_session_id:
            raise HTTPException(status_code=400, detail="current device cannot be revoked from this action")
        revoked_session = _revoke_device_session(
            conn,
            user_id,
            normalized_session_id,
            "self_service_revoke_device",
            current_session_id=current_session_id or None,
        )
        if revoked_session is None:
            raise HTTPException(status_code=404, detail="device session not found or already revoked")
        overview = _build_user_account_overview(
            conn,
            user_id,
            current_device_session_id=current_session_id or None,
            ledger_limit=50,
            usage_limit=50,
        )
        overview["session_action"] = {
            "action": "revoke_device_session",
            "revoked_session_id": normalized_session_id,
            "revoked_device_label": revoked_session.get("device_label") or "设备",
            "revoked_session_count": int(revoked_session.get("revoked_session_count") or 1),
        }
        overview = _apply_security_verification_summary(overview)
    return _success_response(
        f"/portal/api/account/sessions/{normalized_session_id}/revoke",
        overview,
        "device session revoked",
    )


@router.post("/portal/api/redeem-codes/redeem")
def portal_redeem_code(request: Request, payload: RedeemCodeRedeemRequest) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        current_session = _require_elevated_device_session(conn, user_id, request)
        redeem_result = _redeem_code(conn, user_id=user_id, redeem_code=payload.code)
        overview = _build_user_account_overview(
            conn,
            user_id,
            current_device_session_id=str(current_session.get("session_id") or "") or None,
            ledger_limit=50,
            usage_limit=50,
        )
        overview["redeem_result"] = redeem_result
        overview = _apply_security_verification_summary(overview)
    return _success_response(
        "/portal/api/redeem-codes/redeem",
        overview,
        "redeem code applied",
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
        filter_clause = _PORTAL_LEDGER_FILTER_CLAUSES["credit"]
    elif ledger_filter == "spend":
        filter_clause = " AND points_delta < 0"
    elif ledger_filter in _PORTAL_LEDGER_FILTER_CLAUSES:
        filter_clause = _PORTAL_LEDGER_FILTER_CLAUSES[ledger_filter]
    elif ledger_filter == "other":
        filter_clause = (
            " AND NOT ("
            "entry_type = 'consume'"
            " OR entry_type = 'refund'"
            " OR entry_type = 'daily_quota_reset'"
            " OR (points_delta > 0 AND entry_type NOT IN ('refund', 'daily_quota_reset'))"
            ")"
        )

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
        purchase_guard = _build_monthly_package_purchase_guard(conn, user_id, package)
        if purchase_guard:
            raise HTTPException(status_code=409, detail=str(purchase_guard.get("message") or "current subscription blocks monthly purchase"))
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
