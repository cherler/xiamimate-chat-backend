"""Internal API routes — /internal/*."""
from __future__ import annotations

from typing import Any

import requests as http_requests
from fastapi import APIRouter, HTTPException, Request

try:
    import psycopg2.extras
except ImportError:
    pass

from data_platform.chat_backend.infra.settings import (
    POINTS_PRICE_VERSION,
    IDEMPOTENCY_KEY_HEADER_NAME,
    INTERNAL_SERVICE_NAME_HEADER_NAME,
    INTERNAL_SERVICE_SECRET,
    INTERNAL_SERVICE_SECRET_HEADER_NAME,
    TERMINAL_RUN_STATUSES,
    USER_ID_HEADER_NAME,
    WORKFLOW_BUNDLED_NON_BILLABLE_EVENT_TYPES,
    _generate_id,
    _utc_now,
)
from data_platform.chat_backend.infra.postgres import (
    _fetch_optional_one,
    _postgres_conn,
    _run_pg_dict_query,
)
from data_platform.chat_backend.infra.http import (
    _begin_idempotent_request,
    _build_request_hash,
    _complete_idempotent_request,
    _require_idempotency_key,
    _require_internal_service,
    _success_response,
)
from data_platform.chat_backend.domains.identity.service import (
    _ensure_user_record,
    _fetch_user,
)
from data_platform.chat_backend.domains.api_keys.service import (
    _build_public_api_key_payload,
    _ensure_user_api_key,
    _resolve_user_api_key,
    _touch_user_api_key,
)
from data_platform.chat_backend.domains.billing.service import (
    _adjust_daily_credit_quota_consumed,
    _apply_order_promotions_after_payment,
    _apply_user_plan_tier_from_package,
    _apply_guest_daily_quota_if_needed,
    _build_credit_balance_breakdown,
    _calculate_points_for_event,
    _create_ledger_entry,
    _ensure_user_credit_account_state,
    _fetch_billing_package,
    _fetch_subscription,
    _get_credit_account,
    _get_point_cost_by_event,
    _grant_points_with_ledger,
    _grant_subscription_period,
    _is_guest_daily_quota_user,
    _normalize_period_window,
    _preview_credit_consumption_allocations,
    _record_usage_event,
    _resolve_refund_source_allocations,
)
from data_platform.chat_backend.domains.payments.service import (
    _fetch_latest_payment_session,
    _fetch_payment_order,
    _insert_payment_callback_event,
    _update_payment_session_status,
)
from data_platform.chat_backend.domains.payments.wechat_pay import (
    extract_wechat_trade_payload,
    verify_and_decrypt_wechat_notify,
)
from data_platform.chat_backend.domains.portal.service import (
    _backend_base_url,
    _generate_portal_token,
    _portal_public_base_url,
)
from data_platform.chat_backend.api.models import (
    ChargePointsRequest,
    DifyRunCallbackRequest,
    GrantPointsRequest,
    GrantSubscriptionRequest,
    IdentityExchangeRequest,
    PaymentProviderCallbackRequest,
    RefundPointsRequest,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Portal token creation
# ---------------------------------------------------------------------------

@router.post("/internal/portal/create-token")
def create_portal_token(request: Request) -> dict[str, Any]:
    _require_internal_service(request, "/internal/portal/create-token")
    user_id = (request.headers.get(USER_ID_HEADER_NAME) or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="missing X-User-Id header")
    with _postgres_conn() as conn:
        _fetch_user(conn, user_id)
    from data_platform.chat_backend.infra.settings import PORTAL_TOKEN_TTL_SECONDS
    token = _generate_portal_token(user_id)
    portal_url = f"{_portal_public_base_url()}/portal?t={token}"
    return _success_response(
        "/internal/portal/create-token",
        {"token": token, "portal_url": portal_url, "ttl_seconds": PORTAL_TOKEN_TTL_SECONDS},
        "portal token created",
    )


# ---------------------------------------------------------------------------
# Internal identity exchange (used by Open WebUI / Pipelines bridge)
# ---------------------------------------------------------------------------

@router.post("/internal/identity/exchange-webui-user")
def internal_exchange_webui_user(request: Request, payload: IdentityExchangeRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    with _postgres_conn() as conn:
        user = _ensure_user_record(
            conn,
            user_id=payload.user_id,
            email=payload.email,
            display_name=payload.display_name,
        )
        user_api_key = _ensure_user_api_key(conn, user)
        credit_account = _ensure_user_credit_account_state(conn, user)
    return _success_response(
        "/internal/identity/exchange-webui-user",
        {
            "user": user.__dict__,
            "api_key": user_api_key.__dict__,
            "points_account": credit_account.__dict__,
            "pricing_version": POINTS_PRICE_VERSION,
            "point_cost_by_event": _get_point_cost_by_event(),
        },
        "webui user exchanged",
    )


# ---------------------------------------------------------------------------
# Admin grant-points (internal)
# ---------------------------------------------------------------------------

@router.post("/internal/admin/grant-points")
def admin_grant_points(request: Request, payload: GrantPointsRequest) -> dict[str, Any]:
    scope = request.url.path
    _require_internal_service(request, scope)
    idempotency_key = _require_idempotency_key(request)
    with _postgres_conn() as conn:
        cached_response = _begin_idempotent_request(conn, scope, idempotency_key, _build_request_hash(payload))
        if cached_response is not None:
            return cached_response
        user = _ensure_user_record(
            conn,
            user_id=payload.user_id,
            email=payload.user_email,
            display_name=payload.display_name,
            plan_tier=payload.plan_tier,
        )
        updated_account, ledger_entry = _grant_points_with_ledger(
            conn=conn,
            user_id=user.user_id,
            points=payload.points,
            entry_type=payload.entry_type,
            event_type=payload.entry_type,
            reference_id=payload.reference_id,
            description=payload.description,
            meta_json=payload.meta,
            granted_points=payload.points,
        )
        response_json = _success_response(
            "/internal/admin/grant-points",
            {"points_account": updated_account, "ledger_entry": ledger_entry},
            "points granted",
        )
        _complete_idempotent_request(conn, scope, idempotency_key, response_json)
    return response_json


# ---------------------------------------------------------------------------
# Billing charge / refund
# ---------------------------------------------------------------------------

@router.post("/internal/billing/charge-points")
def charge_points(request: Request, payload: ChargePointsRequest) -> dict[str, Any]:
    scope = request.url.path
    _require_internal_service(request, scope)
    idempotency_key = _require_idempotency_key(request)
    with _postgres_conn() as conn:
        cached_response = _begin_idempotent_request(conn, scope, idempotency_key, _build_request_hash(payload))
        if cached_response is not None:
            return cached_response
        api_key_row = _resolve_user_api_key(conn, payload.api_key)
        if api_key_row is None:
            raise HTTPException(status_code=401, detail="invalid user api key")
        if api_key_row["status"] != "active":
            raise HTTPException(status_code=403, detail="user api key inactive")

        user = _fetch_user(conn, api_key_row["user_id"])
        if _is_guest_daily_quota_user(user):
            _apply_guest_daily_quota_if_needed(conn, user)
        account = _get_credit_account(conn, api_key_row["user_id"], for_update=True)
        total_points = sum(_calculate_points_for_event(event.event_type, event.units) for event in payload.events)
        if int(account["balance_points"]) < total_points:
            raise HTTPException(status_code=402, detail="insufficient points")

        charges: list[dict[str, Any]] = []
        balance_after = int(account["balance_points"])
        for event in payload.events:
            charged_points = _calculate_points_for_event(event.event_type, event.units)
            source_allocations = _preview_credit_consumption_allocations(
                conn,
                api_key_row["user_id"],
                charged_points,
            )
            balance_after -= charged_points
            updated_account = _run_pg_dict_query(
                conn,
                """
                UPDATE app.user_credit_account
                SET balance_points = %s,
                    lifetime_spent_points = lifetime_spent_points + %s,
                    updated_at = NOW()
                WHERE user_id = %s
                RETURNING user_id, balance_points, reserved_points, lifetime_granted_points,
                          lifetime_purchased_points, lifetime_spent_points, created_at, updated_at
                """,
                [balance_after, charged_points, api_key_row["user_id"]],
            )[0]
            usage_event = _record_usage_event(
                conn,
                user_id=api_key_row["user_id"],
                session_id=None,
                run_id=None,
                event_type=event.event_type,
                units=event.units,
                meta_json={
                    **event.meta,
                    "api_key_id": api_key_row["api_key_id"],
                    "points_price_version": POINTS_PRICE_VERSION,
                    "points_charged": charged_points,
                },
            )
            ledger_entry = _create_ledger_entry(
                conn=conn,
                user_id=api_key_row["user_id"],
                api_key_id=api_key_row["api_key_id"],
                entry_type="consume",
                event_type=event.event_type,
                units=event.units,
                points_delta=-charged_points,
                balance_after_points=balance_after,
                reference_id=event.reference_id,
                description=event.description,
                meta_json={
                    **event.meta,
                    "points_price_version": POINTS_PRICE_VERSION,
                    "points_charged": charged_points,
                    "balance_source_allocations": source_allocations,
                },
            )
            charges.append(
                {
                    "event_type": event.event_type,
                    "units": event.units,
                    "points_charged": charged_points,
                    "balance_source_allocations": source_allocations,
                    "usage_event": usage_event,
                    "ledger_entry": ledger_entry,
                    "points_account": updated_account,
                }
            )

        _touch_user_api_key(conn, api_key_row["api_key_id"])
        if _is_guest_daily_quota_user(user):
            _adjust_daily_credit_quota_consumed(conn, api_key_row["user_id"], total_points)

        response_json = _success_response(
            "/internal/billing/charge-points",
            {
                "user_id": api_key_row["user_id"],
                "api_key_id": api_key_row["api_key_id"],
                "pricing_version": POINTS_PRICE_VERSION,
                "charges": charges,
            },
            "points charged",
        )
        _complete_idempotent_request(conn, scope, idempotency_key, response_json)
    return response_json


@router.post("/internal/billing/refund-points")
def refund_points(request: Request, payload: RefundPointsRequest) -> dict[str, Any]:
    scope = request.url.path
    _require_internal_service(request, scope)
    idempotency_key = _require_idempotency_key(request)
    with _postgres_conn() as conn:
        cached_response = _begin_idempotent_request(conn, scope, idempotency_key, _build_request_hash(payload))
        if cached_response is not None:
            return cached_response
        api_key_row = _resolve_user_api_key(conn, payload.api_key)
        if api_key_row is None:
            raise HTTPException(status_code=401, detail="invalid user api key")

        user = _fetch_user(conn, api_key_row["user_id"])
        account = _get_credit_account(conn, api_key_row["user_id"], for_update=True)
        balance_after = int(account["balance_points"]) + payload.points
        refund_allocations = _resolve_refund_source_allocations(
            conn,
            user_id=api_key_row["user_id"],
            reference_id=payload.reference_id,
            event_type=payload.event_type,
            points=payload.points,
        )
        updated_account = _run_pg_dict_query(
            conn,
            """
            UPDATE app.user_credit_account
            SET balance_points = %s,
                lifetime_spent_points = GREATEST(0, lifetime_spent_points - %s),
                updated_at = NOW()
            WHERE user_id = %s
            RETURNING user_id, balance_points, reserved_points, lifetime_granted_points,
                      lifetime_purchased_points, lifetime_spent_points, created_at, updated_at
            """,
            [balance_after, payload.points, api_key_row["user_id"]],
        )[0]
        ledger_entry = _create_ledger_entry(
            conn=conn,
            user_id=api_key_row["user_id"],
            api_key_id=api_key_row["api_key_id"],
            entry_type="refund",
            event_type=payload.event_type,
            units=payload.units,
            points_delta=payload.points,
            balance_after_points=balance_after,
            reference_id=payload.reference_id,
            description=payload.description,
            meta_json={
                **payload.meta,
                "points_price_version": POINTS_PRICE_VERSION,
                "points_refunded": payload.points,
                "refund_allocations": refund_allocations,
            },
        )
        _touch_user_api_key(conn, api_key_row["api_key_id"])

        response_json = _success_response(
            "/internal/billing/refund-points",
            {
                "user_id": api_key_row["user_id"],
                "api_key_id": api_key_row["api_key_id"],
                "pricing_version": POINTS_PRICE_VERSION,
                "points_account": updated_account,
                "balance_breakdown": _build_credit_balance_breakdown(conn, api_key_row["user_id"]),
                "ledger_entry": ledger_entry,
            },
            "points refunded",
        )
        if _is_guest_daily_quota_user(user):
            _adjust_daily_credit_quota_consumed(conn, api_key_row["user_id"], -payload.points)
        _complete_idempotent_request(conn, scope, idempotency_key, response_json)
    return response_json


# ---------------------------------------------------------------------------
# Dify run callback
# ---------------------------------------------------------------------------

@router.post("/internal/dify/run-callback")
def dify_run_callback(payload: DifyRunCallbackRequest) -> dict[str, Any]:
    with _postgres_conn() as conn:
        rows = _run_pg_dict_query(
            conn,
            """
            SELECT r.run_id, r.session_id, s.user_id
            FROM app.analysis_run r
            JOIN app.chat_session s ON r.session_id = s.session_id
            WHERE r.run_id = %s
            LIMIT 1
            """,
            [payload.run_id],
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"analysis run not found: {payload.run_id}")

        run_info = rows[0]
        finished_at = _utc_now() if payload.status in TERMINAL_RUN_STATUSES else None
        run_row = _run_pg_dict_query(
            conn,
            """
            UPDATE app.analysis_run
            SET status = %s,
                dify_run_id = COALESCE(%s, dify_run_id),
                final_answer_text = COALESCE(%s, final_answer_text),
                finished_at = COALESCE(%s, finished_at),
                updated_at = NOW()
            WHERE run_id = %s
            RETURNING run_id, session_id, message_id, product_query, analysis_goal,
                      input_payload_json, status, dify_run_id, final_answer_text,
                      started_at, finished_at, created_at, updated_at
            """,
            [payload.status, payload.dify_run_id, payload.final_answer_text, finished_at, payload.run_id],
        )[0]

        assistant_message_row = None
        if payload.assistant_message:
            assistant_message_row = _run_pg_dict_query(
                conn,
                """
                INSERT INTO app.chat_message (
                    message_id, session_id, role, content, message_type, metadata_json, created_at
                ) VALUES (%s, %s, 'assistant', %s, %s, %s, NOW())
                RETURNING message_id, session_id, role, content, message_type, metadata_json, created_at
                """,
                [
                    _generate_id("msg"),
                    run_info["session_id"],
                    payload.assistant_message,
                    payload.assistant_message_type,
                    psycopg2.extras.Json({"source": "dify_callback", "run_id": payload.run_id}),
                ],
            )[0]

        artifact_rows: list[dict[str, Any]] = []
        for artifact in payload.artifacts:
            artifact_rows.append(
                _run_pg_dict_query(
                    conn,
                    """
                    INSERT INTO app.analysis_artifact (
                        artifact_id, run_id, artifact_type, artifact_key, artifact_payload_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (run_id, artifact_key) DO UPDATE SET
                        artifact_type = EXCLUDED.artifact_type,
                        artifact_payload_json = EXCLUDED.artifact_payload_json
                    RETURNING artifact_id, run_id, artifact_type, artifact_key, artifact_payload_json, created_at
                    """,
                    [
                        _generate_id("artifact"),
                        payload.run_id,
                        artifact.artifact_type,
                        artifact.artifact_key,
                        psycopg2.extras.Json(artifact.artifact_payload),
                    ],
                )[0]
            )

        usage_rows: list[dict[str, Any]] = []
        for usage_event in payload.usage_events:
            usage_meta = dict(usage_event.meta or {})
            if usage_event.event_type in WORKFLOW_BUNDLED_NON_BILLABLE_EVENT_TYPES:
                usage_meta.update(
                    {
                        "billing_status": "audit_only",
                        "billing_reason": "bundled_into_dify_workflow_run",
                        "bundled_parent_event_type": "dify_workflow_run",
                    }
                )
            usage_rows.append(
                _record_usage_event(
                    conn,
                    user_id=run_info["user_id"],
                    session_id=run_info["session_id"],
                    run_id=payload.run_id,
                    event_type=usage_event.event_type,
                    units=usage_event.units,
                    meta_json=usage_meta,
                )
            )

        _run_pg_dict_query(
            conn,
            "UPDATE app.chat_session SET updated_at = NOW() WHERE session_id = %s RETURNING session_id",
            [run_info["session_id"]],
        )

    return _success_response(
        "/internal/dify/run-callback",
        {
            "run": run_row,
            "assistant_message": assistant_message_row,
            "artifacts": artifact_rows,
            "usage_events": usage_rows,
        },
        "dify callback processed",
    )


# ---------------------------------------------------------------------------
# Payment provider callback
# ---------------------------------------------------------------------------

def _safe_wechat_notify_headers(request: Request) -> dict[str, str]:
    keys = [
        "Wechatpay-Timestamp",
        "Wechatpay-Nonce",
        "Wechatpay-Serial",
        "Wechatpay-Signature",
    ]
    result: dict[str, str] = {}
    for key in keys:
        value = request.headers.get(key) or ""
        result[key] = "<present>" if key == "Wechatpay-Signature" and value else value
    return result


def _post_internal_payment_callback(provider: str, payload: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
    if not INTERNAL_SERVICE_SECRET:
        raise HTTPException(status_code=503, detail="CHAT_BACKEND_SERVICE_SECRET is not configured")
    callback_url = _backend_base_url() + f"/internal/payments/provider-callback/{provider}"
    headers = {
        INTERNAL_SERVICE_SECRET_HEADER_NAME: INTERNAL_SERVICE_SECRET,
        INTERNAL_SERVICE_NAME_HEADER_NAME: "wechat-pay-notify",
        IDEMPOTENCY_KEY_HEADER_NAME: idempotency_key,
    }
    try:
        response = http_requests.post(callback_url, headers=headers, json=payload, timeout=12)
    except Exception as exc:  # pragma: no cover - network failure only
        raise HTTPException(status_code=502, detail=f"internal payment callback failed: {exc}") from exc
    try:
        response_json = response.json()
    except Exception:
        response_json = {"message": response.text.strip() or response.reason}
    if response.status_code != 200 or response_json.get("success") is not True:
        raise HTTPException(
            status_code=502,
            detail=response_json.get("detail") or response_json.get("message") or "internal payment callback failed",
        )
    return response_json


@router.post("/internal/payments/provider-notify/wechat")
async def internal_wechat_payment_notify(request: Request) -> dict[str, str]:
    raw_body = await request.body()
    safe_headers = _safe_wechat_notify_headers(request)
    try:
        notification, decrypted = verify_and_decrypt_wechat_notify(request.headers, raw_body)
        trade = extract_wechat_trade_payload(decrypted)
    except HTTPException as exc:
        with _postgres_conn() as conn:
            _insert_payment_callback_event(
                conn,
                provider="wechat",
                payload_json={
                    "headers": safe_headers,
                    "raw_body_preview": raw_body.decode("utf-8", errors="replace")[:4000],
                    "error": str(exc.detail),
                },
                signature_verified=False,
                processed_status="rejected",
                event_type="wechat_notify",
            )
        raise

    order_id = str(trade.get("order_id") or "").strip()
    provider_trade_no = trade.get("provider_trade_no")
    paid_amount_cents = trade.get("paid_amount_cents")
    trade_state = str(trade.get("trade_state") or "").strip().upper()

    with _postgres_conn() as conn:
        try:
            order_row = _fetch_payment_order(conn, order_id)
            latest_session = _fetch_latest_payment_session(conn, order_id)
            if str(order_row.get("provider") or "").strip().lower() != "wechat":
                raise HTTPException(status_code=409, detail="payment provider does not match order provider")
            if paid_amount_cents is None or int(paid_amount_cents) != int(order_row["amount_cents"]):
                raise HTTPException(status_code=400, detail="payment amount does not match order amount")
            if trade_state != "SUCCESS":
                _insert_payment_callback_event(
                    conn,
                    provider="wechat",
                    order_id=order_id,
                    provider_order_id=trade.get("provider_order_id") or order_id,
                    provider_trade_no=provider_trade_no,
                    event_type="wechat_notify",
                    signature_verified=True,
                    payload_json={"notification": notification, "decrypted": decrypted},
                    processed_status="ignored",
                    processed_at=_utc_now(),
                )
                if latest_session:
                    _update_payment_session_status(
                        conn,
                        session_id=str(latest_session["session_id"]),
                        status="pending",
                        provider_trade_no=provider_trade_no,
                        prepay_payload_json={
                            **dict(latest_session.get("prepay_payload_json") or {}),
                            "last_notify_payload": decrypted,
                        },
                    )
                return {"code": "SUCCESS", "message": "成功"}
        except HTTPException as exc:
            _insert_payment_callback_event(
                conn,
                provider="wechat",
                order_id=order_id or None,
                provider_order_id=trade.get("provider_order_id") or order_id or None,
                provider_trade_no=provider_trade_no,
                event_type="wechat_notify",
                signature_verified=True,
                payload_json={"notification": notification, "decrypted": decrypted, "error": str(exc.detail)},
                processed_status="rejected",
                processed_at=_utc_now(),
            )
            raise

    callback_payload = {
        "order_id": order_id,
        "provider_order_id": trade.get("provider_order_id") or order_id,
        "provider_trade_no": provider_trade_no,
        "paid_amount_cents": paid_amount_cents,
        "meta": {
            "source": "wechat_pay_notify",
            "trade_state": trade_state,
            "wechat_payload": decrypted,
        },
    }
    try:
        _post_internal_payment_callback(
            "wechat",
            callback_payload,
            idempotency_key=f"wechat-notify:{provider_trade_no or order_id}",
        )
    except HTTPException as exc:
        with _postgres_conn() as conn:
            _insert_payment_callback_event(
                conn,
                provider="wechat",
                order_id=order_id or None,
                provider_order_id=trade.get("provider_order_id") or order_id or None,
                provider_trade_no=provider_trade_no,
                event_type="wechat_notify",
                signature_verified=True,
                payload_json={"notification": notification, "decrypted": decrypted, "error": str(exc.detail)},
                processed_status="failed",
                processed_at=_utc_now(),
            )
        raise

    with _postgres_conn() as conn:
        latest_session = _fetch_latest_payment_session(conn, order_id)
        if latest_session:
            _update_payment_session_status(
                conn,
                session_id=str(latest_session["session_id"]),
                status="paid",
                provider_trade_no=provider_trade_no,
                prepay_payload_json={
                    **dict(latest_session.get("prepay_payload_json") or {}),
                    "last_notify_payload": decrypted,
                },
                paid_at=_utc_now(),
            )
        _insert_payment_callback_event(
            conn,
            provider="wechat",
            order_id=order_id,
            provider_order_id=trade.get("provider_order_id") or order_id,
            provider_trade_no=provider_trade_no,
            event_type="wechat_notify",
            signature_verified=True,
            payload_json={"notification": notification, "decrypted": decrypted},
            processed_status="processed",
            processed_at=_utc_now(),
        )
    return {"code": "SUCCESS", "message": "成功"}

@router.post("/internal/payments/provider-callback/{provider}")
def internal_payment_provider_callback(provider: str, request: Request, payload: PaymentProviderCallbackRequest) -> dict[str, Any]:
    scope = request.url.path
    _require_internal_service(request, scope)
    idempotency_key = _require_idempotency_key(request)
    with _postgres_conn() as conn:
        cached_response = _begin_idempotent_request(conn, scope, idempotency_key, _build_request_hash(payload))
        if cached_response is not None:
            return cached_response

        order_row = _fetch_payment_order(conn, payload.order_id)
        if order_row["provider"] != provider:
            raise HTTPException(status_code=409, detail="payment provider does not match order provider")

        package = _fetch_billing_package(conn, order_row["package_code"])
        if payload.paid_amount_cents is not None and int(payload.paid_amount_cents) != int(order_row["amount_cents"]):
            raise HTTPException(status_code=400, detail="payment amount does not match order amount")

        if order_row["status"] == "paid":
            updated_account = _get_credit_account(conn, order_row["user_id"], for_update=False)
            subscription_row = None
            promotion_results: list[dict[str, Any]] = []
            if order_row["product_type"] == "monthly_subscription":
                subscriptions = _run_pg_dict_query(
                    conn,
                    """
                    SELECT subscription_id, user_id, package_code, provider, provider_subscription_id,
                           status, monthly_points, current_period_start, current_period_end,
                           next_grant_at, last_grant_at, cancel_at_period_end, meta_json,
                           created_at, updated_at
                    FROM app.billing_subscription
                    WHERE user_id = %s AND package_code = %s
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT 1
                    """,
                    [order_row["user_id"], order_row["package_code"]],
                )
                subscription_row = subscriptions[0] if subscriptions else None
            response_json = _success_response(
                f"/internal/payments/provider-callback/{provider}",
                {
                    "order": order_row,
                    "package": package,
                    "points_account": updated_account,
                    "subscription": subscription_row,
                    "ledger_entry": None,
                    "subscription_grant": None,
                    "promotion_results": promotion_results,
                },
                "payment callback already applied",
            )
            _complete_idempotent_request(conn, scope, idempotency_key, response_json)
            return response_json

        updated_order_rows = _run_pg_dict_query(
            conn,
            """
            UPDATE app.payment_order
            SET status = 'paid',
                provider_order_id = COALESCE(%s, provider_order_id),
                provider_trade_no = COALESCE(%s, provider_trade_no),
                callback_payload_json = %s,
                paid_at = COALESCE(paid_at, NOW()),
                updated_at = NOW()
            WHERE order_id = %s AND status <> 'paid'
            RETURNING order_id, user_id, package_code, product_type, provider, list_amount_cents,
                      discount_amount_cents, amount_cents, points_amount, status,
                      provider_order_id, provider_trade_no, promotion_snapshot_json,
                      callback_payload_json, paid_at, created_at, updated_at
            """,
            [
                payload.provider_order_id,
                payload.provider_trade_no,
                psycopg2.extras.Json(payload.meta),
                payload.order_id,
            ],
        )
        if not updated_order_rows:
            order_row = _fetch_payment_order(conn, payload.order_id)
            updated_account = _get_credit_account(conn, order_row["user_id"], for_update=False)
            subscription_row = None
            if order_row["product_type"] == "monthly_subscription":
                subscriptions = _run_pg_dict_query(
                    conn,
                    """
                    SELECT subscription_id, user_id, package_code, provider, provider_subscription_id,
                           status, monthly_points, current_period_start, current_period_end,
                           next_grant_at, last_grant_at, cancel_at_period_end, meta_json,
                           created_at, updated_at
                    FROM app.billing_subscription
                    WHERE user_id = %s AND package_code = %s
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT 1
                    """,
                    [order_row["user_id"], order_row["package_code"]],
                )
                subscription_row = subscriptions[0] if subscriptions else None
            response_json = _success_response(
                f"/internal/payments/provider-callback/{provider}",
                {
                    "order": order_row,
                    "package": package,
                    "points_account": updated_account,
                    "subscription": subscription_row,
                    "ledger_entry": None,
                    "subscription_grant": None,
                    "promotion_results": [],
                },
                "payment callback already applied",
            )
            _complete_idempotent_request(conn, scope, idempotency_key, response_json)
            return response_json
        updated_order = updated_order_rows[0]

        subscription_row = None
        subscription_grant_row = None
        promotion_results: list[dict[str, Any]] = []
        if package["product_type"] == "credit_pack":
            updated_account, ledger_entry = _grant_points_with_ledger(
                conn=conn,
                user_id=updated_order["user_id"],
                points=int(package["points_amount"]),
                entry_type="recharge",
                event_type="recharge",
                reference_id=updated_order["order_id"],
                description="credit pack purchase",
                meta_json={
                    "provider": provider,
                    "package_code": package["package_code"],
                    "payment_order_id": updated_order["order_id"],
                    "provider_trade_no": payload.provider_trade_no,
                },
                purchased_points=int(package["points_amount"]),
            )
            updated_account, promotion_results = _apply_order_promotions_after_payment(
                conn,
                order_row=updated_order,
                package=package,
                provider=provider,
                provider_trade_no=payload.provider_trade_no,
                updated_account=updated_account,
            )
        else:
            period_start, period_end = _normalize_period_window(
                payload.period_start,
                payload.period_end,
                int(package["period_days"]),
            )
            existing_subscription = None
            if payload.provider_subscription_id:
                existing_subscription = _fetch_optional_one(
                    conn,
                    """
                    SELECT subscription_id, user_id, package_code, provider, provider_subscription_id,
                           status, monthly_points, current_period_start, current_period_end,
                           next_grant_at, last_grant_at, cancel_at_period_end, meta_json,
                           created_at, updated_at
                    FROM app.billing_subscription
                    WHERE provider = %s AND provider_subscription_id = %s
                    LIMIT 1
                    """,
                    [provider, payload.provider_subscription_id],
                )
            if existing_subscription is None:
                existing_subscription = _run_pg_dict_query(
                    conn,
                    """
                    INSERT INTO app.billing_subscription (
                        subscription_id, user_id, package_code, provider, provider_subscription_id,
                        status, monthly_points, current_period_start, current_period_end,
                        next_grant_at, last_grant_at, cancel_at_period_end, meta_json,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, 'active', %s, %s, %s, %s, NULL, FALSE, %s, NOW(), NOW())
                    RETURNING subscription_id, user_id, package_code, provider, provider_subscription_id,
                              status, monthly_points, current_period_start, current_period_end,
                              next_grant_at, last_grant_at, cancel_at_period_end, meta_json,
                              created_at, updated_at
                    """,
                    [
                        _generate_id("sub"),
                        updated_order["user_id"],
                        package["package_code"],
                        provider,
                        payload.provider_subscription_id,
                        int(package["points_amount"]),
                        period_start,
                        period_end,
                        period_end,
                        psycopg2.extras.Json(
                            {
                                "payment_order_id": updated_order["order_id"],
                                "provider_trade_no": payload.provider_trade_no,
                            }
                        ),
                    ],
                )[0]
            subscription_row, updated_account, subscription_grant_row, ledger_entry = _grant_subscription_period(
                conn=conn,
                subscription_row=existing_subscription,
                period_start=period_start,
                period_end=period_end,
                reference_id=payload.provider_trade_no or f"{existing_subscription['subscription_id']}:{period_start.isoformat()}:{period_end.isoformat()}",
                order_id=updated_order["order_id"],
                meta_json={
                    "provider": provider,
                    "package_code": package["package_code"],
                    "payment_order_id": updated_order["order_id"],
                    "provider_subscription_id": payload.provider_subscription_id,
                },
            )
            _apply_user_plan_tier_from_package(conn, updated_order["user_id"], package)
            updated_account, promotion_results = _apply_order_promotions_after_payment(
                conn,
                order_row=updated_order,
                package=package,
                provider=provider,
                provider_trade_no=payload.provider_trade_no,
                updated_account=updated_account,
            )

        response_json = _success_response(
            f"/internal/payments/provider-callback/{provider}",
            {
                "order": updated_order,
                "package": package,
                "points_account": updated_account,
                "subscription": subscription_row,
                "ledger_entry": ledger_entry,
                "subscription_grant": subscription_grant_row,
                "promotion_results": promotion_results,
            },
            "payment callback applied",
        )
        _complete_idempotent_request(conn, scope, idempotency_key, response_json)
    return response_json


# ---------------------------------------------------------------------------
# Subscription grant
# ---------------------------------------------------------------------------

@router.post("/internal/subscriptions/{subscription_id}/grant")
def internal_grant_subscription_points(
    subscription_id: str,
    request: Request,
    payload: GrantSubscriptionRequest,
) -> dict[str, Any]:
    scope = request.url.path
    _require_internal_service(request, scope)
    idempotency_key = _require_idempotency_key(request)
    with _postgres_conn() as conn:
        cached_response = _begin_idempotent_request(conn, scope, idempotency_key, _build_request_hash(payload))
        if cached_response is not None:
            return cached_response

        subscription_row = _fetch_subscription(conn, subscription_id)
        period_start, period_end = _normalize_period_window(
            payload.period_start,
            payload.period_end,
            max(1, int(subscription_row["monthly_points"])),
        )
        reference_id = payload.provider_trade_no or f"{subscription_id}:{period_start.isoformat()}:{period_end.isoformat()}"
        updated_subscription, updated_account, grant_row, ledger_entry = _grant_subscription_period(
            conn=conn,
            subscription_row=subscription_row,
            period_start=period_start,
            period_end=period_end,
            reference_id=reference_id,
            order_id=payload.order_id,
            meta_json={
                **payload.meta,
                "provider_trade_no": payload.provider_trade_no,
            },
        )
        response_json = _success_response(
            f"/internal/subscriptions/{subscription_id}/grant",
            {
                "subscription": updated_subscription,
                "points_account": updated_account,
                "subscription_grant": grant_row,
                "ledger_entry": ledger_entry,
            },
            "subscription points granted",
        )
        _complete_idempotent_request(conn, scope, idempotency_key, response_json)
    return response_json
