"""Payments domain — service functions."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from data_platform.chat_backend.infra.postgres import _fetch_optional_one


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
