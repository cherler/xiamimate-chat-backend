"""Persistence for TikTok Shop realtime query snapshots."""
from __future__ import annotations

import uuid
from typing import Any

try:
    import psycopg2.extras
except ImportError:
    psycopg2 = None  # type: ignore[assignment]

from data_platform.chat_backend.infra.postgres import _run_pg_dict_query


def fetch_recent_tiktok_realtime_query(
    conn,
    *,
    report_run_id: str,
    query: str,
    target_market: str,
    max_age_minutes: int,
) -> dict[str, Any] | None:
    rows = _run_pg_dict_query(
        conn,
        """
        SELECT
            id, report_run_id, query, target_market, provider, request_payload,
            vendor_endpoints, vendor_response_raw, normalized_summary, result_text,
            status, latency_ms, created_at
        FROM app.report_tiktok_realtime_queries
        WHERE report_run_id = %s
          AND lower(query) = lower(%s)
          AND target_market = %s
          AND normalized_summary IS NOT NULL
          AND status IN ('ok', 'partial', 'timeout')
          AND created_at >= NOW() - (%s::text || ' minutes')::interval
        ORDER BY created_at DESC
        LIMIT 1
        """,
        [report_run_id, query, target_market, max_age_minutes],
    )
    return rows[0] if rows else None


def record_tiktok_realtime_query(
    conn,
    *,
    report_run_id: str,
    query: str,
    target_market: str,
    provider: str,
    request_payload: dict[str, Any],
    vendor_endpoints: list[dict[str, Any]],
    vendor_response_raw: dict[str, Any],
    normalized_summary: dict[str, Any],
    result_text: str,
    status: str,
    latency_ms: int,
) -> str:
    snapshot_id = str(uuid.uuid4())
    _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.report_tiktok_realtime_queries (
            id, report_run_id, query, target_market, provider, request_payload,
            vendor_endpoints, vendor_response_raw, normalized_summary, result_text,
            status, latency_ms, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING id
        """,
        [
            snapshot_id,
            report_run_id,
            query,
            target_market,
            provider,
            psycopg2.extras.Json(request_payload),
            psycopg2.extras.Json(vendor_endpoints),
            psycopg2.extras.Json(vendor_response_raw),
            psycopg2.extras.Json(normalized_summary),
            result_text,
            status,
            latency_ms,
        ],
    )
    return snapshot_id
