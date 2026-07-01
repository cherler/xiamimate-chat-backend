"""Notification domain — portal notification persistence and read-state."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from data_platform.chat_backend.infra.settings import _generate_id
from data_platform.chat_backend.infra.postgres import _run_pg_dict_query

_NOTIFICATION_CATEGORIES = {"system", "user"}
_NOTIFICATION_LEVELS = {"info", "success", "warning", "error"}
_LOW_BALANCE_NOTIFICATION_KEY = "balance_low_threshold_500"
_BROADCAST_TARGET_SCOPES = {"all_active"}


def _normalize_notification_category(value: str) -> str:
    normalized = str(value or "system").strip().lower() or "system"
    return normalized if normalized in _NOTIFICATION_CATEGORIES else "system"



def _normalize_notification_level(value: str) -> str:
    normalized = str(value or "info").strip().lower() or "info"
    return normalized if normalized in _NOTIFICATION_LEVELS else "info"


def _normalize_broadcast_target_scope(value: str) -> str:
    normalized = str(value or "all_active").strip().lower() or "all_active"
    return normalized if normalized in _BROADCAST_TARGET_SCOPES else "all_active"



def _upsert_user_notification(
    conn,
    *,
    user_id: str,
    notification_key: str,
    category: str,
    tag: str,
    level: str,
    title: str,
    body: str,
    event_type: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    action_url: str | None = None,
    occurred_at: Any | None = None,
) -> dict[str, Any]:
    return _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.user_notification (
            notification_id, user_id, notification_key, category, tag, level, title, body,
            event_type, resource_type, resource_id, action_url, occurred_at, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()), NOW(), NOW())
        ON CONFLICT (user_id, notification_key) DO UPDATE SET
            category = EXCLUDED.category,
            tag = EXCLUDED.tag,
            level = EXCLUDED.level,
            title = EXCLUDED.title,
            body = EXCLUDED.body,
            event_type = EXCLUDED.event_type,
            resource_type = EXCLUDED.resource_type,
            resource_id = EXCLUDED.resource_id,
            action_url = EXCLUDED.action_url,
            occurred_at = EXCLUDED.occurred_at,
            updated_at = NOW()
        RETURNING notification_id, user_id, notification_key, category, tag, level, title, body,
                  event_type, resource_type, resource_id, action_url, read_at, occurred_at,
                  created_at, updated_at
        """,
        [
            _generate_id("notification"),
            user_id,
            str(notification_key or "").strip(),
            _normalize_notification_category(category),
            str(tag or "通知").strip() or "通知",
            _normalize_notification_level(level),
            str(title or "新通知").strip() or "新通知",
            str(body or "").strip(),
            str(event_type or "").strip() or None,
            str(resource_type or "").strip() or None,
            str(resource_id or "").strip() or None,
            str(action_url or "").strip() or None,
            occurred_at,
        ],
    )[0]



def _delete_user_notification_by_key(conn, user_id: str, notification_key: str) -> None:
    _run_pg_dict_query(
        conn,
        """
        DELETE FROM app.user_notification
        WHERE user_id = %s AND notification_key = %s
        RETURNING notification_id
        """,
        [user_id, notification_key],
    )



def _list_notifications_for_user(conn, user_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT notification_id, user_id, notification_key, category, tag, level, title, body,
               event_type, resource_type, resource_id, action_url, read_at, occurred_at,
               created_at, updated_at
        FROM app.user_notification
        WHERE user_id = %s
        ORDER BY occurred_at DESC, created_at DESC, notification_id DESC
        LIMIT %s
        """,
        [user_id, max(1, limit)],
    )


def _list_system_notification_broadcasts(conn, *, limit: int = 50) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT broadcast_id, operator_id, target_scope, tag, level, title, body,
               action_url, delivered_user_count, created_at, updated_at
        FROM app.system_notification_broadcast
        ORDER BY created_at DESC, broadcast_id DESC
        LIMIT %s
        """,
        [max(1, limit)],
    )


def _create_system_notification_broadcast(
    conn,
    *,
    operator_id: str,
    title: str,
    body: str,
    tag: str = "系统通知",
    level: str = "info",
    action_url: str | None = None,
    target_scope: str = "all_active",
) -> dict[str, Any]:
    return _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.system_notification_broadcast (
            broadcast_id, operator_id, target_scope, tag, level, title, body,
            action_url, delivered_user_count, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, NOW(), NOW())
        RETURNING broadcast_id, operator_id, target_scope, tag, level, title, body,
                  action_url, delivered_user_count, created_at, updated_at
        """,
        [
            _generate_id("broadcast"),
            str(operator_id or "").strip(),
            _normalize_broadcast_target_scope(target_scope),
            str(tag or "系统通知").strip() or "系统通知",
            _normalize_notification_level(level),
            str(title or "").strip(),
            str(body or "").strip(),
            str(action_url or "").strip() or None,
        ],
    )[0]


def _fanout_system_notification_broadcast(conn, broadcast: dict[str, Any]) -> dict[str, Any]:
    broadcast_id = str(broadcast.get("broadcast_id") or "").strip()
    if not broadcast_id:
        return {"delivered_user_count": 0}

    user_rows = _run_pg_dict_query(
        conn,
        """
        SELECT user_id
        FROM app.app_user
        WHERE status = 'active'
        ORDER BY created_at ASC, user_id ASC
        """,
    )
    delivered_count = 0
    for user_row in user_rows:
        user_id = str(user_row.get("user_id") or "").strip()
        if not user_id:
            continue
        _upsert_user_notification(
            conn,
            user_id=user_id,
            notification_key=f"broadcast:{broadcast_id}",
            category="system",
            tag=str(broadcast.get("tag") or "系统通知"),
            level=str(broadcast.get("level") or "info"),
            title=str(broadcast.get("title") or "系统通知"),
            body=str(broadcast.get("body") or ""),
            event_type="system_notification_broadcast",
            resource_type="system_notification_broadcast",
            resource_id=broadcast_id,
            action_url=str(broadcast.get("action_url") or "").strip() or "/portal/notifications",
            occurred_at=broadcast.get("created_at"),
        )
        delivered_count += 1

    updated_rows = _run_pg_dict_query(
        conn,
        """
        UPDATE app.system_notification_broadcast
        SET delivered_user_count = %s,
            updated_at = NOW()
        WHERE broadcast_id = %s
        RETURNING broadcast_id, operator_id, target_scope, tag, level, title, body,
                  action_url, delivered_user_count, created_at, updated_at
        """,
        [delivered_count, broadcast_id],
    )
    return updated_rows[0] if updated_rows else {"delivered_user_count": delivered_count}



def _set_notification_read_state(
    conn,
    user_id: str,
    *,
    read: bool,
    notification_ids: list[str] | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    ids = [str(item).strip() for item in (notification_ids or []) if str(item).strip()]
    normalized_category = str(category or "").strip().lower()
    if not ids and not normalized_category:
        return []

    filters = ["user_id = %s"]
    params: list[Any] = [user_id]
    if ids:
        filters.append("notification_id = ANY(%s)")
        params.append(ids)
    if normalized_category:
        filters.append("category = %s")
        params.append(_normalize_notification_category(normalized_category))

    return _run_pg_dict_query(
        conn,
        """
        UPDATE app.user_notification
        SET read_at = CASE WHEN %s THEN COALESCE(read_at, NOW()) ELSE NULL END,
            updated_at = NOW()
        WHERE %s
        RETURNING notification_id, user_id, notification_key, category, tag, level, title, body,
                  event_type, resource_type, resource_id, action_url, read_at, occurred_at,
                  created_at, updated_at
        """ % ("%s", " AND ".join(filters)),
        [read, *params],
    )



def _find_active_subscription(subscriptions: list[dict[str, Any]]) -> dict[str, Any] | None:
    now = datetime.now(timezone.utc)
    for subscription in subscriptions:
        status = str(subscription.get("status") or "").strip().lower()
        if status != "active":
            continue
        period_end = subscription.get("current_period_end")
        if isinstance(period_end, datetime) and period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=timezone.utc)
        if period_end is not None and isinstance(period_end, datetime) and period_end <= now:
            continue
        return subscription
    return None



def _sync_portal_notifications(
    conn,
    user_id: str,
    *,
    points_account: dict[str, Any],
    recent_ledger: list[dict[str, Any]],
    recent_orders: list[dict[str, Any]],
    subscriptions: list[dict[str, Any]],
) -> None:
    for ledger_row in recent_ledger:
        event_type = str(ledger_row.get("event_type") or "").strip()
        if event_type in {"recharge_bonus_single", "recharge_bonus_cumulative"}:
            entry_id = str(ledger_row.get("entry_id") or "").strip()
            reward_points = int(ledger_row.get("points_delta") or 0)
            if reward_points > 0:
                _upsert_user_notification(
                    conn,
                    user_id=user_id,
                    notification_key=f"recharge_bonus:{entry_id or ledger_row.get('reference_id') or event_type}",
                    category="system",
                    tag="赠送到账",
                    level="success",
                    title="赠送积分已到账",
                    body=f"{str(ledger_row.get('description') or '充值赠送积分')}，本次到账 {reward_points} 积分。",
                    event_type=event_type,
                    resource_type="credit_ledger_entry",
                    resource_id=entry_id or None,
                    action_url="/portal/topup",
                    occurred_at=ledger_row.get("created_at"),
                )
            continue
        if event_type == "referral_invited_reward":
            binding_id = str(ledger_row.get("reference_id") or ledger_row.get("entry_id") or "binding")
            reward_points = int(ledger_row.get("points_delta") or 0)
            _upsert_user_notification(
                conn,
                user_id=user_id,
                notification_key=f"referral_invited_reward:{binding_id}",
                category="user",
                tag="邀请奖励",
                level="success",
                title="邀请码绑定成功",
                body=f"你已绑定邀请码，系统已额外赠送 {reward_points} 积分。完成邮箱验证后，邀请人也会获得奖励。",
                event_type="referral_invited_reward",
                resource_type="credit_ledger_entry",
                resource_id=str(ledger_row.get("entry_id") or "").strip() or None,
                action_url="/portal/account",
                occurred_at=ledger_row.get("created_at"),
            )
            continue
        if event_type != "referral_inviter_reward":
            continue
        invited_user_id = str(ledger_row.get("reference_id") or "").strip() or str(ledger_row.get("entry_id") or "").strip()
        reward_points = int(ledger_row.get("points_delta") or 0)
        _upsert_user_notification(
            conn,
            user_id=user_id,
            notification_key=f"referral_inviter_reward:{invited_user_id}",
            category="user",
            tag="邀请奖励",
            level="success",
            title="邀请新用户注册成功",
            body=f"你邀请的新用户已完成注册验证，系统已赠送 {reward_points} 积分。",
            event_type="referral_inviter_reward",
            resource_type="credit_ledger_entry",
            resource_id=str(ledger_row.get("entry_id") or "").strip() or None,
            action_url="/portal/notifications",
            occurred_at=ledger_row.get("created_at"),
        )

    for order in recent_orders:
        if str(order.get("status") or "").strip().lower() != "paid":
            continue
        order_id = str(order.get("order_id") or order.get("provider_trade_no") or order.get("created_at") or "order")
        is_subscription = str(order.get("product_type") or "") == "monthly_subscription"
        _upsert_user_notification(
            conn,
            user_id=user_id,
            notification_key=("subscription_paid:" if is_subscription else "recharge_paid:") + order_id,
            category="system",
            tag="套餐开通" if is_subscription else "充值到账",
            level="success",
            title="订阅已生效" if is_subscription else "充值已到账",
            body=(
                f"{str(order.get('package_code') or '当前套餐')} 已开通，本次到账 {int(order.get('points_amount') or 0)} 积分。"
                if is_subscription else
                f"{str(order.get('package_code') or '充值订单')} 支付成功，本次到账 {int(order.get('points_amount') or 0)} 积分。"
            ),
            event_type="subscription_paid" if is_subscription else "recharge_paid",
            resource_type="payment_order",
            resource_id=str(order.get("order_id") or "").strip() or None,
            action_url="/portal/notifications",
            occurred_at=order.get("paid_at") or order.get("created_at"),
        )

    active_subscription = _find_active_subscription(subscriptions)
    if active_subscription is not None:
        subscription_id = str(active_subscription.get("subscription_id") or active_subscription.get("package_code") or "subscription")
        period_end = active_subscription.get("current_period_end")
        _upsert_user_notification(
            conn,
            user_id=user_id,
            notification_key=f"subscription_period:{subscription_id}:{period_end}",
            category="system",
            tag="套餐有效期",
            level="info",
            title="当前套餐有效中",
            body="当前套餐正在有效期内，可在“当前套餐”页查看生效时间、到期时间和月包积分清零规则。",
            event_type="subscription_period_active",
            resource_type="billing_subscription",
            resource_id=subscription_id,
            action_url="/portal/plan",
            occurred_at=active_subscription.get("current_period_start") or active_subscription.get("created_at"),
        )

    if int(points_account.get("balance_points") or 0) <= 500:
        _upsert_user_notification(
            conn,
            user_id=user_id,
            notification_key=_LOW_BALANCE_NOTIFICATION_KEY,
            category="user",
            tag="余额提醒",
            level="warning",
            title="账户余额偏低",
            body="当前可用积分低于 500，建议提前查看订阅与充值页，避免使用中断。",
            event_type="low_balance_warning",
            resource_type="user_credit_account",
            resource_id=user_id,
            action_url="/portal/topup",
            occurred_at=points_account.get("updated_at"),
        )
    else:
        _delete_user_notification_by_key(conn, user_id, _LOW_BALANCE_NOTIFICATION_KEY)
