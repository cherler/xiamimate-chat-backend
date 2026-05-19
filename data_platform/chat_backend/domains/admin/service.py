"""Admin domain — overview, audit logging, and cross-domain account views."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException
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
from data_platform.chat_backend.infra.postgres import _fetch_optional_one, _run_pg_dict_query
from data_platform.chat_backend.domains.identity.service import (
    _build_identity_verification_summary,
    _fetch_user,
    _reconcile_openwebui_user_sources,
    _reconcile_openwebui_user_sources_for_admin,
)
from data_platform.chat_backend.domains.notifications.service import (
    _list_notifications_for_user,
    _sync_portal_notifications,
)
from data_platform.chat_backend.domains.api_keys.service import _list_api_keys_for_user
from data_platform.chat_backend.domains.billing.service import (
    _apply_guest_daily_quota_if_needed,
    _build_credit_balance_breakdown,
    _create_ledger_entry,
    _ensure_credit_account,
    _fetch_latest_daily_credit_quota_state,
    _fetch_subscriptions_for_user,
    _get_credit_account,
    _get_event_pricing,
    _get_point_cost_by_event,
    _load_event_pricing_from_db,
)
from data_platform.chat_backend.domains.device_sessions.service import _list_recent_device_sessions


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
    current_device_session_id: str | None = None,
    ledger_limit: int = 20,
    usage_limit: int = 20,
    order_limit: int = 10,
    session_limit: int = 10,
    run_limit: int = 10,
) -> dict[str, Any]:
    _reconcile_openwebui_user_sources(conn, [user_id])
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
    subscriptions = _fetch_subscriptions_for_user(conn, user_id)
    _sync_portal_notifications(
        conn,
        user_id,
        points_account=points_account,
        recent_ledger=recent_ledger,
        recent_orders=recent_orders,
        subscriptions=subscriptions,
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
        "subscriptions": subscriptions,
        "notifications": _list_notifications_for_user(conn, user_id, limit=100),
        "recent_sessions": recent_sessions,
        "recent_runs": recent_runs,
        "current_device_session": next(
            (
                session
                for session in _list_recent_device_sessions(
                    conn,
                    user_id,
                    current_session_id=current_device_session_id,
                    limit=10,
                )
                if session and session.get("is_current")
            ),
            None,
        ),
        "recent_device_sessions": _list_recent_device_sessions(
            conn,
            user_id,
            current_session_id=current_device_session_id,
            limit=10,
        ),
        "pricing_version": POINTS_PRICE_VERSION,
        "point_cost_by_event": _get_point_cost_by_event(),
        "event_pricing_display": {k: v["display_name"] for k, v in _get_event_pricing().items()},
        "admin_notes": _list_user_admin_notes(conn, user_id, limit=50),
        "tags": _list_user_tags(conn, user_id),
        "timeline": _build_user_timeline(conn, user_id, limit=80),
    }


def _parse_int_filter(value: Any, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{field_name} must be an integer")


def _normalize_tag_key(value: str) -> str:
    normalized = "_".join(str(value or "").strip().lower().split())
    if not normalized:
        raise HTTPException(status_code=400, detail="tag_key is required")
    if len(normalized) > 64:
        raise HTTPException(status_code=400, detail="tag_key is too long")
    return normalized


def _list_admin_users(
    conn,
    *,
    query: str = "",
    include_orphaned: bool = False,
    plan_tier: str | None = None,
    status: str | None = None,
    email_verified: str | None = None,
    source_state: str | None = None,
    min_balance: int | None = None,
    max_balance: int | None = None,
    last_active_days: int | None = None,
    limit: int = 20,
    offset: int = 0,
    sort_by: str = "last_activity_at",
    sort_dir: str = "desc",
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    normalized_sort_by = sort_by if sort_by in {
        "created_at",
        "updated_at",
        "last_activity_at",
        "balance_points",
        "plan_tier",
        "status",
    } else "last_activity_at"
    normalized_sort_dir = "ASC" if str(sort_dir or "").lower() == "asc" else "DESC"
    order_sql = f"{normalized_sort_by} {normalized_sort_dir}, u.user_id DESC"

    activity_sql = """
        GREATEST(
            COALESCE(u.source_last_seen_at, '-infinity'::timestamptz),
            COALESCE(u.updated_at, '-infinity'::timestamptz),
            COALESCE(api_key_state.last_used_at, '-infinity'::timestamptz),
            COALESCE(activity.last_usage_at, '-infinity'::timestamptz),
            COALESCE(activity.last_session_at, '-infinity'::timestamptz),
            COALESCE(activity.last_run_at, '-infinity'::timestamptz),
            COALESCE(activity.last_order_at, '-infinity'::timestamptz)
        )
    """
    from_sql = f"""
        FROM app.app_user u
        LEFT JOIN app.user_credit_account a ON u.user_id = a.user_id
        LEFT JOIN LATERAL (
            SELECT MAX(last_used_at) AS last_used_at
            FROM app.user_api_key
            WHERE user_id = u.user_id
        ) api_key_state ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                (SELECT MAX(created_at) FROM app.usage_event WHERE user_id = u.user_id) AS last_usage_at,
                (SELECT MAX(updated_at) FROM app.chat_session WHERE user_id = u.user_id) AS last_session_at,
                (
                    SELECT MAX(r.updated_at)
                    FROM app.analysis_run r
                    JOIN app.chat_session s ON s.session_id = r.session_id
                    WHERE s.user_id = u.user_id
                ) AS last_run_at,
                (SELECT MAX(updated_at) FROM app.payment_order WHERE user_id = u.user_id) AS last_order_at
        ) activity ON TRUE
    """
    where_clauses: list[str] = []
    params: list[Any] = []
    if not include_orphaned:
        where_clauses.append("u.source_state <> 'orphaned'")
    if query:
        like_query = f"%{query}%"
        where_clauses.append("(u.user_id ILIKE %s OR u.email ILIKE %s OR u.display_name ILIKE %s)")
        params.extend([like_query, like_query, like_query])
    if plan_tier:
        where_clauses.append("u.plan_tier = %s")
        params.append(plan_tier)
    if status:
        where_clauses.append("u.status = %s")
        params.append(status)
    if source_state:
        where_clauses.append("u.source_state = %s")
        params.append(source_state)
    if email_verified == "verified":
        where_clauses.append("u.email_verified_at IS NOT NULL")
    elif email_verified == "unverified":
        where_clauses.append("u.email_verified_at IS NULL")
    if min_balance is not None:
        where_clauses.append("COALESCE(a.balance_points, 0) >= %s")
        params.append(min_balance)
    if max_balance is not None:
        where_clauses.append("COALESCE(a.balance_points, 0) <= %s")
        params.append(max_balance)
    if last_active_days is not None and last_active_days > 0:
        where_clauses.append(f"{activity_sql} >= NOW() - (%s::int * INTERVAL '1 day')")
        params.append(last_active_days)
    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    total_row = _fetch_optional_one(
        conn,
        f"SELECT COUNT(*) AS total {from_sql} {where_sql}",
        params,
    ) or {"total": 0}
    rows = _run_pg_dict_query(
        conn,
        f"""
        SELECT u.user_id, u.email, u.display_name, u.status, u.plan_tier,
               u.created_at, u.updated_at, u.email_verified_at,
               u.source_state, u.source_last_seen_at, u.source_orphaned_at, u.source_recovered_at,
               COALESCE(a.balance_points, 0) AS balance_points,
               api_key_state.last_used_at AS api_key_last_used_at,
               {activity_sql} AS last_activity_at,
               COALESCE(tag_state.tag_names, '') AS tag_names
        {from_sql}
        LEFT JOIN LATERAL (
            SELECT string_agg(t.display_name, ', ' ORDER BY t.display_name) AS tag_names
            FROM app.user_tag_assignment uta
            JOIN app.user_tag t ON t.tag_id = uta.tag_id
            WHERE uta.user_id = u.user_id
        ) tag_state ON TRUE
        {where_sql}
        ORDER BY {order_sql}
        LIMIT %s OFFSET %s
        """,
        [*params, limit, offset],
    )
    return {
        "users": rows,
        "page": {
            "limit": limit,
            "offset": offset,
            "total": int(total_row.get("total") or 0),
            "sort_by": normalized_sort_by,
            "sort_dir": normalized_sort_dir.lower(),
        },
        "filters": {
            "query": query,
            "include_orphaned": include_orphaned,
            "plan_tier": plan_tier,
            "status": status,
            "email_verified": email_verified,
            "source_state": source_state,
            "min_balance": min_balance,
            "max_balance": max_balance,
            "last_active_days": last_active_days,
        },
    }


def _list_user_admin_notes(conn, user_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT note_id, user_id, operator_id, note_text, created_at
        FROM app.user_admin_note
        WHERE user_id = %s
        ORDER BY created_at DESC, note_id DESC
        LIMIT %s
        """,
        [user_id, max(1, min(limit, 100))],
    )


def _create_user_admin_note(conn, *, user_id: str, operator_id: str, note_text: str) -> dict[str, Any]:
    text = str(note_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="note_text is required")
    return _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.user_admin_note (note_id, user_id, operator_id, note_text, created_at)
        VALUES (%s, %s, %s, %s, NOW())
        RETURNING note_id, user_id, operator_id, note_text, created_at
        """,
        [_generate_id("user_note"), user_id, operator_id, text],
    )[0]


def _list_all_user_tags(conn) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT tag_id, tag_key, display_name, description, created_at, updated_at
        FROM app.user_tag
        ORDER BY display_name ASC, tag_key ASC
        """,
    )


def _create_user_tag(conn, *, tag_key: str, display_name: str, description: str | None = None) -> dict[str, Any]:
    normalized_key = _normalize_tag_key(tag_key or display_name)
    normalized_name = str(display_name or normalized_key).strip() or normalized_key
    return _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.user_tag (tag_id, tag_key, display_name, description, created_at, updated_at)
        VALUES (%s, %s, %s, %s, NOW(), NOW())
        ON CONFLICT (tag_key) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            description = COALESCE(EXCLUDED.description, app.user_tag.description),
            updated_at = NOW()
        RETURNING tag_id, tag_key, display_name, description, created_at, updated_at
        """,
        [_generate_id("user_tag"), normalized_key, normalized_name, str(description or "").strip() or None],
    )[0]


def _list_user_tags(conn, user_id: str) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT t.tag_id, t.tag_key, t.display_name, t.description,
               uta.assigned_by, uta.assigned_at
        FROM app.user_tag_assignment uta
        JOIN app.user_tag t ON t.tag_id = uta.tag_id
        WHERE uta.user_id = %s
        ORDER BY t.display_name ASC, t.tag_key ASC
        """,
        [user_id],
    )


def _assign_user_tag(conn, *, user_id: str, tag_key: str, display_name: str | None, operator_id: str) -> dict[str, Any]:
    tag = _create_user_tag(
        conn,
        tag_key=tag_key,
        display_name=display_name or tag_key,
    )
    return _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.user_tag_assignment (user_id, tag_id, assigned_by, assigned_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (user_id, tag_id) DO UPDATE SET
            assigned_by = EXCLUDED.assigned_by,
            assigned_at = NOW()
        RETURNING user_id, tag_id, assigned_by, assigned_at
        """,
        [user_id, tag["tag_id"], operator_id],
    )[0] | {"tag": tag}


def _unassign_user_tag(conn, *, user_id: str, tag_id: str) -> dict[str, Any]:
    row = _fetch_optional_one(
        conn,
        """
        DELETE FROM app.user_tag_assignment
        WHERE user_id = %s AND tag_id = %s
        RETURNING user_id, tag_id, assigned_by, assigned_at
        """,
        [user_id, tag_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail="tag assignment not found")
    return row


def _build_user_timeline(conn, user_id: str, *, limit: int = 80) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT *
        FROM (
            SELECT 'user_created' AS event_type,
                   '用户注册/建档' AS title,
                   u.user_id AS detail,
                   u.created_at AS occurred_at,
                   jsonb_build_object('status', u.status, 'plan_tier', u.plan_tier, 'email_verified_at', u.email_verified_at) AS meta_json
            FROM app.app_user u
            WHERE u.user_id = %s

            UNION ALL
            SELECT 'credit_ledger' AS event_type,
                   COALESCE(l.event_type, l.entry_type) AS title,
                   CONCAT(l.points_delta, ' points · ', COALESCE(l.description, '')) AS detail,
                   l.created_at AS occurred_at,
                   jsonb_build_object('entry_id', l.entry_id, 'entry_type', l.entry_type, 'balance_after_points', l.balance_after_points, 'reference_id', l.reference_id) AS meta_json
            FROM app.credit_ledger_entry l
            WHERE l.user_id = %s

            UNION ALL
            SELECT 'payment_order' AS event_type,
                   CONCAT('订单 ', o.status) AS title,
                   CONCAT(o.package_code, ' · ', o.amount_cents, ' cents') AS detail,
                   COALESCE(o.paid_at, o.created_at) AS occurred_at,
                   jsonb_build_object('order_id', o.order_id, 'provider', o.provider, 'points_amount', o.points_amount) AS meta_json
            FROM app.payment_order o
            WHERE o.user_id = %s

            UNION ALL
            SELECT 'analysis_run' AS event_type,
                   CONCAT('分析运行 ', r.status) AS title,
                   COALESCE(r.product_query, r.analysis_goal, r.run_id) AS detail,
                   COALESCE(r.finished_at, r.started_at, r.created_at) AS occurred_at,
                   jsonb_build_object('run_id', r.run_id, 'session_id', r.session_id, 'session_title', s.title) AS meta_json
            FROM app.analysis_run r
            JOIN app.chat_session s ON s.session_id = r.session_id
            WHERE s.user_id = %s

            UNION ALL
            SELECT 'admin_audit' AS event_type,
                   CONCAT('后台操作 ', a.action) AS title,
                   a.operator_id AS detail,
                   a.created_at AS occurred_at,
                   jsonb_build_object('audit_id', a.audit_id, 'request_json', a.request_json) AS meta_json
            FROM app.admin_audit_log a
            WHERE a.target_type = 'user' AND a.target_id = %s

            UNION ALL
            SELECT 'admin_note' AS event_type,
                   '运营备注' AS title,
                   n.note_text AS detail,
                   n.created_at AS occurred_at,
                   jsonb_build_object('note_id', n.note_id, 'operator_id', n.operator_id) AS meta_json
            FROM app.user_admin_note n
            WHERE n.user_id = %s

            UNION ALL
            SELECT 'user_tag' AS event_type,
                   '标签变更' AS title,
                   t.display_name AS detail,
                   uta.assigned_at AS occurred_at,
                   jsonb_build_object('tag_id', t.tag_id, 'tag_key', t.tag_key, 'assigned_by', uta.assigned_by) AS meta_json
            FROM app.user_tag_assignment uta
            JOIN app.user_tag t ON t.tag_id = uta.tag_id
            WHERE uta.user_id = %s

            UNION ALL
            SELECT 'notification' AS event_type,
                   n.title AS title,
                   n.body AS detail,
                   n.occurred_at AS occurred_at,
                   jsonb_build_object('notification_id', n.notification_id, 'tag', n.tag, 'level', n.level, 'read_at', n.read_at) AS meta_json
            FROM app.user_notification n
            WHERE n.user_id = %s
        ) timeline
        ORDER BY occurred_at DESC NULLS LAST, event_type ASC
        LIMIT %s
        """,
        [user_id, user_id, user_id, user_id, user_id, user_id, user_id, user_id, max(1, min(limit, 200))],
    )


def _adjust_user_points_with_ledger(
    conn,
    *,
    user_id: str,
    points_delta: int,
    operator_id: str,
    reason: str,
    reference_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_reason = str(reason or "").strip()
    if not normalized_reason:
        raise HTTPException(status_code=400, detail="reason is required")
    if points_delta == 0:
        raise HTTPException(status_code=400, detail="points_delta cannot be zero")
    _ensure_credit_account(conn, user_id)
    account = _get_credit_account(conn, user_id, for_update=True)
    balance_after = int(account["balance_points"]) + int(points_delta)
    if balance_after < 0:
        raise HTTPException(status_code=400, detail="adjustment would make balance negative")
    updated_account = _run_pg_dict_query(
        conn,
        """
        UPDATE app.user_credit_account
        SET balance_points = %s,
            updated_at = NOW()
        WHERE user_id = %s
        RETURNING user_id, balance_points, reserved_points, lifetime_granted_points,
                  lifetime_purchased_points, lifetime_spent_points, created_at, updated_at
        """,
        [balance_after, user_id],
    )[0]
    ledger_entry = _create_ledger_entry(
        conn=conn,
        user_id=user_id,
        api_key_id=None,
        entry_type="admin_adjustment",
        event_type="admin_adjustment",
        units=1,
        points_delta=int(points_delta),
        balance_after_points=balance_after,
        reference_id=reference_id or f"admin_adjust:{operator_id}:{_generate_id('adjust')}",
        description=normalized_reason,
        meta_json={
            "operator_id": operator_id,
            "reason": normalized_reason,
        },
    )
    return updated_account, ledger_entry


def _build_admin_overview(conn) -> dict[str, Any]:
    _reconcile_openwebui_user_sources_for_admin(conn, scan_limit=200)
    metrics = _run_pg_dict_query(
        conn,
        """
        SELECT
            (SELECT COUNT(*) FROM app.app_user WHERE source_state <> 'orphaned') AS total_users,
            (SELECT COUNT(*) FROM app.app_user WHERE source_state = 'orphaned') AS orphaned_users,
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
