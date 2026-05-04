"""Persistence for Onebound 1688 realtime supplier discovery snapshots."""
from __future__ import annotations

import uuid
from typing import Any

try:
    import psycopg2.extras
except ImportError:
    psycopg2 = None  # type: ignore[assignment]

from data_platform.chat_backend.infra.postgres import _run_pg_dict_query


def fetch_recent_onebound_1688_query(
    conn,
    *,
    report_run_id: str,
    query: str,
    marketplace: str,
    max_age_minutes: int,
) -> dict[str, Any] | None:
    rows = _run_pg_dict_query(
        conn,
        """
        SELECT
            id, report_run_id, query, marketplace, provider, request_payload,
            vendor_endpoints, vendor_response_raw, normalized_summary, result_text,
            status, latency_ms, created_at
        FROM app.report_onebound_1688_realtime_queries
        WHERE report_run_id = %s
          AND lower(query) = lower(%s)
          AND marketplace = %s
          AND normalized_summary IS NOT NULL
          AND status IN ('ok', 'partial', 'timeout', 'no_result')
          AND created_at >= NOW() - (%s::text || ' minutes')::interval
        ORDER BY created_at DESC
        LIMIT 1
        """,
        [report_run_id, query, marketplace, max_age_minutes],
    )
    return rows[0] if rows else None


def record_onebound_1688_query(
    conn,
    *,
    report_run_id: str,
    query: str,
    marketplace: str,
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
        INSERT INTO app.report_onebound_1688_realtime_queries (
            id, report_run_id, query, marketplace, provider, request_payload,
            vendor_endpoints, vendor_response_raw, normalized_summary, result_text,
            status, latency_ms, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING id
        """,
        [
            snapshot_id,
            report_run_id,
            query,
            marketplace,
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


def record_onebound_1688_supplier_offers(
    conn,
    *,
    snapshot_id: str,
    report_run_id: str,
    offers: list[dict[str, Any]],
) -> None:
    for rank, offer in enumerate(offers, start=1):
        _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.report_onebound_1688_supplier_offer_results (
                id, snapshot_id, report_run_id, rank, num_iid, title, detail_url,
                pic_url, price_cny, moq, sales_30d, seller_id, shop_id,
                seller_name, shop_name, seller_info, normalized_offer, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """,
            [
                str(uuid.uuid4()),
                snapshot_id,
                report_run_id,
                rank,
                _as_text(offer.get("num_iid")),
                _as_text(offer.get("title")),
                _as_text(offer.get("detail_url")),
                _as_text(offer.get("pic_url")),
                _as_float(offer.get("price_cny")),
                _as_int(offer.get("moq")),
                _as_int(offer.get("sales_30d")),
                _as_text(offer.get("seller_id")),
                _as_text(offer.get("shop_id")),
                _as_text(offer.get("seller_name")),
                _as_text(offer.get("shop_name")),
                psycopg2.extras.Json(offer.get("seller_info") if isinstance(offer.get("seller_info"), dict) else {}),
                psycopg2.extras.Json(offer),
            ],
        )


def _as_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _as_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
