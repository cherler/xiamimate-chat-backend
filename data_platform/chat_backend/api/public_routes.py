"""Public API routes — /health, /v1/*."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

try:
    import psycopg2.extras
except ImportError:
    pass

from data_platform.chat_backend.infra.settings import (
    PLAN_LIMITS,
    POINTS_PRICE_VERSION,
    _generate_id,
)
from data_platform.chat_backend.infra.postgres import (
    _ensure_app_schema,
    _postgres_conn,
    _run_pg_dict_query,
)
from data_platform.chat_backend.infra.http import _success_response
from data_platform.chat_backend.domains.identity.service import _provision_user_identity
from data_platform.chat_backend.domains.api_keys.service import _build_public_api_key_payload
from data_platform.chat_backend.domains.billing.service import (
    _fetch_billing_package,
    _get_point_cost_by_event,
    _list_billing_packages,
    _seed_billing_event_pricing,
    _seed_billing_packages,
    _fetch_subscriptions_for_user,
)
from data_platform.chat_backend.domains.payments.service import _fetch_payment_order_for_user
from data_platform.chat_backend.domains.runtime_records.service import (
    _fetch_run_for_user,
    _fetch_session_for_user,
    _require_active_session,
)
from data_platform.chat_backend.domains.admin.service import _build_user_account_overview
from data_platform.chat_backend.api.models import (
    CreateMessageRequest,
    CreatePaymentOrderRequest,
    CreateSessionRequest,
    CreateThemeRunRequest,
)

router = APIRouter()


@router.get("/health")
def health() -> dict[str, Any]:
    with _postgres_conn() as conn:
        _ensure_app_schema(conn)
        _seed_billing_packages(conn)
        _seed_billing_event_pricing(conn)
        _run_pg_dict_query(conn, "SELECT 1 AS ok")
    return _success_response(
        "/health",
        {"status": "ok", "pricing_version": POINTS_PRICE_VERSION},
        "healthy",
    )


@router.post("/v1/identity/exchange")
def exchange_identity(payload: dict[str, Any]) -> dict[str, Any]:
    from data_platform.chat_backend.api.models import IdentityExchangeRequest
    req = IdentityExchangeRequest(**payload)
    with _postgres_conn() as conn:
        from data_platform.chat_backend.domains.identity.service import _upsert_user_row
        user = _upsert_user_row(conn, user_id=req.user_id, email=req.email, display_name=req.display_name)
        from data_platform.chat_backend.domains.api_keys.service import _ensure_user_api_key
        user_api_key = _ensure_user_api_key(conn, user)
        from data_platform.chat_backend.domains.billing.service import _ensure_user_credit_account_state
        credit_account = _ensure_user_credit_account_state(conn, user)
    return _success_response(
        "/v1/identity/exchange",
        {
            "user": user.__dict__,
            "api_key": _build_public_api_key_payload(user_api_key),
            "points_account": credit_account.__dict__,
            "pricing_version": POINTS_PRICE_VERSION,
            "point_cost_by_event": _get_point_cost_by_event(),
        },
        "identity exchanged",
    )


@router.get("/v1/me")
def get_current_user(request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, user_api_key, credit_account = _provision_user_identity(conn, request)
    return _success_response(
        "/v1/me",
        {
            "user": user.__dict__,
            "api_key": _build_public_api_key_payload(user_api_key),
            "points_account": credit_account.__dict__,
            "pricing_version": POINTS_PRICE_VERSION,
            "point_cost_by_event": _get_point_cost_by_event(),
        },
        "current user loaded",
    )


@router.get("/v1/me/account-overview")
def get_my_account_overview(request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        overview = _build_user_account_overview(conn, user.user_id)
    return _success_response(
        "/v1/me/account-overview",
        overview,
        "account overview loaded",
    )


@router.get("/v1/me/usage")
def get_my_usage(request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        summary = _run_pg_dict_query(
            conn,
            """
            SELECT
                COALESCE(SUM(units) FILTER (WHERE created_at >= NOW() - INTERVAL '1 day'), 0) AS units_1d,
                COALESCE(SUM(units) FILTER (WHERE created_at >= NOW() - INTERVAL '7 day'), 0) AS units_7d,
                COALESCE(SUM(units) FILTER (WHERE created_at >= NOW() - INTERVAL '30 day'), 0) AS units_30d,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '30 day') AS event_count_30d
            FROM app.usage_event
            WHERE user_id = %s
            """,
            [user.user_id],
        )[0]
        by_type = _run_pg_dict_query(
            conn,
            """
            SELECT event_type, COALESCE(SUM(units), 0) AS total_units
            FROM app.usage_event
            WHERE user_id = %s
              AND created_at >= NOW() - INTERVAL '30 day'
            GROUP BY event_type
            ORDER BY total_units DESC, event_type ASC
            """,
            [user.user_id],
        )
    return _success_response(
        "/v1/me/usage",
        {
            "user_id": user.user_id,
            "usage": summary,
            "usage_by_type_30d": by_type,
        },
        "usage loaded",
    )


@router.get("/v1/me/plan")
def get_my_plan(request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
    return _success_response(
        "/v1/me/plan",
        {
            "user_id": user.user_id,
            "plan_tier": user.plan_tier,
            "entitlements": PLAN_LIMITS.get(user.plan_tier, {}),
        },
        "plan loaded",
    )


@router.get("/v1/me/api-key")
def get_my_api_key(request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, user_api_key, credit_account = _provision_user_identity(conn, request)
    return _success_response(
        "/v1/me/api-key",
        {
            "user_id": user.user_id,
            "api_key": _build_public_api_key_payload(user_api_key),
            "api_keys": [_build_public_api_key_payload(user_api_key)],
            "points_account": credit_account.__dict__,
            "pricing_version": POINTS_PRICE_VERSION,
            "point_cost_by_event": _get_point_cost_by_event(),
        },
        "user api key loaded",
    )


@router.get("/v1/me/points")
def get_my_points(request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, credit_account = _provision_user_identity(conn, request)
        ledger_rows = _run_pg_dict_query(
            conn,
            """
            SELECT entry_id, entry_type, event_type, units, points_delta, balance_after_points,
                   reference_id, description, meta_json, created_at
            FROM app.credit_ledger_entry
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 20
            """,
            [user.user_id],
        )
    return _success_response(
        "/v1/me/points",
        {
            "user_id": user.user_id,
            "points_account": credit_account.__dict__,
            "recent_ledger": ledger_rows,
            "pricing_version": POINTS_PRICE_VERSION,
            "point_cost_by_event": _get_point_cost_by_event(),
        },
        "points loaded",
    )


@router.get("/v1/billing/packages")
def list_billing_packages(request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        packages = _list_billing_packages(conn)
    return _success_response(
        "/v1/billing/packages",
        {
            "user_id": user.user_id,
            "packages": packages,
        },
        "billing packages loaded",
    )


@router.post("/v1/payments/orders")
def create_payment_order(request: Request, payload: CreatePaymentOrderRequest) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        package = _fetch_billing_package(conn, payload.package_code)
        order_id = _generate_id("order")
        order_row = _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.payment_order (
                order_id, user_id, package_code, product_type, provider, amount_cents,
                points_amount, status, callback_payload_json, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s, NOW(), NOW())
            RETURNING order_id, user_id, package_code, product_type, provider, amount_cents,
                      points_amount, status, provider_order_id, provider_trade_no,
                      callback_payload_json, paid_at, created_at, updated_at
            """,
            [
                order_id,
                user.user_id,
                package["package_code"],
                package["product_type"],
                payload.provider,
                package["price_cents"],
                package["points_amount"],
                psycopg2.extras.Json(
                    {
                        "package_name": package["package_name"],
                        "package_meta": package.get("meta_json") or {},
                        "created_via": "/v1/payments/orders",
                    }
                ),
            ],
        )[0]
    return _success_response(
        "/v1/payments/orders",
        {
            "order": order_row,
            "package": package,
        },
        "payment order created",
    )


@router.get("/v1/payments/orders/{order_id}")
def get_payment_order(order_id: str, request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        order_row = _fetch_payment_order_for_user(conn, order_id, user.user_id)
        package = _fetch_billing_package(conn, order_row["package_code"])
    return _success_response(
        f"/v1/payments/orders/{order_id}",
        {
            "order": order_row,
            "package": package,
        },
        "payment order loaded",
    )


@router.get("/v1/me/subscription")
def get_my_subscription(request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        subscriptions = _fetch_subscriptions_for_user(conn, user.user_id)
    return _success_response(
        "/v1/me/subscription",
        {
            "user_id": user.user_id,
            "subscriptions": subscriptions,
        },
        "subscription state loaded",
    )


# ---------------------------------------------------------------------------
# Chat sessions & messages
# ---------------------------------------------------------------------------

@router.post("/v1/chat/sessions")
def create_chat_session(request: Request, payload: CreateSessionRequest) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        session_id = _generate_id("sess")
        session_row = _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.chat_session (
                session_id, user_id, title, target_platform, target_market,
                validation_marketplace, status, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, 'active', NOW(), NOW())
            RETURNING session_id, user_id, title, target_platform, target_market,
                      validation_marketplace, status, created_at, updated_at, closed_at
            """,
            [
                session_id,
                user.user_id,
                payload.title,
                payload.target_platform,
                payload.target_market,
                payload.validation_marketplace,
            ],
        )[0]
    return _success_response("/v1/chat/sessions", {"session": session_row}, "chat session created")


@router.get("/v1/chat/sessions/{session_id}")
def get_chat_session(session_id: str, request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        session_row = _fetch_session_for_user(conn, session_id, user.user_id)
        counts = _run_pg_dict_query(
            conn,
            """
            SELECT
                (SELECT COUNT(*) FROM app.chat_message WHERE session_id = %s) AS message_count,
                (SELECT COUNT(*) FROM app.analysis_run WHERE session_id = %s) AS run_count
            """,
            [session_id, session_id],
        )[0]
    session_row.update(counts)
    return _success_response(f"/v1/chat/sessions/{session_id}", {"session": session_row}, "chat session loaded")


@router.get("/v1/chat/sessions/{session_id}/messages")
def list_chat_messages(session_id: str, request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        _fetch_session_for_user(conn, session_id, user.user_id)
        rows = _run_pg_dict_query(
            conn,
            """
            SELECT message_id, session_id, role, content, message_type, metadata_json, created_at
            FROM app.chat_message
            WHERE session_id = %s
            ORDER BY created_at ASC, message_id ASC
            """,
            [session_id],
        )
    return _success_response(
        f"/v1/chat/sessions/{session_id}/messages",
        {"session_id": session_id, "messages": rows},
        "chat messages loaded",
    )


@router.post("/v1/chat/sessions/{session_id}/messages")
def create_chat_message(session_id: str, request: Request, payload: CreateMessageRequest) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        session_row = _fetch_session_for_user(conn, session_id, user.user_id)
        _require_active_session(session_row)
        message_id = _generate_id("msg")
        row = _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.chat_message (
                message_id, session_id, role, content, message_type, metadata_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
            RETURNING message_id, session_id, role, content, message_type, metadata_json, created_at
            """,
            [message_id, session_id, payload.role, payload.content, payload.message_type, psycopg2.extras.Json(payload.metadata)],
        )[0]
        _run_pg_dict_query(
            conn,
            "UPDATE app.chat_session SET updated_at = NOW() WHERE session_id = %s RETURNING session_id",
            [session_id],
        )
    return _success_response(
        f"/v1/chat/sessions/{session_id}/messages",
        {"message": row},
        "chat message created",
    )


@router.post("/v1/chat/sessions/{session_id}/close")
def close_chat_session(session_id: str, request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        _fetch_session_for_user(conn, session_id, user.user_id)
        row = _run_pg_dict_query(
            conn,
            """
            UPDATE app.chat_session
            SET status = 'closed', updated_at = NOW(), closed_at = COALESCE(closed_at, NOW())
            WHERE session_id = %s AND user_id = %s
            RETURNING session_id, user_id, title, target_platform, target_market,
                      validation_marketplace, status, created_at, updated_at, closed_at
            """,
            [session_id, user.user_id],
        )[0]
    return _success_response(
        f"/v1/chat/sessions/{session_id}/close",
        {"session": row},
        "chat session closed",
    )


# ---------------------------------------------------------------------------
# Analysis runs & artifacts
# ---------------------------------------------------------------------------

@router.post("/v1/analysis/theme-runs")
def create_theme_run(request: Request, payload: CreateThemeRunRequest) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        session_row = _fetch_session_for_user(conn, payload.session_id, user.user_id)
        _require_active_session(session_row)
        if payload.message_id is not None:
            message_rows = _run_pg_dict_query(
                conn,
                "SELECT message_id FROM app.chat_message WHERE message_id = %s AND session_id = %s LIMIT 1",
                [payload.message_id, payload.session_id],
            )
            if not message_rows:
                raise HTTPException(status_code=404, detail=f"chat message not found: {payload.message_id}")

        run_id = _generate_id("run")
        run_row = _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.analysis_run (
                run_id, session_id, message_id, product_query, analysis_goal,
                input_payload_json, status, started_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, 'queued', NOW(), NOW(), NOW())
            RETURNING run_id, session_id, message_id, product_query, analysis_goal,
                      input_payload_json, status, dify_run_id, final_answer_text,
                      started_at, finished_at, created_at, updated_at
            """,
            [
                run_id,
                payload.session_id,
                payload.message_id,
                payload.product_query,
                payload.analysis_goal,
                psycopg2.extras.Json(payload.input_payload),
            ],
        )[0]
        _run_pg_dict_query(
            conn,
            "UPDATE app.chat_session SET updated_at = NOW() WHERE session_id = %s RETURNING session_id",
            [payload.session_id],
        )
    return _success_response("/v1/analysis/theme-runs", {"run": run_row}, "theme analysis run created")


@router.get("/v1/analysis/theme-runs/{run_id}")
def get_theme_run(run_id: str, request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        run_row = _fetch_run_for_user(conn, run_id, user.user_id)
        counts = _run_pg_dict_query(
            conn,
            "SELECT COUNT(*) AS artifact_count FROM app.analysis_artifact WHERE run_id = %s",
            [run_id],
        )[0]
    run_row.update(counts)
    return _success_response(f"/v1/analysis/theme-runs/{run_id}", {"run": run_row}, "theme analysis run loaded")


@router.get("/v1/analysis/theme-runs/{run_id}/artifacts")
def get_theme_run_artifacts(run_id: str, request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        _fetch_run_for_user(conn, run_id, user.user_id)
        rows = _run_pg_dict_query(
            conn,
            """
            SELECT artifact_id, run_id, artifact_type, artifact_key, artifact_payload_json, created_at
            FROM app.analysis_artifact
            WHERE run_id = %s
            ORDER BY created_at ASC, artifact_id ASC
            """,
            [run_id],
        )
    return _success_response(
        f"/v1/analysis/theme-runs/{run_id}/artifacts",
        {"run_id": run_id, "artifacts": rows},
        "analysis artifacts loaded",
    )
