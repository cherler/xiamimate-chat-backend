"""Admin API routes — /admin/*."""
from __future__ import annotations

import secrets
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse

from data_platform.chat_backend.infra.settings import (
    POINTS_PRICE_VERSION,
    INTERNAL_SERVICE_SECRET,
    INTERNAL_SERVICE_SECRET_HEADER_NAME,
    INTERNAL_SERVICE_NAME_HEADER_NAME,
    TRUSTED_ADMIN_SERVICE_NAME,
    TRUSTED_ADMIN_SESSION_HEADER_NAME,
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
from data_platform.chat_backend.domains.identity.service import _reconcile_openwebui_user_sources_for_admin
from data_platform.chat_backend.domains.billing.service import (
    _create_redeem_code_batch,
    _disable_redeem_code,
    _grant_points_with_ledger,
    _invalidate_event_pricing_cache,
    _list_redeem_codes,
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
    AdminCreateRedeemCodeBatchRequest,
    AdminGrantPointsRequest,
    AdminKeepaJobCancelRequest,
    AdminKeepaJobPromoteRequest,
    CreateSystemNotificationBroadcastRequest,
    UpdateEventPricingRequest,
    UpdateSiteConfigRequest,
)

# Import HTML renderer from original location (will be moved in a later phase)
from data_platform.api.chat_backend_admin_html import render_admin_backoffice_html

router = APIRouter()


@router.get("/admin/backoffice")
def admin_backoffice_page(request: Request) -> HTMLResponse:
    trusted_openwebui_admin = False
    if INTERNAL_SERVICE_SECRET:
        provided_secret = (request.headers.get(INTERNAL_SERVICE_SECRET_HEADER_NAME) or "").strip()
        service_name = (request.headers.get(INTERNAL_SERVICE_NAME_HEADER_NAME) or "").strip()
        trusted_admin_verified = (request.headers.get(TRUSTED_ADMIN_SESSION_HEADER_NAME) or "").strip()
        trusted_openwebui_admin = (
            provided_secret
            and secrets.compare_digest(provided_secret, INTERNAL_SERVICE_SECRET)
            and service_name == TRUSTED_ADMIN_SERVICE_NAME
            and trusted_admin_verified == "1"
        )
    return HTMLResponse(render_admin_backoffice_html(trusted_openwebui_admin=bool(trusted_openwebui_admin)))


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
    include_orphaned = (request.query_params.get("include_orphaned") or "").strip().lower() in {"1", "true", "yes", "on"}
    raw_limit = (request.query_params.get("limit") or "20").strip()
    try:
        limit = max(1, min(int(raw_limit), 100))
    except ValueError:
        raise HTTPException(status_code=400, detail="limit must be an integer")

    with _postgres_conn() as conn:
        _reconcile_openwebui_user_sources_for_admin(conn, query=query, scan_limit=max(limit * 5, 100))
        if query:
            like_query = f"%{query}%"
            source_filter_sql = "" if include_orphaned else "AND u.source_state <> 'orphaned'"
            rows = _run_pg_dict_query(
                conn,
                f"""
                SELECT u.user_id, u.email, u.display_name, u.status, u.plan_tier,
                       u.created_at, u.updated_at, u.source_state, u.source_last_seen_at,
                       u.source_orphaned_at, u.source_recovered_at,
                       COALESCE(a.balance_points, 0) AS balance_points,
                       k.last_used_at AS api_key_last_used_at
                FROM app.app_user u
                LEFT JOIN app.user_credit_account a ON u.user_id = a.user_id
                LEFT JOIN app.user_api_key k ON u.user_id = k.user_id
                WHERE (u.user_id ILIKE %s OR u.email ILIKE %s OR u.display_name ILIKE %s)
                {source_filter_sql}
                ORDER BY u.updated_at DESC, u.user_id DESC
                LIMIT %s
                """,
                [like_query, like_query, like_query, limit],
            )
        else:
            source_filter_sql = "" if include_orphaned else "WHERE u.source_state <> 'orphaned'"
            rows = _run_pg_dict_query(
                conn,
                f"""
                SELECT u.user_id, u.email, u.display_name, u.status, u.plan_tier,
                       u.created_at, u.updated_at, u.source_state, u.source_last_seen_at,
                       u.source_orphaned_at, u.source_recovered_at,
                       COALESCE(a.balance_points, 0) AS balance_points,
                       k.last_used_at AS api_key_last_used_at
                FROM app.app_user u
                LEFT JOIN app.user_credit_account a ON u.user_id = a.user_id
                LEFT JOIN app.user_api_key k ON u.user_id = k.user_id
                {source_filter_sql}
                ORDER BY u.updated_at DESC, u.user_id DESC
                LIMIT %s
                """,
                [limit],
            )
    return _success_response(
        "/admin/api/users",
        {"query": query, "include_orphaned": include_orphaned, "users": rows},
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


@router.get("/admin/api/redeem-codes")
def admin_list_redeem_codes(request: Request) -> dict[str, Any]:
    _require_admin_operator(request)
    raw_limit = (request.query_params.get("limit") or "50").strip()
    raw_offset = (request.query_params.get("offset") or "0").strip()
    raw_batch_limit = (request.query_params.get("batch_limit") or "20").strip()
    raw_batch_offset = (request.query_params.get("batch_offset") or "0").strip()
    raw_selected_batch_offset = (request.query_params.get("selected_batch_offset") or "0").strip()
    status = (request.query_params.get("status") or "").strip().lower() or None
    batch_id = (request.query_params.get("batch_id") or "").strip() or None
    batch_keyword = (request.query_params.get("batch_keyword") or "").strip() or None
    include_plain_codes = (request.query_params.get("include_plain_codes") or "").strip().lower() in {"1", "true", "yes"}
    try:
        limit = max(1, min(int(raw_limit), 200))
        offset = max(0, int(raw_offset))
        batch_limit = max(1, min(int(raw_batch_limit), 100))
        batch_offset = max(0, int(raw_batch_offset))
        selected_batch_offset = max(0, int(raw_selected_batch_offset))
    except ValueError:
        raise HTTPException(status_code=400, detail="limit, offset, batch_limit, batch_offset and selected_batch_offset must be integers")

    with _postgres_conn() as conn:
        result = _list_redeem_codes(
            conn,
            limit=limit,
            offset=offset,
            batch_limit=batch_limit,
            batch_offset=batch_offset,
            status=status,
            batch_id=batch_id,
            batch_keyword=batch_keyword,
            selected_batch_offset=selected_batch_offset,
            include_plain_codes=include_plain_codes,
        )
    return _success_response(
        "/admin/api/redeem-codes",
        result,
        "redeem codes loaded",
    )


@router.post("/admin/api/redeem-codes/batches")
def admin_create_redeem_code_batch(
    request: Request,
    payload: AdminCreateRedeemCodeBatchRequest,
) -> dict[str, Any]:
    operator_id = _require_admin_operator(request)
    with _postgres_conn() as conn:
        result = _create_redeem_code_batch(
            conn,
            operator_id=operator_id,
            points=payload.points,
            code_count=payload.code_count,
            code_type=payload.code_type,
            batch_name=payload.batch_name,
            note=payload.note,
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            meta_json=payload.meta,
        )
        audit_log = _audit_admin_action(
            conn,
            operator_id=operator_id,
            action="create_redeem_code_batch",
            target_type="redeem_code_batch",
            target_id=str((result.get("batch") or {}).get("batch_id") or "") or None,
            request_json=jsonable_encoder(payload),
            result_json={
                "batch": result.get("batch") or {},
                "generated_code_count": len(result.get("codes") or []),
            },
        )
    return _success_response(
        "/admin/api/redeem-codes/batches",
        {
            **result,
            "audit_log": audit_log,
        },
        "redeem code batch created",
    )


@router.post("/admin/api/redeem-codes/{code_id}/disable")
def admin_disable_redeem_code(code_id: str, request: Request) -> dict[str, Any]:
    operator_id = _require_admin_operator(request)
    with _postgres_conn() as conn:
        redeem_code = _disable_redeem_code(conn, code_id=code_id)
        audit_log = _audit_admin_action(
            conn,
            operator_id=operator_id,
            action="disable_redeem_code",
            target_type="redeem_code",
            target_id=code_id,
            request_json={"code_id": code_id},
            result_json={"redeem_code": redeem_code},
        )
    return _success_response(
        f"/admin/api/redeem-codes/{code_id}/disable",
        {"redeem_code": redeem_code, "audit_log": audit_log},
        "redeem code disabled",
    )


@router.get("/admin/api/keepa-operations")
def admin_keepa_operations(request: Request) -> dict[str, Any]:
    _require_admin_operator(request)
    raw_limit = (request.query_params.get("limit") or "30").strip()
    try:
        limit = max(1, min(int(raw_limit), 100))
    except ValueError:
        raise HTTPException(status_code=400, detail="limit must be an integer")

    with _postgres_conn() as conn:
        table_rows = _run_pg_dict_query(
            conn,
            """
            SELECT
                to_regclass('sync.keepa_candidate_expansion_jobs')::text AS jobs_table,
                to_regclass('sync.keepa_token_ledger')::text AS ledger_table,
                to_regclass('sync.keepa_token_budget_policy')::text AS policy_table
            """,
        )
        table_state = table_rows[0] if table_rows else {}
        has_jobs = bool(table_state.get("jobs_table"))
        has_ledger = bool(table_state.get("ledger_table"))
        has_policy = bool(table_state.get("policy_table"))

        status_counts = []
        recent_jobs = []
        if has_jobs:
            status_counts = _run_pg_dict_query(
                conn,
                """
                SELECT status, COUNT(*) AS job_count
                FROM sync.keepa_candidate_expansion_jobs
                GROUP BY status
                ORDER BY job_count DESC, status ASC
                """,
            )
            recent_jobs = _run_pg_dict_query(
                conn,
                """
                SELECT job_id, marketplace, domain, source, priority, product_query, recall_mode,
                       category_id, category_path, target_asin_count, min_pool_size, status,
                       status_reason, tokens_estimated, tokens_reserved, tokens_consumed,
                       token_wait_until, result_new_asin_count, error_message,
                       created_at, updated_at, started_at, finished_at
                FROM sync.keepa_candidate_expansion_jobs
                ORDER BY updated_at DESC NULLS LAST, created_at DESC
                LIMIT %s
                """,
                [limit],
            )

        token_latest = None
        recent_token_ledger = []
        token_24h = []
        if has_ledger:
            latest_rows = _run_pg_dict_query(
                conn,
                """
                SELECT ledger_id, job_id, domain, source, queue_name, action, tokens_before,
                       tokens_delta, tokens_after, keepa_refill_in_ms, status, message, created_at
                FROM sync.keepa_token_ledger
                ORDER BY created_at DESC, ledger_id DESC
                LIMIT 1
                """,
            )
            token_latest = latest_rows[0] if latest_rows else None
            recent_token_ledger = _run_pg_dict_query(
                conn,
                """
                SELECT ledger_id, job_id, domain, source, queue_name, action, tokens_before,
                       tokens_delta, tokens_after, keepa_refill_in_ms, status, message, created_at
                FROM sync.keepa_token_ledger
                ORDER BY created_at DESC, ledger_id DESC
                LIMIT %s
                """,
                [limit],
            )
            token_24h = _run_pg_dict_query(
                conn,
                """
                SELECT queue_name,
                       SUM(CASE WHEN tokens_delta < 0 THEN -tokens_delta ELSE 0 END) AS tokens_consumed_24h,
                       COUNT(*) AS event_count
                FROM sync.keepa_token_ledger
                WHERE created_at >= NOW() - INTERVAL '24 hours'
                GROUP BY queue_name
                ORDER BY tokens_consumed_24h DESC NULLS LAST, queue_name ASC
                """,
            )

        token_budget_policy = []
        if has_policy:
            token_budget_policy = _run_pg_dict_query(
                conn,
                """
                SELECT policy_name, enabled, interactive_min_tokens, bestseller_min_tokens,
                       search_min_tokens, history_min_tokens, safe_reserve_tokens,
                       pause_history_when_interactive_pending, max_history_tokens_per_run,
                       updated_at, notes
                FROM sync.keepa_token_budget_policy
                ORDER BY policy_name ASC
                """,
            )

    return _success_response(
        "/admin/api/keepa-operations",
        {
            "table_state": table_state,
            "status_counts": status_counts,
            "recent_jobs": recent_jobs,
            "token_latest": token_latest,
            "token_24h": token_24h,
            "recent_token_ledger": recent_token_ledger,
            "token_budget_policy": token_budget_policy,
        },
        "keepa operations loaded",
    )


@router.post("/admin/api/keepa-operations/jobs/{job_id}/promote")
def admin_promote_keepa_job(
    job_id: str,
    request: Request,
    payload: AdminKeepaJobPromoteRequest,
) -> dict[str, Any]:
    operator_id = _require_admin_operator(request)
    reason = (payload.reason or "admin promote").strip() or "admin promote"
    with _postgres_conn() as conn:
        table_rows = _run_pg_dict_query(
            conn,
            "SELECT to_regclass('sync.keepa_candidate_expansion_jobs')::text AS jobs_table",
        )
        if not table_rows or not table_rows[0].get("jobs_table"):
            raise HTTPException(status_code=503, detail="keepa expansion job table is unavailable")
        rows = _run_pg_dict_query(
            conn,
            """
            SELECT job_id, status, priority
            FROM sync.keepa_candidate_expansion_jobs
            WHERE job_id = %s
            """,
            [job_id],
        )
        if not rows:
            raise HTTPException(status_code=404, detail="keepa expansion job not found")
        before = rows[0]
        if before.get("status") in {"completed", "failed", "cancelled"}:
            raise HTTPException(status_code=409, detail=f"cannot promote terminal job status: {before.get('status')}")
        updated_rows = _run_pg_dict_query(
            conn,
            """
            UPDATE sync.keepa_candidate_expansion_jobs
            SET priority = %s,
                status_reason = %s,
                updated_at = NOW(),
                meta_json = COALESCE(meta_json, '{}'::JSONB) || jsonb_build_object(
                    'admin_promoted_at', NOW(),
                    'admin_promoted_by', %s,
                    'admin_promote_reason', %s,
                    'admin_previous_priority', %s
                )
            WHERE job_id = %s
            RETURNING job_id, marketplace, domain, source, priority, product_query, recall_mode,
                      category_id, category_path, target_asin_count, status, status_reason,
                      tokens_estimated, tokens_reserved, tokens_consumed, result_new_asin_count,
                      created_at, updated_at, started_at, finished_at
            """,
            [payload.priority, reason, operator_id, reason, before.get("priority"), job_id],
        )
        _run_pg_dict_query(
            conn,
            """
            INSERT INTO sync.keepa_token_ledger (
                job_id, domain, source, queue_name, action, tokens_before,
                tokens_delta, tokens_after, status, message, meta_json
            )
            SELECT job_id, domain, source,
                   CASE WHEN %s LIKE 'interactive%%' THEN 'interactive' ELSE 'background' END,
                   'promote', NULL, 0, NULL, 'recorded', %s,
                   %s::JSONB
            FROM sync.keepa_candidate_expansion_jobs
            WHERE job_id = %s
                 RETURNING ledger_id
            """,
            [
                payload.priority,
                reason,
                json.dumps(jsonable_encoder({"operator_id": operator_id, "priority": payload.priority}), ensure_ascii=False),
                job_id,
            ],
        )
        audit_log = _audit_admin_action(
            conn,
            operator_id=operator_id,
            action="promote_keepa_expansion_job",
            target_type="keepa_candidate_expansion_job",
            target_id=job_id,
            request_json=jsonable_encoder(payload),
            result_json={"before": before, "job": updated_rows[0] if updated_rows else None},
        )
        conn.commit()
    return _success_response(
        f"/admin/api/keepa-operations/jobs/{job_id}/promote",
        {"job": updated_rows[0] if updated_rows else None, "audit_log": audit_log},
        "keepa expansion job promoted",
    )


@router.post("/admin/api/keepa-operations/jobs/{job_id}/cancel")
def admin_cancel_keepa_job(
    job_id: str,
    request: Request,
    payload: AdminKeepaJobCancelRequest,
) -> dict[str, Any]:
    operator_id = _require_admin_operator(request)
    reason = (payload.reason or "admin cancel").strip() or "admin cancel"
    with _postgres_conn() as conn:
        table_rows = _run_pg_dict_query(
            conn,
            "SELECT to_regclass('sync.keepa_candidate_expansion_jobs')::text AS jobs_table",
        )
        if not table_rows or not table_rows[0].get("jobs_table"):
            raise HTTPException(status_code=503, detail="keepa expansion job table is unavailable")
        rows = _run_pg_dict_query(
            conn,
            """
            SELECT job_id, status, priority
            FROM sync.keepa_candidate_expansion_jobs
            WHERE job_id = %s
            """,
            [job_id],
        )
        if not rows:
            raise HTTPException(status_code=404, detail="keepa expansion job not found")
        before = rows[0]
        if before.get("status") in {"completed", "failed", "cancelled"}:
            raise HTTPException(status_code=409, detail=f"cannot cancel terminal job status: {before.get('status')}")
        updated_rows = _run_pg_dict_query(
            conn,
            """
            UPDATE sync.keepa_candidate_expansion_jobs
            SET status = 'cancelled',
                status_reason = %s,
                error_message = NULL,
                updated_at = NOW(),
                finished_at = NOW(),
                meta_json = COALESCE(meta_json, '{}'::JSONB) || jsonb_build_object(
                    'admin_cancelled_at', NOW(),
                    'admin_cancelled_by', %s,
                    'admin_cancel_reason', %s,
                    'admin_previous_status', %s
                )
            WHERE job_id = %s
            RETURNING job_id, marketplace, domain, source, priority, product_query, recall_mode,
                      category_id, category_path, target_asin_count, status, status_reason,
                      tokens_estimated, tokens_reserved, tokens_consumed, result_new_asin_count,
                      created_at, updated_at, started_at, finished_at
            """,
            [reason, operator_id, reason, before.get("status"), job_id],
        )
        _run_pg_dict_query(
            conn,
            """
            INSERT INTO sync.keepa_token_ledger (
                job_id, domain, source, queue_name, action, tokens_before,
                tokens_delta, tokens_after, status, message, meta_json
            )
            SELECT job_id, domain, source,
                   CASE WHEN priority LIKE 'interactive%%' THEN 'interactive' ELSE 'background' END,
                   'cancel', NULL, 0, NULL, 'recorded', %s,
                   %s::JSONB
            FROM sync.keepa_candidate_expansion_jobs
            WHERE job_id = %s
                 RETURNING ledger_id
            """,
            [
                reason,
                json.dumps(jsonable_encoder({"operator_id": operator_id, "previous_status": before.get("status")}), ensure_ascii=False),
                job_id,
            ],
        )
        audit_log = _audit_admin_action(
            conn,
            operator_id=operator_id,
            action="cancel_keepa_expansion_job",
            target_type="keepa_candidate_expansion_job",
            target_id=job_id,
            request_json=jsonable_encoder(payload),
            result_json={"before": before, "job": updated_rows[0] if updated_rows else None},
        )
        conn.commit()
    return _success_response(
        f"/admin/api/keepa-operations/jobs/{job_id}/cancel",
        {"job": updated_rows[0] if updated_rows else None, "audit_log": audit_log},
        "keepa expansion job cancelled",
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
