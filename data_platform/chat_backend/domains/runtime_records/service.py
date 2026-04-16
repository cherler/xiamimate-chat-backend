"""Runtime records domain — session, message, and run helpers."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from data_platform.chat_backend.infra.postgres import _run_pg_dict_query


def _fetch_session_for_user(conn, session_id: str, user_id: str) -> dict[str, Any]:
    rows = _run_pg_dict_query(
        conn,
        """
        SELECT session_id, user_id, title, target_platform, target_market, validation_marketplace,
               status, created_at, updated_at, closed_at
        FROM app.chat_session
        WHERE session_id = %s AND user_id = %s
        LIMIT 1
        """,
        [session_id, user_id],
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"chat session not found: {session_id}")
    return rows[0]


def _fetch_run_for_user(conn, run_id: str, user_id: str) -> dict[str, Any]:
    rows = _run_pg_dict_query(
        conn,
        """
        SELECT
            r.run_id,
            r.session_id,
            r.message_id,
            r.product_query,
            r.analysis_goal,
            r.input_payload_json,
            r.status,
            r.dify_run_id,
            r.final_answer_text,
            r.started_at,
            r.finished_at,
            r.created_at,
            r.updated_at
        FROM app.analysis_run r
        JOIN app.chat_session s ON r.session_id = s.session_id
        WHERE r.run_id = %s AND s.user_id = %s
        LIMIT 1
        """,
        [run_id, user_id],
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"analysis run not found: {run_id}")
    return rows[0]


def _require_active_session(session_row: dict[str, Any]) -> None:
    if session_row["status"] != "active":
        raise HTTPException(status_code=409, detail=f"chat session is not active: {session_row['session_id']}")
