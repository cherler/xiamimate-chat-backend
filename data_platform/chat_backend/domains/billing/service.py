"""Billing domain — service functions.

Covers: credit accounts, ledger entries, usage events, daily quota,
event pricing (DB + cache), billing packages, subscriptions.

Depends on: infra.settings, infra.postgres, billing.models, identity.models.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

try:
    import psycopg2.extras
except ImportError:
    pass

from data_platform.chat_backend.infra.settings import (
    DEFAULT_BILLING_PACKAGES,
    DEFAULT_EVENT_PRICING,
    GUEST_DAILY_POINTS,
    POINTS_PRICE_VERSION,
    SIGNUP_GIFT_POINTS,
    _current_quota_date,
    _generate_id,
    _is_guest_identity,
    _utc_now,
)
from data_platform.chat_backend.infra.postgres import (
    _fetch_optional_one,
    _postgres_conn,
    _run_pg_dict_query,
)
from data_platform.chat_backend.domains.billing.models import UserCreditAccount
from data_platform.chat_backend.domains.identity.models import RequestUser


# ---------------------------------------------------------------------------
# Event-pricing cache (DB-backed with in-memory TTL)
# ---------------------------------------------------------------------------

_EVENT_PRICING_CACHE: dict[str, dict[str, Any]] = {}
_EVENT_PRICING_CACHE_LOCK = threading.Lock()
_EVENT_PRICING_CACHE_TS: float = 0.0
_EVENT_PRICING_CACHE_TTL: float = 60.0


# ---------------------------------------------------------------------------
# Credit account
# ---------------------------------------------------------------------------

def _ensure_credit_account(conn, user_id: str) -> UserCreditAccount:
    row = _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.user_credit_account (
            user_id, balance_points, reserved_points, lifetime_granted_points,
            lifetime_purchased_points, lifetime_spent_points, created_at, updated_at
        ) VALUES (%s, 0, 0, 0, 0, 0, NOW(), NOW())
        ON CONFLICT (user_id) DO UPDATE SET updated_at = app.user_credit_account.updated_at
        RETURNING user_id, balance_points, reserved_points, lifetime_granted_points,
                  lifetime_purchased_points, lifetime_spent_points, created_at, updated_at
        """,
        [user_id],
    )[0]
    return UserCreditAccount(**row)


def _get_credit_account(conn, user_id: str, for_update: bool) -> dict[str, Any]:
    clause = " FOR UPDATE" if for_update else ""
    row = _fetch_optional_one(
        conn,
        f"""
        SELECT user_id, balance_points, reserved_points, lifetime_granted_points,
               lifetime_purchased_points, lifetime_spent_points, created_at, updated_at
        FROM app.user_credit_account
        WHERE user_id = %s
        LIMIT 1{clause}
        """,
        [user_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"credit account not found: {user_id}")
    return row


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

def _create_ledger_entry(
    conn,
    user_id: str,
    api_key_id: str | None,
    entry_type: str,
    event_type: str | None,
    units: int,
    points_delta: int,
    balance_after_points: int,
    reference_id: str | None,
    description: str | None,
    meta_json: dict[str, Any],
) -> dict[str, Any]:
    return _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.credit_ledger_entry (
            entry_id, user_id, api_key_id, entry_type, event_type, units, points_delta,
            balance_after_points, reference_id, description, meta_json, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING entry_id, user_id, api_key_id, entry_type, event_type, units,
                  points_delta, balance_after_points, reference_id, description, meta_json, created_at
        """,
        [
            _generate_id("ledger"),
            user_id,
            api_key_id,
            entry_type,
            event_type,
            units,
            points_delta,
            balance_after_points,
            reference_id,
            description,
            psycopg2.extras.Json(meta_json),
        ],
    )[0]


def _credit_points_account(
    conn,
    user_id: str,
    points: int,
    granted_points: int = 0,
    purchased_points: int = 0,
) -> dict[str, Any]:
    _ensure_credit_account(conn, user_id)
    account = _get_credit_account(conn, user_id, for_update=True)
    balance_after = int(account["balance_points"]) + points
    return _run_pg_dict_query(
        conn,
        """
        UPDATE app.user_credit_account
        SET balance_points = %s,
            lifetime_granted_points = lifetime_granted_points + %s,
            lifetime_purchased_points = lifetime_purchased_points + %s,
            updated_at = NOW()
        WHERE user_id = %s
        RETURNING user_id, balance_points, reserved_points, lifetime_granted_points,
                  lifetime_purchased_points, lifetime_spent_points, created_at, updated_at
        """,
        [balance_after, granted_points, purchased_points, user_id],
    )[0]


def _grant_points_with_ledger(
    conn,
    user_id: str,
    points: int,
    entry_type: str,
    event_type: str,
    reference_id: str | None,
    description: str | None,
    meta_json: dict[str, Any],
    api_key_id: str | None = None,
    granted_points: int = 0,
    purchased_points: int = 0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated_account = _credit_points_account(
        conn,
        user_id=user_id,
        points=points,
        granted_points=granted_points,
        purchased_points=purchased_points,
    )
    ledger_entry = _create_ledger_entry(
        conn=conn,
        user_id=user_id,
        api_key_id=api_key_id,
        entry_type=entry_type,
        event_type=event_type,
        units=1,
        points_delta=points,
        balance_after_points=int(updated_account["balance_points"]),
        reference_id=reference_id,
        description=description,
        meta_json=meta_json,
    )
    return updated_account, ledger_entry


# ---------------------------------------------------------------------------
# Usage events
# ---------------------------------------------------------------------------

def _record_usage_event(
    conn,
    user_id: str,
    event_type: str,
    units: int,
    meta_json: dict[str, Any],
    session_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    return _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.usage_event (
            event_id, user_id, session_id, run_id, event_type, units, meta_json, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING event_id, user_id, session_id, run_id, event_type, units, meta_json, created_at
        """,
        [
            _generate_id("usage"),
            user_id,
            session_id,
            run_id,
            event_type,
            units,
            psycopg2.extras.Json(meta_json),
        ],
    )[0]


# ---------------------------------------------------------------------------
# Daily credit quota (guest users)
# ---------------------------------------------------------------------------

def _fetch_daily_credit_quota_state(conn, user_id: str, quota_date) -> dict[str, Any] | None:
    return _fetch_optional_one(
        conn,
        """
        SELECT user_id, quota_date, quota_points, applied_delta_points, consumed_points,
               reset_reference_id, created_at, updated_at
        FROM app.daily_credit_quota_state
        WHERE user_id = %s AND quota_date = %s
        LIMIT 1
        """,
        [user_id, quota_date],
    )


def _fetch_latest_daily_credit_quota_state(conn, user_id: str) -> dict[str, Any] | None:
    return _fetch_optional_one(
        conn,
        """
        SELECT user_id, quota_date, quota_points, applied_delta_points, consumed_points,
               reset_reference_id, created_at, updated_at
        FROM app.daily_credit_quota_state
        WHERE user_id = %s
        ORDER BY quota_date DESC, updated_at DESC
        LIMIT 1
        """,
        [user_id],
    )


def _is_guest_daily_quota_user(user: RequestUser) -> bool:
    return _is_guest_identity(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        plan_tier=user.plan_tier,
    )


def _adjust_daily_credit_quota_consumed(conn, user_id: str, delta_points: int) -> None:
    if delta_points == 0:
        return
    quota_date = _current_quota_date()
    _run_pg_dict_query(
        conn,
        """
        UPDATE app.daily_credit_quota_state
        SET consumed_points = GREATEST(0, consumed_points + %s),
            updated_at = NOW()
        WHERE user_id = %s AND quota_date = %s
        RETURNING user_id, quota_date
        """,
        [delta_points, user_id, quota_date],
    )


def _apply_guest_daily_quota_if_needed(conn, user: RequestUser) -> UserCreditAccount:
    _ensure_credit_account(conn, user.user_id)
    quota_date = _current_quota_date()
    existing_state = _fetch_daily_credit_quota_state(conn, user.user_id, quota_date)
    if existing_state is not None:
        return UserCreditAccount(**_get_credit_account(conn, user.user_id, for_update=False))

    account = _get_credit_account(conn, user.user_id, for_update=True)
    target_points = GUEST_DAILY_POINTS
    current_balance = int(account["balance_points"])
    delta_points = target_points - current_balance
    updated_account = account
    reference_id = f"guest_daily_quota:{user.user_id}:{quota_date.isoformat()}"

    if delta_points > 0:
        updated_account = _credit_points_account(
            conn,
            user_id=user.user_id,
            points=delta_points,
            granted_points=delta_points,
        )
    elif delta_points < 0:
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
            [target_points, user.user_id],
        )[0]

    if delta_points != 0:
        _create_ledger_entry(
            conn=conn,
            user_id=user.user_id,
            api_key_id=None,
            entry_type="daily_quota_reset",
            event_type="daily_quota_reset",
            units=1,
            points_delta=delta_points,
            balance_after_points=int(updated_account["balance_points"]),
            reference_id=reference_id,
            description=f"guest daily quota reset to {target_points} points",
            meta_json={
                "policy": "guest_daily_points",
                "quota_date": quota_date.isoformat(),
                "quota_points": target_points,
                "points_price_version": POINTS_PRICE_VERSION,
            },
        )

    _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.daily_credit_quota_state (
            user_id, quota_date, quota_points, applied_delta_points, consumed_points,
            reset_reference_id, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
        RETURNING user_id, quota_date
        """,
        [user.user_id, quota_date, target_points, delta_points, 0, reference_id],
    )
    return UserCreditAccount(**updated_account)


def _grant_signup_gift_if_needed(conn, user_id: str) -> UserCreditAccount:
    _ensure_credit_account(conn, user_id)
    if SIGNUP_GIFT_POINTS <= 0:
        return UserCreditAccount(**_get_credit_account(conn, user_id, for_update=False))

    existing = _fetch_optional_one(
        conn,
        """
        SELECT entry_id
        FROM app.credit_ledger_entry
        WHERE user_id = %s AND entry_type = 'signup_gift'
        LIMIT 1
        """,
        [user_id],
    )
    if existing is not None:
        return UserCreditAccount(**_get_credit_account(conn, user_id, for_update=False))

    _grant_points_with_ledger(
        conn=conn,
        user_id=user_id,
        entry_type="signup_gift",
        event_type="signup_gift",
        reference_id=user_id,
        description="signup gift points",
        meta_json={"points_price_version": POINTS_PRICE_VERSION},
        granted_points=SIGNUP_GIFT_POINTS,
        points=SIGNUP_GIFT_POINTS,
    )
    return UserCreditAccount(**_get_credit_account(conn, user_id, for_update=False))


def _ensure_user_credit_account_state(conn, user: RequestUser) -> UserCreditAccount:
    if _is_guest_daily_quota_user(user):
        return _apply_guest_daily_quota_if_needed(conn, user)
    return _grant_signup_gift_if_needed(conn, user.user_id)


# ---------------------------------------------------------------------------
# Billing packages
# ---------------------------------------------------------------------------

def _seed_billing_packages(conn) -> None:
    for package in DEFAULT_BILLING_PACKAGES:
        _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.billing_package (
                package_code, package_name, product_type, price_cents, points_amount,
                period_days, status, display_order, meta_json, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, 'active', %s, %s, NOW(), NOW())
            ON CONFLICT (package_code) DO UPDATE SET
                package_name = EXCLUDED.package_name,
                product_type = EXCLUDED.product_type,
                price_cents = EXCLUDED.price_cents,
                points_amount = EXCLUDED.points_amount,
                period_days = EXCLUDED.period_days,
                display_order = EXCLUDED.display_order,
                meta_json = EXCLUDED.meta_json,
                updated_at = NOW()
            RETURNING package_code
            """,
            [
                package["package_code"],
                package["package_name"],
                package["product_type"],
                package["price_cents"],
                package["points_amount"],
                package["period_days"],
                package["display_order"],
                psycopg2.extras.Json(package.get("meta_json") or {}),
            ],
        )


def _fetch_billing_package(conn, package_code: str) -> dict[str, Any]:
    row = _fetch_optional_one(
        conn,
        """
        SELECT package_code, package_name, product_type, price_cents, points_amount,
               period_days, status, display_order, meta_json, created_at, updated_at
        FROM app.billing_package
        WHERE package_code = %s
        LIMIT 1
        """,
        [package_code],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"billing package not found: {package_code}")
    if row["status"] != "active":
        raise HTTPException(status_code=409, detail=f"billing package is not active: {package_code}")
    return row


def _list_billing_packages(conn) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT package_code, package_name, product_type, price_cents, points_amount,
               period_days, status, display_order, meta_json, created_at, updated_at
        FROM app.billing_package
        WHERE status = 'active'
        ORDER BY display_order ASC, created_at ASC, package_code ASC
        """,
    )


# ---------------------------------------------------------------------------
# Event pricing (DB + cache)
# ---------------------------------------------------------------------------

def _seed_billing_event_pricing(conn) -> None:
    for row in DEFAULT_EVENT_PRICING:
        _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.billing_event_pricing (
                event_type, display_name, points_per_unit, status, display_order, created_at, updated_at
            ) VALUES (%s, %s, %s, 'active', %s, NOW(), NOW())
            ON CONFLICT (event_type) DO NOTHING
            RETURNING event_type
            """,
            [row["event_type"], row["display_name"], row["points_per_unit"], row["display_order"]],
        )


def _load_event_pricing_from_db(conn) -> dict[str, dict[str, Any]]:
    rows = _run_pg_dict_query(
        conn,
        """
        SELECT event_type, display_name, points_per_unit, status, display_order
        FROM app.billing_event_pricing
        WHERE status = 'active'
        ORDER BY display_order ASC, event_type ASC
        """,
    )
    return {row["event_type"]: row for row in rows}


def _get_event_pricing(conn=None) -> dict[str, dict[str, Any]]:
    global _EVENT_PRICING_CACHE, _EVENT_PRICING_CACHE_TS
    now = time.monotonic()
    if _EVENT_PRICING_CACHE and (now - _EVENT_PRICING_CACHE_TS) < _EVENT_PRICING_CACHE_TTL:
        return _EVENT_PRICING_CACHE
    with _EVENT_PRICING_CACHE_LOCK:
        if _EVENT_PRICING_CACHE and (now - _EVENT_PRICING_CACHE_TS) < _EVENT_PRICING_CACHE_TTL:
            return _EVENT_PRICING_CACHE
        try:
            if conn is not None:
                pricing = _load_event_pricing_from_db(conn)
            else:
                with _postgres_conn() as c:
                    pricing = _load_event_pricing_from_db(c)
            if pricing:
                _EVENT_PRICING_CACHE = pricing
                _EVENT_PRICING_CACHE_TS = time.monotonic()
        except Exception:
            pass
    if not _EVENT_PRICING_CACHE:
        _EVENT_PRICING_CACHE = {
            row["event_type"]: {
                "event_type": row["event_type"],
                "display_name": row["display_name"],
                "points_per_unit": row["points_per_unit"],
                "status": "active",
                "display_order": row["display_order"],
            }
            for row in DEFAULT_EVENT_PRICING
        }
        _EVENT_PRICING_CACHE_TS = time.monotonic()
    return _EVENT_PRICING_CACHE


def _invalidate_event_pricing_cache() -> None:
    global _EVENT_PRICING_CACHE_TS
    _EVENT_PRICING_CACHE_TS = 0.0


def _get_point_cost_by_event() -> dict[str, int]:
    pricing = _get_event_pricing()
    return {k: v["points_per_unit"] for k, v in pricing.items()}


def _calculate_points_for_event(event_type: str, units: int) -> int:
    pricing = _get_event_pricing()
    entry = pricing.get(event_type)
    if entry is None:
        raise HTTPException(status_code=400, detail=f"unsupported billing event_type: {event_type}")
    return int(entry["points_per_unit"]) * units


# ---------------------------------------------------------------------------
# Subscription helpers
# ---------------------------------------------------------------------------

def _normalize_period_window(period_start: datetime | None, period_end: datetime | None, period_days: int) -> tuple[datetime, datetime]:
    start = period_start or _utc_now()
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    end = period_end or datetime.fromtimestamp(start.timestamp() + max(1, period_days) * 86400, tz=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if end <= start:
        raise HTTPException(status_code=400, detail="subscription grant period_end must be later than period_start")
    return start, end


def _fetch_subscription(conn, subscription_id: str) -> dict[str, Any]:
    row = _fetch_optional_one(
        conn,
        """
        SELECT subscription_id, user_id, package_code, provider, provider_subscription_id,
               status, monthly_points, current_period_start, current_period_end,
               next_grant_at, last_grant_at, cancel_at_period_end, meta_json,
               created_at, updated_at
        FROM app.billing_subscription
        WHERE subscription_id = %s
        LIMIT 1
        """,
        [subscription_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"subscription not found: {subscription_id}")
    return row


def _fetch_subscriptions_for_user(conn, user_id: str) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT subscription_id, user_id, package_code, provider, provider_subscription_id,
               status, monthly_points, current_period_start, current_period_end,
               next_grant_at, last_grant_at, cancel_at_period_end, meta_json,
               created_at, updated_at
        FROM app.billing_subscription
        WHERE user_id = %s
        ORDER BY updated_at DESC, created_at DESC
        """,
        [user_id],
    )


def _grant_subscription_period(
    conn,
    subscription_row: dict[str, Any],
    period_start: datetime,
    period_end: datetime,
    reference_id: str,
    order_id: str | None,
    meta_json: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    inserted_grant = _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.subscription_grant (
            grant_id, subscription_id, user_id, order_id, period_start, period_end,
            points_amount, reference_id, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (subscription_id, period_start, period_end) DO NOTHING
        RETURNING grant_id, subscription_id, user_id, order_id, period_start, period_end,
                  points_amount, reference_id, created_at
        """,
        [
            _generate_id("subgrant"),
            subscription_row["subscription_id"],
            subscription_row["user_id"],
            order_id,
            period_start,
            period_end,
            subscription_row["monthly_points"],
            reference_id,
        ],
    )
    if not inserted_grant:
        raise HTTPException(status_code=409, detail="subscription points already granted for this period")
    grant_row = inserted_grant[0]

    updated_account, ledger_entry = _grant_points_with_ledger(
        conn=conn,
        user_id=subscription_row["user_id"],
        points=int(subscription_row["monthly_points"]),
        entry_type="subscription_grant",
        event_type="subscription_grant",
        reference_id=reference_id,
        description="subscription points granted",
        meta_json={
            **meta_json,
            "subscription_id": subscription_row["subscription_id"],
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
        },
        purchased_points=int(subscription_row["monthly_points"]),
    )
    updated_subscription = _run_pg_dict_query(
        conn,
        """
        UPDATE app.billing_subscription
        SET status = 'active',
            current_period_start = %s,
            current_period_end = %s,
            next_grant_at = %s,
            last_grant_at = NOW(),
            updated_at = NOW()
        WHERE subscription_id = %s
        RETURNING subscription_id, user_id, package_code, provider, provider_subscription_id,
                  status, monthly_points, current_period_start, current_period_end,
                  next_grant_at, last_grant_at, cancel_at_period_end, meta_json,
                  created_at, updated_at
        """,
        [period_start, period_end, period_end, subscription_row["subscription_id"]],
    )[0]
    return updated_subscription, updated_account, grant_row, ledger_entry
