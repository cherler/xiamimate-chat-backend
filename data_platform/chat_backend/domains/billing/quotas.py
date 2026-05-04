"""Daily quota helpers for the billing domain."""
from __future__ import annotations

from typing import Any

from data_platform.chat_backend.infra.settings import _current_quota_date, _is_guest_identity
from data_platform.chat_backend.infra.postgres import _fetch_optional_one, _run_pg_dict_query
from data_platform.chat_backend.domains.identity.models import RequestUser


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
