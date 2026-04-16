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
    DEFAULT_PROMOTION_RULES,
    GUEST_DAILY_POINTS,
    POINTS_PRICE_VERSION,
    REFERRAL_INVITER_REWARD_POINTS,
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
_LEGACY_BILLING_PACKAGE_CODES = (
    "credit_pack_s",
    "credit_pack_m",
    "credit_pack_l",
    "monthly_basic",
)


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
    _ensure_credit_account(conn, user_id)
    _reconcile_user_subscription_state(conn, user_id)
    _reconcile_expired_subscription_points(conn, user_id)
    return _get_credit_account_row(conn, user_id, for_update=for_update)


def _get_credit_account_row(conn, user_id: str, for_update: bool) -> dict[str, Any]:
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


def _bucket_source_for_entry_type(entry_type: str, meta_json: dict[str, Any] | None = None) -> str:
    normalized = str(entry_type or "").strip().lower()
    meta_json = meta_json or {}
    explicit_source = str(meta_json.get("balance_source") or meta_json.get("source") or "").strip().lower()
    if explicit_source in {"subscription", "recharge", "other"}:
        return explicit_source
    if normalized == "subscription_grant":
        return "subscription"
    if normalized == "recharge":
        return "recharge"
    return "other"


def _serialize_bucket_allocation(bucket: dict[str, Any], points: int) -> dict[str, Any]:
    meta_json = dict(bucket.get("meta_json") or {})
    expires_at = bucket.get("expires_at")
    return {
        "bucket_id": bucket.get("bucket_id"),
        "source": bucket.get("source") or "other",
        "points": int(points),
        "expires_at": expires_at.isoformat() if expires_at is not None else None,
        "package_code": meta_json.get("package_code"),
        "payment_order_id": meta_json.get("payment_order_id"),
        "subscription_grant_reference_id": meta_json.get("subscription_grant_reference_id") or bucket.get("bucket_id"),
    }


def _ordered_consumption_buckets(buckets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [bucket for bucket in buckets if int(bucket.get("remaining") or 0) > 0],
        key=lambda bucket: (
            bucket["expires_at"] is None,
            bucket["expires_at"] or datetime.max.replace(tzinfo=timezone.utc),
            bucket["created_at"],
            bucket["bucket_id"],
        ),
    )


def _allocate_points_from_buckets(
    buckets: list[dict[str, Any]],
    points: int,
    *,
    preferred_bucket_ids: list[str] | None = None,
    preferred_source: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    remaining = max(0, int(points))
    allocations: list[dict[str, Any]] = []
    visited_bucket_refs: set[int] = set()

    def consume_from_candidates(candidates: list[dict[str, Any]]) -> None:
        nonlocal remaining
        for bucket in candidates:
            if remaining <= 0:
                break
            if int(bucket.get("remaining") or 0) <= 0:
                continue
            consumed = min(int(bucket["remaining"]), remaining)
            if consumed <= 0:
                continue
            bucket["remaining"] -= consumed
            remaining -= consumed
            allocations.append(_serialize_bucket_allocation(bucket, consumed))

    if preferred_bucket_ids:
        ordered_targeted: list[dict[str, Any]] = []
        for target_bucket_id in preferred_bucket_ids:
            for bucket in buckets:
                bucket_ref = id(bucket)
                if bucket_ref in visited_bucket_refs:
                    continue
                if bucket.get("bucket_id") != target_bucket_id or int(bucket.get("remaining") or 0) <= 0:
                    continue
                visited_bucket_refs.add(bucket_ref)
                ordered_targeted.append(bucket)
        consume_from_candidates(ordered_targeted)

    if remaining > 0 and preferred_source:
        source_candidates: list[dict[str, Any]] = []
        for bucket in _ordered_consumption_buckets(buckets):
            bucket_ref = id(bucket)
            if bucket_ref in visited_bucket_refs:
                continue
            if bucket.get("source") != preferred_source:
                continue
            visited_bucket_refs.add(bucket_ref)
            source_candidates.append(bucket)
        consume_from_candidates(source_candidates)

    if remaining > 0:
        fallback_candidates: list[dict[str, Any]] = []
        for bucket in _ordered_consumption_buckets(buckets):
            bucket_ref = id(bucket)
            if bucket_ref in visited_bucket_refs:
                continue
            visited_bucket_refs.add(bucket_ref)
            fallback_candidates.append(bucket)
        consume_from_candidates(fallback_candidates)

    return allocations, remaining


def _rebuild_credit_buckets_from_ledger_rows(
    ledger_rows: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    replay_now = now or _utc_now()
    buckets: list[dict[str, Any]] = []
    for row in ledger_rows:
        delta = int(row.get("points_delta") or 0)
        entry_type = str(row.get("entry_type") or "").strip().lower()
        meta_json = dict(row.get("meta_json") or {})
        created_at = _parse_optional_utc_datetime(row.get("created_at")) or replay_now

        if delta > 0:
            refund_allocations = meta_json.get("refund_allocations") or []
            if entry_type == "refund" and refund_allocations:
                for index, allocation in enumerate(refund_allocations):
                    restored_points = int(allocation.get("points") or 0)
                    if restored_points <= 0:
                        continue
                    buckets.append(
                        {
                            "bucket_id": str(allocation.get("bucket_id") or f"{row.get('entry_id') or _generate_id('refund_bucket')}:{index}"),
                            "bucket_type": entry_type,
                            "source": str(allocation.get("source") or "other").strip().lower() or "other",
                            "remaining": restored_points,
                            "expires_at": _parse_optional_utc_datetime(allocation.get("expires_at")),
                            "created_at": created_at,
                            "meta_json": {
                                **meta_json,
                                "subscription_grant_reference_id": allocation.get("subscription_grant_reference_id"),
                                "package_code": allocation.get("package_code"),
                                "payment_order_id": allocation.get("payment_order_id"),
                            },
                        }
                    )
                continue

            expires_at = None
            if entry_type == "subscription_grant":
                expires_at = _parse_optional_utc_datetime(meta_json.get("period_end"))
            buckets.append(
                {
                    "bucket_id": str(row.get("reference_id") or row.get("entry_id") or _generate_id("bucket")),
                    "bucket_type": entry_type,
                    "source": _bucket_source_for_entry_type(entry_type, meta_json),
                    "remaining": delta,
                    "expires_at": expires_at,
                    "created_at": created_at,
                    "meta_json": meta_json,
                }
            )
            continue

        if delta >= 0:
            continue

        remaining_to_consume = -delta
        if entry_type == "subscription_expire":
            target_bucket_id = str(meta_json.get("subscription_grant_reference_id") or "").strip()
            if target_bucket_id:
                _, remaining_to_consume = _allocate_points_from_buckets(
                    buckets,
                    remaining_to_consume,
                    preferred_bucket_ids=[target_bucket_id],
                )

        source_allocations = meta_json.get("balance_source_allocations") or []
        if remaining_to_consume > 0 and source_allocations:
            for allocation in source_allocations:
                allocation_points = min(remaining_to_consume, int(allocation.get("points") or 0))
                if allocation_points <= 0:
                    continue
                _, leftover = _allocate_points_from_buckets(
                    buckets,
                    allocation_points,
                    preferred_bucket_ids=[str(allocation.get("bucket_id") or "").strip()] if allocation.get("bucket_id") else None,
                    preferred_source=str(allocation.get("source") or "").strip().lower() or None,
                )
                consumed_points = allocation_points - leftover
                remaining_to_consume -= consumed_points
                if remaining_to_consume <= 0:
                    break

        if remaining_to_consume > 0:
            _allocate_points_from_buckets(buckets, remaining_to_consume)

    return buckets


def _build_credit_balance_breakdown(conn, user_id: str) -> dict[str, Any]:
    ledger_rows = _run_pg_dict_query(
        conn,
        """
        SELECT entry_id, entry_type, points_delta, reference_id, meta_json, created_at
        FROM app.credit_ledger_entry
        WHERE user_id = %s
        ORDER BY created_at ASC, entry_id ASC
        """,
        [user_id],
    )
    buckets = _rebuild_credit_buckets_from_ledger_rows(ledger_rows, now=_utc_now())
    subscription_balance_points = sum(int(bucket.get("remaining") or 0) for bucket in buckets if bucket.get("source") == "subscription")
    recharge_balance_points = sum(int(bucket.get("remaining") or 0) for bucket in buckets if bucket.get("source") == "recharge")
    other_balance_points = sum(int(bucket.get("remaining") or 0) for bucket in buckets if bucket.get("source") not in {"subscription", "recharge"})
    total_balance_points = subscription_balance_points + recharge_balance_points + other_balance_points
    return {
        "total_balance_points": total_balance_points,
        "subscription_balance_points": subscription_balance_points,
        "recharge_balance_points": recharge_balance_points,
        "other_balance_points": other_balance_points,
        "permanent_balance_points": recharge_balance_points + other_balance_points,
        "consumption_priority": ["subscription", "recharge", "other"],
        "consumption_policy_text": "消费时优先扣减月包积分；充值包积分永久有效。",
    }


def _preview_credit_consumption_allocations(conn, user_id: str, points: int) -> list[dict[str, Any]]:
    if points <= 0:
        return []
    ledger_rows = _run_pg_dict_query(
        conn,
        """
        SELECT entry_id, entry_type, points_delta, reference_id, meta_json, created_at
        FROM app.credit_ledger_entry
        WHERE user_id = %s
        ORDER BY created_at ASC, entry_id ASC
        """,
        [user_id],
    )
    buckets = _rebuild_credit_buckets_from_ledger_rows(ledger_rows, now=_utc_now())
    allocations, remaining = _allocate_points_from_buckets(buckets, points)
    if remaining > 0:
        raise HTTPException(status_code=402, detail="insufficient points")
    return allocations


def _resolve_refund_source_allocations(
    conn,
    *,
    user_id: str,
    reference_id: str | None,
    event_type: str | None,
    points: int,
) -> list[dict[str, Any]]:
    if not reference_id or points <= 0:
        return []
    ledger_row = _fetch_optional_one(
        conn,
        """
        SELECT entry_id, entry_type, event_type, points_delta, meta_json, created_at
        FROM app.credit_ledger_entry
        WHERE user_id = %s
          AND reference_id = %s
          AND points_delta < 0
          AND entry_type = 'consume'
          AND (%s IS NULL OR event_type = %s)
        ORDER BY created_at DESC, entry_id DESC
        LIMIT 1
        """,
        [user_id, reference_id, event_type, event_type],
    )
    if ledger_row is None:
        return []
    source_allocations = list((ledger_row.get("meta_json") or {}).get("balance_source_allocations") or [])
    if not source_allocations:
        return []
    remaining = points
    refund_allocations: list[dict[str, Any]] = []
    for allocation in source_allocations:
        allocation_points = min(remaining, int(allocation.get("points") or 0))
        if allocation_points <= 0:
            continue
        refund_allocations.append(
            {
                "bucket_id": allocation.get("bucket_id"),
                "source": allocation.get("source"),
                "points": allocation_points,
                "expires_at": allocation.get("expires_at"),
                "package_code": allocation.get("package_code"),
                "payment_order_id": allocation.get("payment_order_id"),
                "subscription_grant_reference_id": allocation.get("subscription_grant_reference_id"),
            }
        )
        remaining -= allocation_points
        if remaining <= 0:
            break
    return refund_allocations


def _parse_optional_utc_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        raw_value = str(value).strip()
        if not raw_value:
            return None
        if raw_value.endswith("Z"):
            raw_value = raw_value[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw_value)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _reconcile_user_subscription_state(conn, user_id: str) -> None:
    now = _utc_now()
    _run_pg_dict_query(
        conn,
        """
        UPDATE app.billing_subscription
        SET status = 'expired',
            updated_at = NOW()
        WHERE user_id = %s
          AND status = 'active'
          AND current_period_end IS NOT NULL
          AND current_period_end <= %s
        RETURNING subscription_id
        """,
        [user_id, now],
    )
    current_tier = _fetch_optional_one(
        conn,
        """
        SELECT COALESCE(NULLIF(LOWER(TRIM(bp.meta_json->>'tier_key')), ''), 'free') AS tier_key
        FROM app.billing_subscription bs
        JOIN app.billing_package bp ON bp.package_code = bs.package_code
        WHERE bs.user_id = %s
          AND bs.status = 'active'
          AND (bs.current_period_end IS NULL OR bs.current_period_end > %s)
        ORDER BY bs.current_period_end DESC NULLS LAST, bs.updated_at DESC, bs.created_at DESC
        LIMIT 1
        """,
        [user_id, now],
    )
    target_tier = str((current_tier or {}).get("tier_key") or "free").strip().lower() or "free"
    _run_pg_dict_query(
        conn,
        """
        UPDATE app.app_user
        SET plan_tier = %s,
            updated_at = NOW()
        WHERE user_id = %s
          AND COALESCE(plan_tier, '') <> %s
        RETURNING user_id
        """,
        [target_tier, user_id, target_tier],
    )


def _reconcile_expired_subscription_points(conn, user_id: str) -> None:
    now = _utc_now()
    expired_grant_exists = _fetch_optional_one(
        conn,
        """
        SELECT grant_id
        FROM app.subscription_grant
        WHERE user_id = %s
          AND period_end <= %s
        LIMIT 1
        """,
        [user_id, now],
    )
    if expired_grant_exists is None:
        return

    ledger_rows = _run_pg_dict_query(
        conn,
        """
        SELECT entry_id, entry_type, points_delta, reference_id, description, meta_json, created_at
        FROM app.credit_ledger_entry
        WHERE user_id = %s
        ORDER BY created_at ASC, entry_id ASC
        """,
        [user_id],
    )
    if not ledger_rows:
        return

    buckets = _rebuild_credit_buckets_from_ledger_rows(ledger_rows, now=now)

    expired_buckets = [
        bucket
        for bucket in buckets
        if bucket["bucket_type"] == "subscription_grant"
        and bucket["expires_at"] is not None
        and bucket["expires_at"] <= now
        and bucket["remaining"] > 0
    ]
    if not expired_buckets:
        return

    account = _get_credit_account_row(conn, user_id, for_update=True)
    balance_after = int(account.get("balance_points") or 0)
    if balance_after <= 0:
        return

    expired_buckets.sort(key=lambda bucket: (bucket["expires_at"], bucket["created_at"], bucket["bucket_id"]))
    applied_expire_points = 0
    for bucket in expired_buckets:
        points_to_expire = min(int(bucket["remaining"]), balance_after)
        if points_to_expire <= 0:
            break
        balance_after -= points_to_expire
        applied_expire_points += points_to_expire
        bucket_meta = dict(bucket.get("meta_json") or {})
        _create_ledger_entry(
            conn=conn,
            user_id=user_id,
            api_key_id=None,
            entry_type="subscription_expire",
            event_type="subscription_expire",
            units=1,
            points_delta=-points_to_expire,
            balance_after_points=balance_after,
            reference_id=f"subscription_expire:{bucket['bucket_id']}",
            description="expired subscription points removed",
            meta_json={
                "subscription_grant_reference_id": bucket["bucket_id"],
                "expired_points": points_to_expire,
                "period_start": bucket_meta.get("period_start"),
                "period_end": bucket_meta.get("period_end"),
                "points_price_version": POINTS_PRICE_VERSION,
            },
        )
    if applied_expire_points <= 0:
        return

    _run_pg_dict_query(
        conn,
        """
        UPDATE app.user_credit_account
        SET balance_points = %s,
            updated_at = NOW()
        WHERE user_id = %s
        RETURNING user_id
        """,
        [balance_after, user_id],
    )


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
    user_row = _fetch_optional_one(
        conn,
        """
        SELECT email_verified_at
        FROM app.app_user
        WHERE user_id = %s
        LIMIT 1
        """,
        [user_id],
    )
    if user_row is None:
        raise HTTPException(status_code=404, detail=f"user not found: {user_id}")
    if user_row.get("email_verified_at") is None:
        return UserCreditAccount(**_get_credit_account(conn, user_id, for_update=False))

    signup_points, signup_rule = _resolve_signup_gift_points(conn)
    if signup_points <= 0:
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
        meta_json={
            "points_price_version": POINTS_PRICE_VERSION,
            "promotion_rule_code": signup_rule["rule_code"] if signup_rule else None,
        },
        granted_points=signup_points,
        points=signup_points,
    )
    return UserCreditAccount(**_get_credit_account(conn, user_id, for_update=False))


def _resolve_referral_inviter_reward_points(conn) -> tuple[int, dict[str, Any] | None]:
    rules = _list_active_promotion_rules(conn, ["referral_inviter_reward"])
    if not rules:
        return REFERRAL_INVITER_REWARD_POINTS, None
    rule = rules[0]
    if rule.get("benefit_type") != "points_bonus":
        return REFERRAL_INVITER_REWARD_POINTS, rule
    return max(0, int(rule.get("benefit_value") or 0)), rule


def _mark_referral_binding_rewarded(conn, invited_user_id: str, *, rewarded: bool) -> None:
    status = "rewarded" if rewarded else "activated"
    _run_pg_dict_query(
        conn,
        """
        UPDATE app.user_referral_binding
        SET status = %s,
            activated_at = COALESCE(activated_at, NOW()),
            rewarded_at = CASE WHEN %s THEN COALESCE(rewarded_at, NOW()) ELSE rewarded_at END,
            updated_at = NOW()
        WHERE invited_user_id = %s
        RETURNING binding_id
        """,
        [status, rewarded, invited_user_id],
    )


def _grant_referral_inviter_reward_if_needed(conn, invited_user_id: str) -> dict[str, Any] | None:
    binding = _fetch_optional_one(
        conn,
        """
        SELECT binding_id, inviter_user_id, invited_user_id, invite_code,
               status, activated_at, rewarded_at, created_at, updated_at
        FROM app.user_referral_binding
        WHERE invited_user_id = %s
        LIMIT 1
        """,
        [invited_user_id],
    )
    if binding is None:
        return None

    invited_user = _fetch_optional_one(
        conn,
        """
        SELECT user_id, email, display_name, email_verified_at
        FROM app.app_user
        WHERE user_id = %s
        LIMIT 1
        """,
        [invited_user_id],
    )
    if invited_user is None or invited_user.get("email_verified_at") is None:
        return None

    reward_points, reward_rule = _resolve_referral_inviter_reward_points(conn)
    existing_reward = _fetch_optional_one(
        conn,
        """
        SELECT entry_id
        FROM app.credit_ledger_entry
        WHERE user_id = %s
          AND event_type = 'referral_inviter_reward'
          AND reference_id = %s
        LIMIT 1
        """,
        [binding["inviter_user_id"], invited_user_id],
    )
    if existing_reward is not None or binding.get("rewarded_at") is not None:
        _mark_referral_binding_rewarded(conn, invited_user_id, rewarded=True)
        return None

    if reward_rule is not None:
        claim_row = _create_promotion_claim(
            conn,
            rule_code=str(reward_rule.get("rule_code") or ""),
            user_id=binding["inviter_user_id"],
            claim_key=invited_user_id,
            order_id=None,
            status="applied",
            benefit_snapshot_json={
                "invited_user_id": invited_user_id,
                "invited_user_email": invited_user.get("email"),
                "invited_user_display_name": invited_user.get("display_name"),
                "invite_code": binding.get("invite_code"),
                "reward_points": reward_points,
                "rule_code": reward_rule.get("rule_code"),
            },
        )
        if claim_row is None:
            _mark_referral_binding_rewarded(conn, invited_user_id, rewarded=True)
            return None

    ledger_entry = None
    updated_account = None
    if reward_points > 0:
        updated_account, ledger_entry = _grant_points_with_ledger(
            conn=conn,
            user_id=binding["inviter_user_id"],
            points=reward_points,
            entry_type="promotion_reward",
            event_type="referral_inviter_reward",
            reference_id=invited_user_id,
            description="inviter reward points",
            meta_json={
                "points_price_version": POINTS_PRICE_VERSION,
                "invite_code": binding.get("invite_code"),
                "invited_user_id": invited_user_id,
                "promotion_rule_code": reward_rule.get("rule_code") if reward_rule else None,
            },
            granted_points=reward_points,
        )
    _mark_referral_binding_rewarded(conn, invited_user_id, rewarded=True)
    return {
        "binding": binding,
        "points_granted": reward_points,
        "points_account": updated_account,
        "ledger_entry": ledger_entry,
    }


def _ensure_user_credit_account_state(conn, user: RequestUser) -> UserCreditAccount:
    if _is_guest_daily_quota_user(user):
        return _apply_guest_daily_quota_if_needed(conn, user)
    account = _grant_signup_gift_if_needed(conn, user.user_id)
    _grant_referral_inviter_reward_if_needed(conn, user.user_id)
    return account


# ---------------------------------------------------------------------------
# Promotions & billing packages
# ---------------------------------------------------------------------------

def _seed_promotion_rules(conn) -> None:
    for rule in DEFAULT_PROMOTION_RULES:
        _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.promotion_rule (
                rule_code, rule_name, rule_type, status, target_product_type,
                target_package_codes, benefit_type, benefit_value, criteria_json,
                meta_json, display_order, start_at, end_at, created_at, updated_at
            ) VALUES (%s, %s, %s, 'active', %s, %s, %s, %s, %s, %s, %s, NULL, NULL, NOW(), NOW())
            ON CONFLICT (rule_code) DO UPDATE SET
                rule_name = EXCLUDED.rule_name,
                rule_type = EXCLUDED.rule_type,
                status = 'active',
                target_product_type = EXCLUDED.target_product_type,
                target_package_codes = EXCLUDED.target_package_codes,
                benefit_type = EXCLUDED.benefit_type,
                benefit_value = EXCLUDED.benefit_value,
                criteria_json = EXCLUDED.criteria_json,
                meta_json = EXCLUDED.meta_json,
                display_order = EXCLUDED.display_order,
                updated_at = NOW()
            RETURNING rule_code
            """,
            [
                rule["rule_code"],
                rule["rule_name"],
                rule["rule_type"],
                rule.get("target_product_type"),
                psycopg2.extras.Json(rule.get("target_package_codes") or []),
                rule["benefit_type"],
                rule["benefit_value"],
                psycopg2.extras.Json(rule.get("criteria_json") or {}),
                psycopg2.extras.Json(rule.get("meta_json") or {}),
                rule["display_order"],
            ],
        )


def _list_active_promotion_rules(conn, rule_types: list[str] | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT rule_code, rule_name, rule_type, status, target_product_type,
               target_package_codes, benefit_type, benefit_value, criteria_json,
               meta_json, display_order, start_at, end_at, created_at, updated_at
        FROM app.promotion_rule
        WHERE status = 'active'
          AND (start_at IS NULL OR start_at <= NOW())
          AND (end_at IS NULL OR end_at >= NOW())
    """
    params: list[Any] = []
    if rule_types:
        sql += " AND rule_type = ANY(%s)"
        params.append(rule_types)
    sql += " ORDER BY display_order ASC, rule_code ASC"
    return _run_pg_dict_query(conn, sql, params)


def _create_promotion_claim(
    conn,
    *,
    rule_code: str,
    user_id: str,
    claim_key: str,
    order_id: str | None,
    status: str,
    benefit_snapshot_json: dict[str, Any],
) -> dict[str, Any] | None:
    rows = _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.promotion_claim (
            claim_id, rule_code, user_id, order_id, claim_key, status,
            benefit_snapshot_json, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
        ON CONFLICT (rule_code, claim_key) DO NOTHING
        RETURNING claim_id, rule_code, user_id, order_id, claim_key, status,
                  benefit_snapshot_json, created_at, updated_at
        """,
        [
            _generate_id("promo_claim"),
            rule_code,
            user_id,
            order_id,
            claim_key,
            status,
            psycopg2.extras.Json(benefit_snapshot_json),
        ],
    )
    return rows[0] if rows else None


def _list_user_promotion_claims(conn, user_id: str) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT claim_id, rule_code, user_id, order_id, claim_key, status,
               benefit_snapshot_json, created_at, updated_at
        FROM app.promotion_claim
        WHERE user_id = %s
        ORDER BY created_at DESC, claim_id DESC
        """,
        [user_id],
    )


def _resolve_signup_gift_points(conn) -> tuple[int, dict[str, Any] | None]:
    rules = _list_active_promotion_rules(conn, ["signup_reward"])
    if not rules:
        return SIGNUP_GIFT_POINTS, None
    rule = rules[0]
    if rule.get("benefit_type") != "points_bonus":
        return SIGNUP_GIFT_POINTS, rule
    return max(0, int(rule.get("benefit_value") or 0)), rule


def _sum_paid_recharge_amount_cents(conn, user_id: str) -> int:
    row = _fetch_optional_one(
        conn,
        """
        SELECT COALESCE(SUM(amount_cents), 0) AS total_cents
        FROM app.payment_order
        WHERE user_id = %s
          AND product_type = 'credit_pack'
          AND status = 'paid'
        """,
        [user_id],
    )
    return int((row or {}).get("total_cents", 0) or 0)


def _has_paid_monthly_subscription(conn, user_id: str) -> bool:
    row = _fetch_optional_one(
        conn,
        """
        SELECT order_id
        FROM app.payment_order
        WHERE user_id = %s
          AND product_type = 'monthly_subscription'
          AND status = 'paid'
        LIMIT 1
        """,
        [user_id],
    )
    return row is not None


def _package_zone_code(package: dict[str, Any]) -> str:
    meta = package.get("meta_json") or {}
    zone_code = str(meta.get("zone_code") or "").strip()
    if zone_code:
        return zone_code
    if package.get("product_type") == "monthly_subscription":
        return "monthly_zone"
    return "recharge_zone"


def _promotion_targets_package(rule: dict[str, Any], package: dict[str, Any]) -> bool:
    target_product_type = (rule.get("target_product_type") or "").strip()
    if target_product_type and target_product_type != package.get("product_type"):
        return False
    target_package_codes = rule.get("target_package_codes") or []
    if target_package_codes and package.get("package_code") not in set(target_package_codes):
        return False
    return True


def _format_cny(cents: int) -> str:
    amount = cents / 100
    if cents % 100 == 0:
        return f"{int(amount)}元"
    return f"{amount:.1f}元"


def _build_payment_order_snapshot(
    conn,
    *,
    user_id: str,
    package: dict[str, Any],
    order_id: str,
) -> dict[str, Any]:
    active_rules = _list_active_promotion_rules(conn)
    user_claims = _list_user_promotion_claims(conn, user_id)
    claimed_rule_codes = {str(row.get("rule_code") or "") for row in user_claims}
    list_amount_cents = int(package.get("price_cents") or 0)
    discount_amount_cents = 0
    payable_amount_cents = list_amount_cents
    applied_promotions: list[dict[str, Any]] = []
    reward_promotions: list[dict[str, Any]] = []

    if package.get("product_type") == "monthly_subscription":
        first_discount_used = _has_paid_monthly_subscription(conn, user_id)
        for rule in active_rules:
            if rule.get("rule_type") != "first_subscription_discount":
                continue
            if not _promotion_targets_package(rule, package):
                continue
            if first_discount_used or rule["rule_code"] in claimed_rule_codes:
                continue
            discount_amount_cents = (list_amount_cents * int(rule.get("benefit_value") or 0)) // 10000
            payable_amount_cents = max(0, list_amount_cents - discount_amount_cents)
            applied_promotions.append(
                {
                    "rule_code": rule["rule_code"],
                    "rule_name": rule["rule_name"],
                    "rule_type": rule["rule_type"],
                    "benefit_type": rule["benefit_type"],
                    "benefit_value": int(rule.get("benefit_value") or 0),
                    "discount_amount_cents": discount_amount_cents,
                    "display_text": (rule.get("meta_json") or {}).get("display_text") or rule["rule_name"],
                    "claim_key": user_id,
                }
            )
            break

    if package.get("product_type") == "credit_pack":
        current_paid_recharge_amount_cents = _sum_paid_recharge_amount_cents(conn, user_id)
        projected_paid_recharge_amount_cents = current_paid_recharge_amount_cents + payable_amount_cents
        for rule in active_rules:
            if rule.get("rule_type") == "recharge_bonus_single" and _promotion_targets_package(rule, package):
                reward_promotions.append(
                    {
                        "rule_code": rule["rule_code"],
                        "rule_name": rule["rule_name"],
                        "rule_type": rule["rule_type"],
                        "benefit_type": rule["benefit_type"],
                        "benefit_value": int(rule.get("benefit_value") or 0),
                        "reward_points": int(rule.get("benefit_value") or 0),
                        "display_text": (rule.get("meta_json") or {}).get("display_text") or rule["rule_name"],
                        "claim_key": order_id,
                    }
                )
            if rule.get("rule_type") == "recharge_bonus_cumulative" and _promotion_targets_package(rule, package):
                threshold_paid_amount_cents = int((rule.get("criteria_json") or {}).get("threshold_paid_amount_cents") or 0)
                if threshold_paid_amount_cents <= 0:
                    continue
                if rule["rule_code"] in claimed_rule_codes:
                    continue
                if current_paid_recharge_amount_cents < threshold_paid_amount_cents <= projected_paid_recharge_amount_cents:
                    reward_promotions.append(
                        {
                            "rule_code": rule["rule_code"],
                            "rule_name": rule["rule_name"],
                            "rule_type": rule["rule_type"],
                            "benefit_type": rule["benefit_type"],
                            "benefit_value": int(rule.get("benefit_value") or 0),
                            "reward_points": int(rule.get("benefit_value") or 0),
                            "threshold_paid_amount_cents": threshold_paid_amount_cents,
                            "display_text": (rule.get("meta_json") or {}).get("display_text") or rule["rule_name"],
                            "claim_key": f"{user_id}:{threshold_paid_amount_cents}",
                        }
                    )
    return {
        "pricing_version": POINTS_PRICE_VERSION,
        "zone_code": _package_zone_code(package),
        "package_code": package["package_code"],
        "package_name": package["package_name"],
        "pricing": {
            "list_amount_cents": list_amount_cents,
            "discount_amount_cents": discount_amount_cents,
            "payable_amount_cents": payable_amount_cents,
            "points_amount": int(package.get("points_amount") or 0),
        },
        "applied_promotions": applied_promotions,
        "reward_promotions": reward_promotions,
    }


def _build_catalog_offer(
    conn,
    *,
    user_id: str,
    package: dict[str, Any],
) -> dict[str, Any]:
    snapshot = _build_payment_order_snapshot(
        conn,
        user_id=user_id,
        package=package,
        order_id=f"preview:{package['package_code']}",
    )
    pricing = snapshot["pricing"]
    reward_points_preview = sum(int(item.get("reward_points") or 0) for item in (snapshot.get("reward_promotions") or []))
    return {
        "package_code": package["package_code"],
        "package_name": package["package_name"],
        "product_type": package["product_type"],
        "points_amount": int(package.get("points_amount") or 0),
        "period_days": int(package.get("period_days") or 0),
        "display_order": int(package.get("display_order") or 0),
        "status": package.get("status"),
        "meta_json": package.get("meta_json") or {},
        "zone_code": snapshot["zone_code"],
        "pricing": {
            **pricing,
            "list_amount_label": _format_cny(int(pricing["list_amount_cents"])),
            "payable_amount_label": _format_cny(int(pricing["payable_amount_cents"])),
            "discount_amount_label": _format_cny(int(pricing["discount_amount_cents"])),
        },
        "applied_promotions": snapshot.get("applied_promotions") or [],
        "reward_promotions": snapshot.get("reward_promotions") or [],
        "reward_points_preview": reward_points_preview,
        "total_points_if_paid": int(package.get("points_amount") or 0) + reward_points_preview,
    }


def _build_billing_catalog(conn, user_id: str) -> dict[str, Any]:
    packages = _list_billing_packages(conn)
    user_claims = _list_user_promotion_claims(conn, user_id)
    claimed_rule_codes = {str(row.get("rule_code") or "") for row in user_claims}
    signup_bonus_points, signup_rule = _resolve_signup_gift_points(conn)
    signup_received = _fetch_optional_one(
        conn,
        """
        SELECT entry_id
        FROM app.credit_ledger_entry
        WHERE user_id = %s AND entry_type = 'signup_gift'
        LIMIT 1
        """,
        [user_id],
    ) is not None
    first_subscription_discount_used = _has_paid_monthly_subscription(conn, user_id) or (
        "first_subscription_monthly_90_off" in claimed_rule_codes
    )
    paid_recharge_amount_cents = _sum_paid_recharge_amount_cents(conn, user_id)
    cumulative_rules = _list_active_promotion_rules(conn, ["recharge_bonus_cumulative"])
    monthly_packages = [package for package in packages if _package_zone_code(package) == "monthly_zone"]
    recharge_packages = [package for package in packages if _package_zone_code(package) == "recharge_zone"]
    cumulative_rewards = []
    for rule in cumulative_rules:
        threshold_paid_amount_cents = int((rule.get("criteria_json") or {}).get("threshold_paid_amount_cents") or 0)
        achieved = paid_recharge_amount_cents >= threshold_paid_amount_cents > 0
        cumulative_rewards.append(
            {
                "rule_code": rule["rule_code"],
                "rule_name": rule["rule_name"],
                "threshold_paid_amount_cents": threshold_paid_amount_cents,
                "threshold_paid_amount_label": _format_cny(threshold_paid_amount_cents),
                "reward_points": int(rule.get("benefit_value") or 0),
                "display_text": (rule.get("meta_json") or {}).get("display_text") or rule["rule_name"],
                "achieved": achieved,
                "claimed": rule["rule_code"] in claimed_rule_codes,
                "remaining_amount_cents": max(0, threshold_paid_amount_cents - paid_recharge_amount_cents),
            }
        )
    return {
        "monthly_zone": {
            "zone_code": "monthly_zone",
            "title": "月包区",
            "packages": [
                _build_catalog_offer(conn, user_id=user_id, package=package)
                for package in monthly_packages
            ],
        },
        "recharge_zone": {
            "zone_code": "recharge_zone",
            "title": "充值区",
            "base_rate": {"points": 100, "currency_cny": 1},
            "packages": [
                _build_catalog_offer(conn, user_id=user_id, package=package)
                for package in recharge_packages
            ],
            "cumulative_rewards": cumulative_rewards,
        },
        "newcomer_zone": {
            "zone_code": "newcomer_zone",
            "title": "新用户区",
            "signup_bonus_points": signup_bonus_points,
            "signup_bonus_received": signup_received,
            "signup_bonus_rule": signup_rule,
            "first_subscription_discount_eligible": not first_subscription_discount_used,
            "first_subscription_discount_used": first_subscription_discount_used,
            "first_subscription_discount_display": "首次订阅月包首月 1 折",
        },
    }


def _apply_order_promotions_after_payment(
    conn,
    *,
    order_row: dict[str, Any],
    package: dict[str, Any],
    provider: str,
    provider_trade_no: str | None,
    updated_account: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    promotion_snapshot = dict(order_row.get("promotion_snapshot_json") or {})
    promotion_results: list[dict[str, Any]] = []
    reward_promotions = promotion_snapshot.get("reward_promotions") or []
    applied_promotions = promotion_snapshot.get("applied_promotions") or []
    current_account = updated_account

    for promo in reward_promotions:
        claim_row = _create_promotion_claim(
            conn,
            rule_code=str(promo.get("rule_code") or ""),
            user_id=order_row["user_id"],
            claim_key=str(promo.get("claim_key") or order_row["order_id"]),
            order_id=order_row["order_id"],
            status="applied",
            benefit_snapshot_json={
                **promo,
                "package_code": package["package_code"],
                "provider": provider,
                "provider_trade_no": provider_trade_no,
                "payment_order_id": order_row["order_id"],
            },
        )
        if claim_row is None:
            promotion_results.append(
                {
                    "promotion": promo,
                    "status": "already_applied",
                    "points_granted": 0,
                    "ledger_entry": None,
                }
            )
            continue

        reward_points = int(promo.get("reward_points") or 0)
        ledger_entry = None
        if reward_points > 0:
            current_account, ledger_entry = _grant_points_with_ledger(
                conn=conn,
                user_id=order_row["user_id"],
                points=reward_points,
                entry_type="promotion_reward",
                event_type=str(promo.get("rule_type") or "promotion_reward"),
                reference_id=str(promo.get("claim_key") or order_row["order_id"]),
                description=str(promo.get("display_text") or promo.get("rule_name") or "promotion reward"),
                meta_json={
                    **promo,
                    "points_price_version": POINTS_PRICE_VERSION,
                    "provider": provider,
                    "provider_trade_no": provider_trade_no,
                    "payment_order_id": order_row["order_id"],
                },
                granted_points=reward_points,
            )
        promotion_results.append(
            {
                "promotion": promo,
                "status": "applied",
                "points_granted": reward_points,
                "ledger_entry": ledger_entry,
            }
        )

    for promo in applied_promotions:
        claim_row = _create_promotion_claim(
            conn,
            rule_code=str(promo.get("rule_code") or ""),
            user_id=order_row["user_id"],
            claim_key=str(promo.get("claim_key") or order_row["user_id"]),
            order_id=order_row["order_id"],
            status="applied",
            benefit_snapshot_json={
                **promo,
                "package_code": package["package_code"],
                "provider": provider,
                "provider_trade_no": provider_trade_no,
                "payment_order_id": order_row["order_id"],
            },
        )
        promotion_results.append(
            {
                "promotion": promo,
                "status": "applied" if claim_row is not None else "already_recorded",
                "points_granted": 0,
                "ledger_entry": None,
            }
        )
    return current_account, promotion_results


def _apply_user_plan_tier_from_package(conn, user_id: str, package: dict[str, Any]) -> None:
    tier_key = str((package.get("meta_json") or {}).get("tier_key") or "").strip().lower()
    if not tier_key:
        return
    _run_pg_dict_query(
        conn,
        """
        UPDATE app.app_user
        SET plan_tier = %s,
            updated_at = NOW()
        WHERE user_id = %s
        RETURNING user_id
        """,
        [tier_key, user_id],
    )

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
                status = 'active',
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
    _run_pg_dict_query(
        conn,
        """
        UPDATE app.billing_package
        SET status = 'disabled',
            updated_at = NOW()
        WHERE package_code = ANY(%s)
        RETURNING package_code
        """,
        [list(_LEGACY_BILLING_PACKAGE_CODES)],
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
