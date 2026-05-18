"""Payments domain — service functions."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

try:
    import psycopg2.extras
except ImportError:
    pass

from data_platform.chat_backend.infra.postgres import _fetch_optional_one, _run_pg_dict_query
from data_platform.chat_backend.infra.settings import _generate_id


def _fetch_payment_order(conn, order_id: str) -> dict[str, Any]:
    row = _fetch_optional_one(
        conn,
        """
     SELECT order_id, user_id, package_code, product_type, provider, list_amount_cents,
         discount_amount_cents, amount_cents, points_amount, status,
         provider_order_id, provider_trade_no, promotion_snapshot_json,
         callback_payload_json, paid_at, created_at, updated_at
        FROM app.payment_order
        WHERE order_id = %s
        LIMIT 1
        """,
        [order_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"payment order not found: {order_id}")
    return row


def _fetch_payment_order_for_user(conn, order_id: str, user_id: str) -> dict[str, Any]:
    row = _fetch_optional_one(
        conn,
        """
     SELECT order_id, user_id, package_code, product_type, provider, list_amount_cents,
         discount_amount_cents, amount_cents, points_amount, status,
         provider_order_id, provider_trade_no, promotion_snapshot_json,
         callback_payload_json, paid_at, created_at, updated_at
        FROM app.payment_order
        WHERE order_id = %s AND user_id = %s
        LIMIT 1
        """,
        [order_id, user_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"payment order not found: {order_id}")
    return row


def _fetch_latest_payment_session(conn, order_id: str) -> dict[str, Any] | None:
    return _fetch_optional_one(
        conn,
        """
        SELECT session_id, order_id, user_id, provider, channel, status,
               provider_order_id, provider_trade_no, cashier_url, qr_code_url,
               prepay_payload_json, expires_at, paid_at, created_at, updated_at
        FROM app.payment_session
        WHERE order_id = %s
        ORDER BY created_at DESC, session_id DESC
        LIMIT 1
        """,
        [order_id],
    )


def _fetch_payment_session(conn, session_id: str) -> dict[str, Any]:
    row = _fetch_optional_one(
        conn,
        """
        SELECT session_id, order_id, user_id, provider, channel, status,
               provider_order_id, provider_trade_no, cashier_url, qr_code_url,
               prepay_payload_json, expires_at, paid_at, created_at, updated_at
        FROM app.payment_session
        WHERE session_id = %s
        LIMIT 1
        """,
        [session_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"payment session not found: {session_id}")
    return row


def _create_payment_session(
    conn,
    *,
    order_row: dict[str, Any],
    provider: str,
    channel: str,
    status: str,
    provider_order_id: str | None = None,
    provider_trade_no: str | None = None,
    cashier_url: str | None = None,
    qr_code_url: str | None = None,
    prepay_payload_json: dict[str, Any] | None = None,
    expires_at: Any | None = None,
) -> dict[str, Any]:
    return _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.payment_session (
            session_id, order_id, user_id, provider, channel, status,
            provider_order_id, provider_trade_no, cashier_url, qr_code_url,
            prepay_payload_json, expires_at, paid_at, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NOW(), NOW())
        RETURNING session_id, order_id, user_id, provider, channel, status,
                  provider_order_id, provider_trade_no, cashier_url, qr_code_url,
                  prepay_payload_json, expires_at, paid_at, created_at, updated_at
        """,
        [
            _generate_id("pay_sess"),
            order_row["order_id"],
            order_row["user_id"],
            provider,
            channel,
            status,
            provider_order_id,
            provider_trade_no,
            cashier_url,
            qr_code_url,
            psycopg2.extras.Json(prepay_payload_json or {}),
            expires_at,
        ],
    )[0]


def _update_payment_session_status(
    conn,
    *,
    session_id: str,
    status: str,
    provider_trade_no: str | None = None,
    prepay_payload_json: dict[str, Any] | None = None,
    paid_at: Any | None = None,
) -> dict[str, Any]:
    return _run_pg_dict_query(
        conn,
        """
        UPDATE app.payment_session
        SET status = %s,
            provider_trade_no = COALESCE(%s, provider_trade_no),
            prepay_payload_json = CASE WHEN %s::jsonb IS NULL THEN prepay_payload_json ELSE %s::jsonb END,
            paid_at = COALESCE(%s, paid_at),
            updated_at = NOW()
        WHERE session_id = %s
        RETURNING session_id, order_id, user_id, provider, channel, status,
                  provider_order_id, provider_trade_no, cashier_url, qr_code_url,
                  prepay_payload_json, expires_at, paid_at, created_at, updated_at
        """,
        [
            status,
            provider_trade_no,
            psycopg2.extras.Json(prepay_payload_json) if prepay_payload_json is not None else None,
            psycopg2.extras.Json(prepay_payload_json) if prepay_payload_json is not None else None,
            paid_at,
            session_id,
        ],
    )[0]


def _insert_payment_callback_event(
    conn,
    *,
    provider: str,
    payload_json: dict[str, Any],
    signature_verified: bool,
    processed_status: str,
    order_id: str | None = None,
    provider_order_id: str | None = None,
    provider_trade_no: str | None = None,
    event_type: str | None = None,
    processed_at: Any | None = None,
) -> dict[str, Any]:
    return _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.payment_callback_event (
            event_id, provider, order_id, provider_order_id, provider_trade_no,
            event_type, signature_verified, payload_json, processed_status,
            processed_at, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING event_id, provider, order_id, provider_order_id, provider_trade_no,
                  event_type, signature_verified, payload_json, processed_status,
                  processed_at, created_at
        """,
        [
            _generate_id("pay_evt"),
            provider,
            order_id,
            provider_order_id,
            provider_trade_no,
            event_type,
            signature_verified,
            psycopg2.extras.Json(payload_json),
            processed_status,
            processed_at,
        ],
    )[0]


def _expire_pending_payment_sessions(conn) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        UPDATE app.payment_session
        SET status = 'expired',
            updated_at = NOW()
        WHERE status = 'pending'
          AND expires_at IS NOT NULL
          AND expires_at <= NOW()
        RETURNING session_id, order_id, user_id, provider, channel, status,
                  provider_order_id, provider_trade_no, cashier_url, qr_code_url,
                  prepay_payload_json, expires_at, paid_at, created_at, updated_at
        """,
    )


def _close_stale_pending_payment_orders(conn, *, close_after_hours: int = 24) -> list[dict[str, Any]]:
    close_after_hours = max(1, int(close_after_hours))
    return _run_pg_dict_query(
        conn,
        """
        UPDATE app.payment_order AS payment_order
        SET status = 'closed',
            updated_at = NOW()
        WHERE payment_order.status = 'pending'
          AND payment_order.created_at <= NOW() - (%s * INTERVAL '1 hour')
          AND NOT EXISTS (
              SELECT 1
              FROM app.payment_session AS payment_session
              WHERE payment_session.order_id = payment_order.order_id
                AND payment_session.status = 'pending'
                AND (
                    payment_session.expires_at IS NULL
                    OR payment_session.expires_at > NOW()
                )
          )
        RETURNING order_id, user_id, package_code, product_type, provider, list_amount_cents,
                  discount_amount_cents, amount_cents, points_amount, status,
                  provider_order_id, provider_trade_no, promotion_snapshot_json,
                  callback_payload_json, paid_at, created_at, updated_at
        """,
        [close_after_hours],
    )
