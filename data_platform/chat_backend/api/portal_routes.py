"""Portal API routes — /portal/*."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from data_platform.chat_backend.infra.postgres import (
    _fetch_optional_one,
    _postgres_conn,
    _run_pg_dict_query,
)
from data_platform.chat_backend.infra.http import _success_response
from data_platform.chat_backend.domains.portal.service import _require_portal_user
from data_platform.chat_backend.domains.admin.service import _build_user_account_overview

# Import HTML renderer from original location (will be moved in a later phase)
from data_platform.api.chat_backend_portal_html import render_portal_html

router = APIRouter()


@router.get("/portal")
def portal_page() -> HTMLResponse:
    return HTMLResponse(render_portal_html())


@router.get("/portal/api/account")
def portal_get_account(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        overview = _build_user_account_overview(conn, user_id, ledger_limit=50, usage_limit=50)
    return _success_response("/portal/api/account", overview, "account loaded")


@router.get("/portal/api/ledger")
def portal_get_ledger(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    page = max(1, int(request.query_params.get("page", "1")))
    page_size = min(100, max(1, int(request.query_params.get("page_size", "30"))))
    offset = (page - 1) * page_size
    with _postgres_conn() as conn:
        rows = _run_pg_dict_query(
            conn,
            """
            SELECT entry_id, entry_type, event_type, units, points_delta, balance_after_points,
                   description, created_at
            FROM app.credit_ledger_entry
            WHERE user_id = %s
            ORDER BY created_at DESC, entry_id DESC
            LIMIT %s OFFSET %s
            """,
            [user_id, page_size, offset],
        )
        total_row = _fetch_optional_one(
            conn,
            "SELECT COUNT(*) AS cnt FROM app.credit_ledger_entry WHERE user_id = %s",
            [user_id],
        )
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
