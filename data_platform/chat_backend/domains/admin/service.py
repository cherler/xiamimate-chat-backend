"""Admin domain — overview, audit logging, and cross-domain account views."""
from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder

try:
    import psycopg2.extras
except ImportError:
    pass

from data_platform.chat_backend.infra.settings import (
    PLAN_LIMITS,
    POINTS_PRICE_VERSION,
    _generate_id,
    _is_guest_identity,
)
from data_platform.chat_backend.infra.postgres import _run_pg_dict_query
from data_platform.chat_backend.domains.identity.service import (
    _build_identity_verification_summary,
    _fetch_user,
)
from data_platform.chat_backend.domains.api_keys.service import _list_api_keys_for_user
from data_platform.chat_backend.domains.billing.service import (
    _apply_guest_daily_quota_if_needed,
    _build_credit_balance_breakdown,
    _ensure_credit_account,
    _fetch_latest_daily_credit_quota_state,
    _fetch_subscriptions_for_user,
    _get_credit_account,
    _get_event_pricing,
    _get_point_cost_by_event,
    _load_event_pricing_from_db,
)


def _audit_admin_action(
    conn,
    operator_id: str,
    action: str,
    target_type: str,
    target_id: str | None,
    request_json: dict[str, Any],
    result_json: dict[str, Any],
) -> dict[str, Any]:
    return _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.admin_audit_log (
            audit_id, operator_id, action, target_type, target_id, request_json, result_json, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING audit_id, operator_id, action, target_type, target_id, request_json, result_json, created_at
        """,
        [
            _generate_id("admin_audit"),
            operator_id,
            action,
            target_type,
            target_id,
            psycopg2.extras.Json(jsonable_encoder(request_json)),
            psycopg2.extras.Json(jsonable_encoder(result_json)),
        ],
    )[0]


def _build_user_account_overview(
    conn,
    user_id: str,
    *,
    ledger_limit: int = 20,
    usage_limit: int = 20,
    order_limit: int = 10,
    session_limit: int = 10,
    run_limit: int = 10,
) -> dict[str, Any]:
    user = _fetch_user(conn, user_id)
    _ensure_credit_account(conn, user_id)
    if _is_guest_identity(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        plan_tier=user.plan_tier,
    ):
        _apply_guest_daily_quota_if_needed(conn, user)
    points_account = _get_credit_account(conn, user_id, for_update=False)
    balance_breakdown = _build_credit_balance_breakdown(conn, user_id)
    user = _fetch_user(conn, user_id)
    api_keys = _list_api_keys_for_user(conn, user_id)
    recent_ledger = _run_pg_dict_query(
        conn,
        """
        SELECT entry_id, entry_type, event_type, units, points_delta, balance_after_points,
               reference_id, description, meta_json, created_at
        FROM app.credit_ledger_entry
        WHERE user_id = %s
        ORDER BY created_at DESC, entry_id DESC
        LIMIT %s
        """,
        [user_id, ledger_limit],
    )
    usage_summary = _run_pg_dict_query(
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
        [user_id],
    )[0]
    usage_by_type_30d = _run_pg_dict_query(
        conn,
        """
        SELECT event_type, COALESCE(SUM(units), 0) AS total_units
        FROM app.usage_event
        WHERE user_id = %s
          AND created_at >= NOW() - INTERVAL '30 day'
        GROUP BY event_type
        ORDER BY total_units DESC, event_type ASC
        """,
        [user_id],
    )
    recent_usage_events = _run_pg_dict_query(
        conn,
        """
        SELECT event_id, session_id, run_id, event_type, units, meta_json, created_at
        FROM app.usage_event
        WHERE user_id = %s
        ORDER BY created_at DESC, event_id DESC
        LIMIT %s
        """,
        [user_id, usage_limit],
    )
    recent_orders = _run_pg_dict_query(
        conn,
        """
        SELECT order_id, package_code, product_type, provider, amount_cents, points_amount,
               status, provider_order_id, provider_trade_no, paid_at, created_at, updated_at
        FROM app.payment_order
        WHERE user_id = %s
        ORDER BY created_at DESC, order_id DESC
        LIMIT %s
        """,
        [user_id, order_limit],
    )
    recent_sessions = _run_pg_dict_query(
        conn,
        """
        SELECT session_id, title, target_platform, target_market, validation_marketplace,
               status, created_at, updated_at, closed_at
        FROM app.chat_session
        WHERE user_id = %s
        ORDER BY updated_at DESC, session_id DESC
        LIMIT %s
        """,
        [user_id, session_limit],
    )
    recent_runs = _run_pg_dict_query(
        conn,
        """
        SELECT r.run_id, r.session_id, r.message_id, r.product_query, r.analysis_goal,
               r.status, r.dify_run_id, r.started_at, r.finished_at, r.created_at, r.updated_at,
               s.title AS session_title
        FROM app.analysis_run r
        JOIN app.chat_session s ON r.session_id = s.session_id
        WHERE s.user_id = %s
        ORDER BY r.updated_at DESC, r.run_id DESC
        LIMIT %s
        """,
        [user_id, run_limit],
    )
    daily_quota_state = _fetch_latest_daily_credit_quota_state(conn, user_id)
    return {
        "user": user.__dict__,
        "identity_verification": _build_identity_verification_summary(conn, user_id),
        "plan_tier": user.plan_tier,
        "entitlements": PLAN_LIMITS.get(user.plan_tier, {}),
        "api_keys": api_keys,
        "points_account": points_account,
        "balance_breakdown": balance_breakdown,
        "daily_quota_state": daily_quota_state,
        "recent_ledger": recent_ledger,
        "usage_summary": usage_summary,
        "usage_by_type_30d": usage_by_type_30d,
        "recent_usage_events": recent_usage_events,
        "recent_orders": recent_orders,
        "subscriptions": _fetch_subscriptions_for_user(conn, user_id),
        "recent_sessions": recent_sessions,
        "recent_runs": recent_runs,
        "pricing_version": POINTS_PRICE_VERSION,
        "point_cost_by_event": _get_point_cost_by_event(),
        "event_pricing_display": {k: v["display_name"] for k, v in _get_event_pricing().items()},
    }


def _build_admin_overview(conn) -> dict[str, Any]:
    metrics = _run_pg_dict_query(
        conn,
        """
        SELECT
            (SELECT COUNT(*) FROM app.app_user) AS total_users,
            (SELECT COUNT(*) FROM app.user_api_key WHERE status = 'active') AS active_api_keys,
            (SELECT COUNT(*) FROM app.payment_order WHERE status = 'paid') AS paid_orders,
            (SELECT COUNT(*) FROM app.billing_subscription WHERE status = 'active') AS active_subscriptions,
            (SELECT COUNT(*) FROM app.analysis_run WHERE status = 'running') AS running_analysis_runs,
            (SELECT COALESCE(SUM(balance_points), 0) FROM app.user_credit_account) AS total_balance_points
        """,
    )[0]
    recent_ledger = _run_pg_dict_query(
        conn,
        """
        SELECT l.entry_id, l.user_id, u.display_name, l.entry_type, l.event_type, l.points_delta,
               l.balance_after_points, l.description, l.created_at
        FROM app.credit_ledger_entry l
        JOIN app.app_user u ON l.user_id = u.user_id
        ORDER BY l.created_at DESC, l.entry_id DESC
        LIMIT 20
        """,
    )
    recent_orders = _run_pg_dict_query(
        conn,
        """
        SELECT o.order_id, o.user_id, u.display_name, o.package_code, o.provider,
               o.amount_cents, o.points_amount, o.status, o.paid_at, o.created_at
        FROM app.payment_order o
        JOIN app.app_user u ON o.user_id = u.user_id
        ORDER BY o.created_at DESC, o.order_id DESC
        LIMIT 20
        """,
    )
    event_pricing = _load_event_pricing_from_db(conn)
    return {
        "metrics": metrics,
        "recent_ledger": recent_ledger,
        "recent_orders": recent_orders,
        "event_pricing": list(event_pricing.values()),
    }
