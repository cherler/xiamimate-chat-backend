#!/usr/bin/env python3
"""Operational helpers for WeChat Pay orders."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests as http_requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_platform.chat_backend.domains.payments.service import (  # noqa: E402
    _close_stale_pending_payment_orders,
    _expire_pending_payment_sessions,
    _fetch_latest_payment_session,
    _fetch_payment_order,
    _update_payment_session_status,
)
from data_platform.chat_backend.domains.payments.wechat_pay import (  # noqa: E402
    extract_wechat_trade_payload,
    query_wechat_order_by_out_trade_no,
    wechat_trade_state_to_session_status,
)
from data_platform.chat_backend.domains.portal.service import _backend_base_url  # noqa: E402
from data_platform.chat_backend.infra.postgres import _postgres_conn, _run_pg_dict_query  # noqa: E402
from data_platform.chat_backend.infra.settings import (  # noqa: E402
    IDEMPOTENCY_KEY_HEADER_NAME,
    INTERNAL_SERVICE_NAME_HEADER_NAME,
    INTERNAL_SERVICE_SECRET,
    INTERNAL_SERVICE_SECRET_HEADER_NAME,
    _utc_now,
)


def _mask(value: Any) -> str:
    text = str(value or "")
    if len(text) <= 12:
        return text
    return f"{text[:6]}...{text[-4:]}"


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, default=str, indent=2))


def _order_summary(order: dict[str, Any]) -> dict[str, Any]:
    return {
        "order_id": _mask(order.get("order_id")),
        "user_id": _mask(order.get("user_id")),
        "package_code": order.get("package_code"),
        "provider": order.get("provider"),
        "amount_cents": order.get("amount_cents"),
        "points_amount": order.get("points_amount"),
        "status": order.get("status"),
        "provider_order_id": _mask(order.get("provider_order_id")),
        "provider_trade_no_exists": bool(order.get("provider_trade_no")),
        "paid_at": order.get("paid_at"),
        "created_at": order.get("created_at"),
        "updated_at": order.get("updated_at"),
    }


def _session_summary(session: dict[str, Any] | None) -> dict[str, Any] | None:
    if session is None:
        return None
    return {
        "session_id": _mask(session.get("session_id")),
        "provider": session.get("provider"),
        "channel": session.get("channel"),
        "status": session.get("status"),
        "provider_order_id": _mask(session.get("provider_order_id")),
        "provider_trade_no_exists": bool(session.get("provider_trade_no")),
        "expires_at": session.get("expires_at"),
        "paid_at": session.get("paid_at"),
        "updated_at": session.get("updated_at"),
    }


def _post_internal_callback(order: dict[str, Any], trade: dict[str, Any]) -> dict[str, Any]:
    if not INTERNAL_SERVICE_SECRET:
        raise RuntimeError("CHAT_BACKEND_SERVICE_SECRET is not configured")
    payload = {
        "order_id": order["order_id"],
        "provider_order_id": trade.get("provider_order_id") or order["order_id"],
        "provider_trade_no": trade.get("provider_trade_no"),
        "paid_amount_cents": trade.get("paid_amount_cents"),
        "meta": {
            "source": "wechat_ops_query",
            "trade_state": trade.get("trade_state"),
        },
    }
    response = http_requests.post(
        _backend_base_url() + "/internal/payments/provider-callback/wechat",
        headers={
            INTERNAL_SERVICE_SECRET_HEADER_NAME: INTERNAL_SERVICE_SECRET,
            INTERNAL_SERVICE_NAME_HEADER_NAME: "wechat-ops-query",
            IDEMPOTENCY_KEY_HEADER_NAME: f"wechat-ops-query:{trade.get('provider_trade_no') or order['order_id']}",
        },
        json=payload,
        timeout=12,
    )
    try:
        body = response.json()
    except Exception:
        body = {"message": response.text.strip() or response.reason}
    if response.status_code != 200 or body.get("success") is not True:
        raise RuntimeError(body.get("detail") or body.get("message") or "internal callback failed")
    return body


def query_order(args: argparse.Namespace) -> None:
    with _postgres_conn() as conn:
        order = _fetch_payment_order(conn, args.order_id)
        latest_session = _fetch_latest_payment_session(conn, args.order_id)

    if str(order.get("provider") or "").lower() != "wechat":
        raise SystemExit("order provider is not wechat")

    trade_response = query_wechat_order_by_out_trade_no(args.order_id)
    trade = extract_wechat_trade_payload(trade_response)
    session_status = wechat_trade_state_to_session_status(str(trade.get("trade_state") or ""))
    applied_callback = False

    if args.apply and session_status == "paid":
        _post_internal_callback(order, trade)
        applied_callback = True

    if args.apply and latest_session is not None:
        with _postgres_conn() as conn:
            _update_payment_session_status(
                conn,
                session_id=str(latest_session["session_id"]),
                status=session_status,
                provider_trade_no=trade.get("provider_trade_no"),
                prepay_payload_json={
                    **dict(latest_session.get("prepay_payload_json") or {}),
                    "last_ops_query_at": _utc_now().isoformat(),
                    "last_ops_query_trade_state": trade.get("trade_state"),
                },
                paid_at=_utc_now() if session_status == "paid" else None,
            )

    with _postgres_conn() as conn:
        refreshed_order = _fetch_payment_order(conn, args.order_id)
        refreshed_session = _fetch_latest_payment_session(conn, args.order_id)

    _print_json(
        {
            "apply": bool(args.apply),
            "applied_internal_callback": applied_callback,
            "local_order": _order_summary(refreshed_order),
            "latest_session": _session_summary(refreshed_session),
            "wechat_trade": {
                "out_trade_no": _mask(trade.get("provider_order_id")),
                "transaction_id_exists": bool(trade.get("provider_trade_no")),
                "trade_state": trade.get("trade_state"),
                "paid_amount_cents": trade.get("paid_amount_cents"),
                "session_status": session_status,
            },
        }
    )


def cleanup_orders(args: argparse.Namespace) -> None:
    if not args.apply:
        with _postgres_conn() as conn:
            expirable_sessions = _run_pg_dict_query(
                conn,
                """
                SELECT session_id, order_id, user_id, provider, channel, status,
                       provider_order_id, provider_trade_no, cashier_url, qr_code_url,
                       prepay_payload_json, expires_at, paid_at, created_at, updated_at
                FROM app.payment_session
                WHERE status = 'pending'
                  AND expires_at IS NOT NULL
                  AND expires_at <= NOW()
                ORDER BY expires_at ASC
                LIMIT %s
                """,
                [args.limit],
            )
            closable_orders = _run_pg_dict_query(
                conn,
                """
                SELECT order_id, user_id, package_code, product_type, provider, list_amount_cents,
                       discount_amount_cents, amount_cents, points_amount, status,
                       provider_order_id, provider_trade_no, promotion_snapshot_json,
                       callback_payload_json, paid_at, created_at, updated_at
                FROM app.payment_order AS payment_order
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
                ORDER BY payment_order.created_at ASC
                LIMIT %s
                """,
                [args.close_after_hours, args.limit],
            )
        _print_json(
            {
                "apply": False,
                "would_expire_sessions": [_session_summary(row) for row in expirable_sessions],
                "would_close_orders": [_order_summary(row) for row in closable_orders],
            }
        )
        return

    with _postgres_conn() as conn:
        expired_sessions = _expire_pending_payment_sessions(conn)
        closed_orders = _close_stale_pending_payment_orders(conn, close_after_hours=args.close_after_hours)
    _print_json(
        {
            "apply": True,
            "expired_sessions_count": len(expired_sessions),
            "closed_orders_count": len(closed_orders),
            "expired_sessions": [_session_summary(row) for row in expired_sessions[: args.limit]],
            "closed_orders": [_order_summary(row) for row in closed_orders[: args.limit]],
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WeChat Pay order operations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    query_parser = subparsers.add_parser("query", help="Query a WeChat order by local order_id")
    query_parser.add_argument("order_id")
    query_parser.add_argument("--apply", action="store_true", help="Apply SUCCESS result through internal callback")
    query_parser.set_defaults(func=query_order)

    cleanup_parser = subparsers.add_parser("cleanup", help="Expire QR sessions and close stale pending orders")
    cleanup_parser.add_argument("--apply", action="store_true", help="Apply cleanup changes")
    cleanup_parser.add_argument("--close-after-hours", type=int, default=24)
    cleanup_parser.add_argument("--limit", type=int, default=20)
    cleanup_parser.set_defaults(func=cleanup_orders)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()