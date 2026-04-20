"""Admin API routes — /admin/*."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse

from data_platform.chat_backend.infra.settings import (
    POINTS_PRICE_VERSION,
    _generate_id,
)
from data_platform.chat_backend.infra.postgres import (
    _postgres_conn,
    _run_pg_dict_query,
)
from data_platform.chat_backend.infra.http import (
    _require_admin_operator,
    _success_response,
)
from data_platform.chat_backend.domains.identity.service import _ensure_user_record
from data_platform.chat_backend.domains.billing.service import (
    _grant_points_with_ledger,
    _invalidate_event_pricing_cache,
)
from data_platform.chat_backend.domains.admin.service import (
    _audit_admin_action,
    _build_admin_overview,
    _build_user_account_overview,
)
from data_platform.chat_backend.domains.notifications.service import (
    _create_system_notification_broadcast,
    _fanout_system_notification_broadcast,
    _list_system_notification_broadcasts,
)
from data_platform.chat_backend.domains.site_config import (
    _list_site_config,
    _update_site_config,
    _invalidate_site_config_cache,
)
from data_platform.chat_backend.api.models import (
    AdminGrantPointsRequest,
    CreateSystemNotificationBroadcastRequest,
    UpdateEventPricingRequest,
    UpdateSiteConfigRequest,
)

# Import HTML renderer from original location (will be moved in a later phase)
from data_platform.api.chat_backend_admin_html import render_admin_backoffice_html

router = APIRouter()


@router.get("/admin/backoffice")
def admin_backoffice_page() -> HTMLResponse:
    return HTMLResponse(render_admin_backoffice_html())


@router.get("/admin/api/overview")
def admin_backoffice_overview(request: Request) -> dict[str, Any]:
    _require_admin_operator(request)
    with _postgres_conn() as conn:
        overview = _build_admin_overview(conn)
    return _success_response(
        "/admin/api/overview",
        overview,
        "admin overview loaded",
    )


@router.get("/admin/api/users")
def admin_backoffice_users(request: Request) -> dict[str, Any]:
    _require_admin_operator(request)
    query = (request.query_params.get("query") or "").strip()
    raw_limit = (request.query_params.get("limit") or "20").strip()
    try:
        limit = max(1, min(int(raw_limit), 100))
    except ValueError:
        raise HTTPException(status_code=400, detail="limit must be an integer")

    with _postgres_conn() as conn:
        if query:
            like_query = f"%{query}%"
            rows = _run_pg_dict_query(
                conn,
                """
                SELECT u.user_id, u.email, u.display_name, u.status, u.plan_tier,
                       u.created_at, u.updated_at,
                       COALESCE(a.balance_points, 0) AS balance_points,
                       k.last_used_at AS api_key_last_used_at
                FROM app.app_user u
                LEFT JOIN app.user_credit_account a ON u.user_id = a.user_id
                LEFT JOIN app.user_api_key k ON u.user_id = k.user_id
                WHERE u.user_id ILIKE %s OR u.email ILIKE %s OR u.display_name ILIKE %s
                ORDER BY u.updated_at DESC, u.user_id DESC
                LIMIT %s
                """,
                [like_query, like_query, like_query, limit],
            )
        else:
            rows = _run_pg_dict_query(
                conn,
                """
                SELECT u.user_id, u.email, u.display_name, u.status, u.plan_tier,
                       u.created_at, u.updated_at,
                       COALESCE(a.balance_points, 0) AS balance_points,
                       k.last_used_at AS api_key_last_used_at
                FROM app.app_user u
                LEFT JOIN app.user_credit_account a ON u.user_id = a.user_id
                LEFT JOIN app.user_api_key k ON u.user_id = k.user_id
                ORDER BY u.updated_at DESC, u.user_id DESC
                LIMIT %s
                """,
                [limit],
            )
    return _success_response(
        "/admin/api/users",
        {"query": query, "users": rows},
        "admin users loaded",
    )


@router.get("/admin/api/users/{user_id}")
def admin_backoffice_user_detail(user_id: str, request: Request) -> dict[str, Any]:
    _require_admin_operator(request)
    with _postgres_conn() as conn:
        overview = _build_user_account_overview(
            conn,
            user_id,
            ledger_limit=50,
            usage_limit=50,
            order_limit=20,
            session_limit=20,
            run_limit=20,
        )
    return _success_response(
        f"/admin/api/users/{user_id}",
        overview,
        "admin user detail loaded",
    )


@router.post("/admin/api/users/{user_id}/grant-points")
def admin_backoffice_grant_points(user_id: str, request: Request, payload: AdminGrantPointsRequest) -> dict[str, Any]:
    operator_id = _require_admin_operator(request)
    with _postgres_conn() as conn:
        user = _ensure_user_record(conn, user_id=user_id)
        reference_id = payload.reference_id or f"admin:{operator_id}:{_generate_id('grant')}"
        updated_account, ledger_entry = _grant_points_with_ledger(
            conn=conn,
            user_id=user.user_id,
            points=payload.points,
            entry_type=payload.entry_type,
            event_type=payload.entry_type,
            reference_id=reference_id,
            description=payload.description or f"admin grant by {operator_id}",
            meta_json={
                **payload.meta,
                "operator_id": operator_id,
            },
            granted_points=payload.points,
        )
        audit_log = _audit_admin_action(
            conn,
            operator_id=operator_id,
            action="grant_points",
            target_type="user",
            target_id=user.user_id,
            request_json={
                "payload": jsonable_encoder(payload),
                "reference_id": reference_id,
            },
            result_json={
                "points_account": updated_account,
                "ledger_entry": ledger_entry,
            },
        )
    return _success_response(
        f"/admin/api/users/{user_id}/grant-points",
        {
            "points_account": updated_account,
            "ledger_entry": ledger_entry,
            "audit_log": audit_log,
        },
        "admin points granted",
    )


@router.get("/admin/api/audit-logs")
def admin_backoffice_audit_logs(request: Request) -> dict[str, Any]:
    _require_admin_operator(request)
    raw_limit = (request.query_params.get("limit") or "50").strip()
    try:
        limit = max(1, min(int(raw_limit), 200))
    except ValueError:
        raise HTTPException(status_code=400, detail="limit must be an integer")
    target_id = (request.query_params.get("target_id") or "").strip()

    with _postgres_conn() as conn:
        if target_id:
            rows = _run_pg_dict_query(
                conn,
                """
                SELECT audit_id, operator_id, action, target_type, target_id, request_json, result_json, created_at
                FROM app.admin_audit_log
                WHERE target_id = %s
                ORDER BY created_at DESC, audit_id DESC
                LIMIT %s
                """,
                [target_id, limit],
            )
        else:
            rows = _run_pg_dict_query(
                conn,
                """
                SELECT audit_id, operator_id, action, target_type, target_id, request_json, result_json, created_at
                FROM app.admin_audit_log
                ORDER BY created_at DESC, audit_id DESC
                LIMIT %s
                """,
                [limit],
            )
    return _success_response(
        "/admin/api/audit-logs",
        {"target_id": target_id or None, "audit_logs": rows},
        "admin audit logs loaded",
    )


@router.get("/admin/api/system-notifications")
def admin_list_system_notifications(request: Request) -> dict[str, Any]:
    _require_admin_operator(request)
    raw_limit = (request.query_params.get("limit") or "50").strip()
    try:
        limit = max(1, min(int(raw_limit), 100))
    except ValueError:
        raise HTTPException(status_code=400, detail="limit must be an integer")

    with _postgres_conn() as conn:
        rows = _list_system_notification_broadcasts(conn, limit=limit)
    return _success_response(
        "/admin/api/system-notifications",
        {"system_notifications": rows},
        "system notifications loaded",
    )


@router.post("/admin/api/system-notifications")
def admin_create_system_notification(
    request: Request,
    payload: CreateSystemNotificationBroadcastRequest,
) -> dict[str, Any]:
    operator_id = _require_admin_operator(request)
    with _postgres_conn() as conn:
        broadcast = _create_system_notification_broadcast(
            conn,
            operator_id=operator_id,
            title=payload.title,
            body=payload.body,
            tag=payload.tag,
            level=payload.level,
            action_url=payload.action_url,
        )
        broadcast = _fanout_system_notification_broadcast(conn, broadcast)
        audit_log = _audit_admin_action(
            conn,
            operator_id=operator_id,
            action="broadcast_system_notification",
            target_type="system_notification_broadcast",
            target_id=str(broadcast.get("broadcast_id") or "") or None,
            request_json=jsonable_encoder(payload),
            result_json=broadcast,
        )
    return _success_response(
        "/admin/api/system-notifications",
        {"broadcast": broadcast, "audit_log": audit_log},
        "system notification broadcast created",
    )


@router.get("/admin/api/pricing")
def admin_list_event_pricing(request: Request) -> dict[str, Any]:
    _require_admin_operator(request)
    with _postgres_conn() as conn:
        rows = _run_pg_dict_query(
            conn,
            """
            SELECT event_type, display_name, points_per_unit, status, display_order, created_at, updated_at
            FROM app.billing_event_pricing
            ORDER BY display_order ASC, event_type ASC
            """,
        )
    return _success_response(
        "/admin/api/pricing",
        {"pricing_version": POINTS_PRICE_VERSION, "event_pricing": rows},
        "event pricing loaded",
    )


@router.put("/admin/api/pricing/{event_type}")
def admin_update_event_pricing(event_type: str, request: Request, payload: UpdateEventPricingRequest) -> dict[str, Any]:
    operator_id = _require_admin_operator(request)
    updates: list[str] = []
    params: list[Any] = []
    if payload.display_name is not None:
        updates.append("display_name = %s")
        params.append(payload.display_name)
    if payload.points_per_unit is not None:
        if payload.points_per_unit < 0:
            raise HTTPException(status_code=400, detail="points_per_unit must be >= 0")
        updates.append("points_per_unit = %s")
        params.append(payload.points_per_unit)
    if payload.status is not None:
        if payload.status not in {"active", "disabled"}:
            raise HTTPException(status_code=400, detail="status must be active or disabled")
        updates.append("status = %s")
        params.append(payload.status)
    if payload.display_order is not None:
        updates.append("display_order = %s")
        params.append(payload.display_order)
    if not updates:
        raise HTTPException(status_code=400, detail="no fields to update")

    updates.append("updated_at = NOW()")
    params.append(event_type)
    with _postgres_conn() as conn:
        rows = _run_pg_dict_query(
            conn,
            f"""
            UPDATE app.billing_event_pricing
            SET {', '.join(updates)}
            WHERE event_type = %s
            RETURNING event_type, display_name, points_per_unit, status, display_order, created_at, updated_at
            """,
            params,
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"event_type not found: {event_type}")
        _audit_admin_action(
            conn,
            operator_id=operator_id,
            action="update_event_pricing",
            target_type="billing_event_pricing",
            target_id=event_type,
            request_json=jsonable_encoder(payload),
            result_json=rows[0],
        )
    _invalidate_event_pricing_cache()
    return _success_response(
        f"/admin/api/pricing/{event_type}",
        {"event_pricing": rows[0]},
        "event pricing updated",
    )


@router.get("/admin/api/site-config")
def admin_list_site_config(request: Request) -> dict[str, Any]:
    _require_admin_operator(request)
    with _postgres_conn() as conn:
        rows = _list_site_config(conn)
    return _success_response(
        "/admin/api/site-config",
        {"site_config": rows},
        "site config loaded",
    )


@router.put("/admin/api/site-config/{config_key}")
def admin_update_site_config(config_key: str, request: Request, payload: UpdateSiteConfigRequest) -> dict[str, Any]:
    operator_id = _require_admin_operator(request)
    with _postgres_conn() as conn:
        updated = _update_site_config(conn, config_key, payload.config_value)
        if not updated:
            raise HTTPException(status_code=404, detail=f"config_key not found: {config_key}")
        _audit_admin_action(
            conn,
            operator_id=operator_id,
            action="update_site_config",
            target_type="site_config",
            target_id=config_key,
            request_json={"config_value": payload.config_value[:200] if len(payload.config_value) > 200 else payload.config_value},
            result_json={"config_key": updated["config_key"], "display_name": updated["display_name"], "updated_at": str(updated["updated_at"])},
        )
    return _success_response(
        f"/admin/api/site-config/{config_key}",
        {"site_config": updated},
        "site config updated",
    )
