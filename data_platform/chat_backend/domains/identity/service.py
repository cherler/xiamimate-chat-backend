"""Identity domain — service functions.

Depends on: infra.settings, infra.postgres, identity.models,
            api_keys.service, billing.service.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from data_platform.chat_backend.infra.settings import (
    DEFAULT_USER_EMAIL,
    DEFAULT_USER_ID,
    DEFAULT_USER_NAME,
    DEMO_FALLBACK_ENABLED,
    USER_ID_HEADER_NAME,
    USER_EMAIL_HEADER_NAME,
    USER_NAME_HEADER_NAME,
    _resolve_initial_plan_tier,
)
from data_platform.chat_backend.infra.postgres import (
    _fetch_optional_one,
    _run_pg_dict_query,
)
from data_platform.chat_backend.domains.identity.models import RequestUser
from data_platform.chat_backend.domains.api_keys.models import UserAPIKey
from data_platform.chat_backend.domains.api_keys.service import _ensure_user_api_key
from data_platform.chat_backend.domains.billing.models import UserCreditAccount
from data_platform.chat_backend.domains.billing.service import _ensure_user_credit_account_state


def _normalize_user_headers(request: Request) -> tuple[str, str, str]:
    raw_user_id = (request.headers.get(USER_ID_HEADER_NAME) or "").strip()
    raw_email = (request.headers.get(USER_EMAIL_HEADER_NAME) or "").strip()
    raw_display_name = (request.headers.get(USER_NAME_HEADER_NAME) or "").strip()

    if not raw_user_id and not DEMO_FALLBACK_ENABLED:
        raise HTTPException(status_code=401, detail=f"missing header: {USER_ID_HEADER_NAME}")

    user_id = raw_user_id or DEFAULT_USER_ID
    email = raw_email or DEFAULT_USER_EMAIL
    display_name = raw_display_name or DEFAULT_USER_NAME
    if not user_id:
        raise HTTPException(status_code=401, detail="missing user id")
    if not email:
        email = DEFAULT_USER_EMAIL
    if not display_name:
        display_name = DEFAULT_USER_NAME
    return user_id, email, display_name


def _upsert_user_row(
    conn,
    user_id: str,
    email: str,
    display_name: str,
    plan_tier: str | None = None,
) -> RequestUser:
    effective_plan_tier = (plan_tier or "").strip() or _resolve_initial_plan_tier(
        user_id=user_id,
        email=email,
        display_name=display_name,
    )
    rows = _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.app_user (
            user_id, email, display_name, status, plan_tier, created_at, updated_at
        ) VALUES (
            %s, %s, %s, 'active', %s, NOW(), NOW()
        )
        ON CONFLICT (user_id) DO UPDATE SET
            email = EXCLUDED.email,
            display_name = EXCLUDED.display_name,
            updated_at = NOW()
        RETURNING user_id, email, display_name, status, plan_tier, created_at, updated_at
        """,
        [user_id, email, display_name, effective_plan_tier],
    )
    row = rows[0]
    return RequestUser(**row)


def _upsert_user(conn, request: Request) -> RequestUser:
    user_id, email, display_name = _normalize_user_headers(request)
    return _upsert_user_row(conn, user_id=user_id, email=email, display_name=display_name)


def _fetch_user(conn, user_id: str) -> RequestUser:
    row = _fetch_optional_one(
        conn,
        """
        SELECT user_id, email, display_name, status, plan_tier, created_at, updated_at
        FROM app.app_user
        WHERE user_id = %s
        LIMIT 1
        """,
        [user_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"user not found: {user_id}")
    return RequestUser(**row)


def _ensure_user_record(
    conn,
    user_id: str,
    email: str | None = None,
    display_name: str | None = None,
    plan_tier: str | None = None,
) -> RequestUser:
    existing = _fetch_optional_one(
        conn,
        """
        SELECT user_id, email, display_name, status, plan_tier, created_at, updated_at
        FROM app.app_user
        WHERE user_id = %s
        LIMIT 1
        """,
        [user_id],
    )
    if existing is not None:
        return RequestUser(**existing)
    safe_email = (email or f"{user_id}@local").strip()
    safe_display_name = (display_name or user_id).strip() or user_id
    return _upsert_user_row(
        conn,
        user_id=user_id,
        email=safe_email,
        display_name=safe_display_name,
        plan_tier=plan_tier,
    )


def _provision_user_identity(conn, request: Request) -> tuple[RequestUser, UserAPIKey, UserCreditAccount]:
    user = _upsert_user(conn, request)
    user_api_key = _ensure_user_api_key(conn, user)
    credit_account = _ensure_user_credit_account_state(conn, user)
    return user, user_api_key, credit_account
