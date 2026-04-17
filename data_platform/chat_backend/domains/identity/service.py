"""Identity domain — service functions.

Depends on: infra.settings, infra.postgres, identity.models,
            api_keys.service, billing.service.
"""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, Request

from data_platform.chat_backend.infra.settings import (
    DEFAULT_USER_EMAIL,
    DEFAULT_USER_ID,
    DEFAULT_USER_NAME,
    DEMO_FALLBACK_ENABLED,
    EMAIL_VERIFICATION_CODE_TTL_SECONDS,
    EMAIL_VERIFICATION_RESEND_INTERVAL_SECONDS,
    USER_ID_HEADER_NAME,
    USER_EMAIL_HEADER_NAME,
    USER_NAME_HEADER_NAME,
    _generate_id,
    _generate_invite_code,
    _generate_numeric_code,
    _hash_text,
    _portal_email_verification_gate_enabled,
    _resolve_initial_plan_tier,
    _send_email_message,
    _utc_now,
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


_APP_USER_SELECT = """
    SELECT user_id, email, display_name, status, plan_tier,
           created_at, updated_at, invite_code, email_verified_at
    FROM app.app_user
"""

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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


def _validate_email_address(email: str) -> str:
    normalized = (email or "").strip().lower()
    if not normalized or not _EMAIL_PATTERN.match(normalized):
        raise HTTPException(status_code=400, detail="invalid email address")
    return normalized


def _ensure_invite_code_for_row(conn, row: dict[str, Any]) -> dict[str, Any]:
    if row.get("invite_code"):
        return row
    invite_code = _generate_invite_code()
    updated = _run_pg_dict_query(
        conn,
        """
        UPDATE app.app_user
        SET invite_code = %s,
            updated_at = NOW()
        WHERE user_id = %s
          AND invite_code IS NULL
        RETURNING user_id, email, display_name, status, plan_tier,
                  created_at, updated_at, invite_code, email_verified_at
        """,
        [invite_code, row["user_id"]],
    )
    if updated:
        return updated[0]
    refetched = _fetch_optional_one(conn, _APP_USER_SELECT + " WHERE user_id = %s LIMIT 1", [row["user_id"]])
    if refetched is None:
        raise HTTPException(status_code=404, detail=f"user not found: {row['user_id']}")
    return refetched


def _build_email_verification_code_hash(user_id: str, email: str, code: str) -> str:
    return _hash_text(f"email-verify:{user_id}:{email.strip().lower()}:{code.strip()}")


def _upsert_user_row(
    conn,
    user_id: str,
    email: str,
    display_name: str,
    plan_tier: str | None = None,
) -> RequestUser:
    normalized_email = (email or "").strip().lower()
    invite_code = _generate_invite_code()
    effective_plan_tier = (plan_tier or "").strip() or _resolve_initial_plan_tier(
        user_id=user_id,
        email=normalized_email,
        display_name=display_name,
    )
    rows = _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.app_user (
            user_id, email, display_name, status, plan_tier, invite_code, email_verified_at, created_at, updated_at
        ) VALUES (
            %s, %s, %s, 'active', %s, %s, NULL, NOW(), NOW()
        )
        ON CONFLICT (user_id) DO UPDATE SET
            email = EXCLUDED.email,
            display_name = EXCLUDED.display_name,
            invite_code = COALESCE(app.app_user.invite_code, EXCLUDED.invite_code),
            email_verified_at = CASE
                WHEN app.app_user.email IS DISTINCT FROM EXCLUDED.email THEN NULL
                ELSE app.app_user.email_verified_at
            END,
            updated_at = NOW()
        RETURNING user_id, email, display_name, status, plan_tier,
                  created_at, updated_at, invite_code, email_verified_at
        """,
        [user_id, normalized_email, display_name, effective_plan_tier, invite_code],
    )
    row = _ensure_invite_code_for_row(conn, rows[0])
    return RequestUser(**row)


def _upsert_user(conn, request: Request) -> RequestUser:
    user_id, email, display_name = _normalize_user_headers(request)
    return _upsert_user_row(conn, user_id=user_id, email=email, display_name=display_name)


def _fetch_user(conn, user_id: str) -> RequestUser:
    row = _fetch_optional_one(
        conn,
        _APP_USER_SELECT + " WHERE user_id = %s LIMIT 1",
        [user_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"user not found: {user_id}")
    row = _ensure_invite_code_for_row(conn, row)
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
        _APP_USER_SELECT + " WHERE user_id = %s LIMIT 1",
        [user_id],
    )
    if existing is not None:
        if email or display_name:
            return _upsert_user_row(
                conn,
                user_id=user_id,
                email=(email or existing.get("email") or f"{user_id}@local").strip(),
                display_name=(display_name or existing.get("display_name") or user_id).strip() or user_id,
                plan_tier=plan_tier or existing.get("plan_tier"),
            )
        existing = _ensure_invite_code_for_row(conn, existing)
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


def _request_email_verification(conn, user_id: str) -> dict[str, Any]:
    user = _fetch_user(conn, user_id)
    email = _validate_email_address(user.email)
    if user.email_verified_at is not None:
        return {
            "email": email,
            "email_verified": True,
            "email_verified_at": user.email_verified_at,
            "expires_in_seconds": 0,
        }

    latest = _fetch_optional_one(
        conn,
        """
        SELECT challenge_id, user_id, email, expires_at, consumed_at, last_sent_at, created_at
        FROM app.email_verification_challenge
        WHERE user_id = %s
          AND email = %s
          AND purpose = 'signup_email_verify'
          AND consumed_at IS NULL
          AND expires_at >= NOW()
        ORDER BY created_at DESC
        LIMIT 1
        """,
        [user_id, email],
    )
    now = _utc_now()
    if latest and latest.get("last_sent_at") is not None:
        cooldown = (now - latest["last_sent_at"]).total_seconds()
        if cooldown < EMAIL_VERIFICATION_RESEND_INTERVAL_SECONDS:
            remaining = int(EMAIL_VERIFICATION_RESEND_INTERVAL_SECONDS - cooldown)
            raise HTTPException(status_code=429, detail=f"请在 {remaining} 秒后再重新发送验证码")

    code = _generate_numeric_code(6)
    challenge_id = _generate_id("email_verify")
    expires_at = now + timedelta(seconds=EMAIL_VERIFICATION_CODE_TTL_SECONDS)
    _run_pg_dict_query(
        conn,
        """
        UPDATE app.email_verification_challenge
        SET consumed_at = NOW(),
            updated_at = NOW()
        WHERE user_id = %s
          AND purpose = 'signup_email_verify'
          AND consumed_at IS NULL
        RETURNING challenge_id
        """,
        [user_id],
    )
    _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.email_verification_challenge (
            challenge_id, user_id, email, purpose, code_hash, expires_at,
            consumed_at, last_sent_at, created_at, updated_at
        ) VALUES (%s, %s, %s, 'signup_email_verify', %s, %s, NULL, NOW(), NOW(), NOW())
        RETURNING challenge_id, email, expires_at, last_sent_at, created_at
        """,
        [challenge_id, user_id, email, _build_email_verification_code_hash(user_id, email, code), expires_at],
    )
    try:
        _send_email_message(
            email,
            "虾密小助手邮箱验证码",
            (
                f"你好，{user.display_name or user.user_id}。\n\n"
                f"你的邮箱验证码是：{code}\n"
                f"验证码 {EMAIL_VERIFICATION_CODE_TTL_SECONDS // 60} 分钟内有效。\n\n"
                "如果这不是你本人操作，请忽略此邮件。"
            ),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"failed to send verification email: {exc}") from exc
    return {
        "email": email,
        "email_verified": False,
        "email_verified_at": None,
        "challenge_id": challenge_id,
        "expires_in_seconds": EMAIL_VERIFICATION_CODE_TTL_SECONDS,
    }


def _confirm_email_verification(conn, user_id: str, code: str) -> RequestUser:
    user = _fetch_user(conn, user_id)
    email = _validate_email_address(user.email)
    normalized_code = (code or "").strip()
    if not normalized_code:
        raise HTTPException(status_code=400, detail="missing email verification code")
    if user.email_verified_at is not None:
        return user

    challenge = _fetch_optional_one(
        conn,
        """
        SELECT challenge_id, user_id, email, code_hash, expires_at, consumed_at, created_at
        FROM app.email_verification_challenge
        WHERE user_id = %s
          AND email = %s
          AND purpose = 'signup_email_verify'
          AND consumed_at IS NULL
          AND expires_at >= NOW()
        ORDER BY created_at DESC
        LIMIT 1
        """,
        [user_id, email],
    )
    if challenge is None:
        raise HTTPException(status_code=400, detail="验证码不存在或已过期，请重新获取")
    if not challenge.get("code_hash") or challenge["code_hash"] != _build_email_verification_code_hash(user_id, email, normalized_code):
        raise HTTPException(status_code=400, detail="验证码错误")

    _run_pg_dict_query(
        conn,
        """
        UPDATE app.email_verification_challenge
        SET consumed_at = NOW(),
            updated_at = NOW()
        WHERE challenge_id = %s
        RETURNING challenge_id
        """,
        [challenge["challenge_id"]],
    )
    updated = _run_pg_dict_query(
        conn,
        """
        UPDATE app.app_user
        SET email_verified_at = NOW(),
            updated_at = NOW()
        WHERE user_id = %s
        RETURNING user_id, email, display_name, status, plan_tier,
                  created_at, updated_at, invite_code, email_verified_at
        """,
        [user_id],
    )[0]
    return RequestUser(**updated)


def _fetch_user_referral_binding(conn, user_id: str) -> dict[str, Any] | None:
    return _fetch_optional_one(
        conn,
        """
        SELECT b.binding_id, b.inviter_user_id, b.invited_user_id, b.invite_code,
               b.status, b.activated_at, b.rewarded_at, b.created_at, b.updated_at,
               inviter.display_name AS inviter_display_name,
               inviter.email AS inviter_email
        FROM app.user_referral_binding b
        JOIN app.app_user inviter ON inviter.user_id = b.inviter_user_id
        WHERE b.invited_user_id = %s
        LIMIT 1
        """,
        [user_id],
    )


def _bind_user_referral(conn, user_id: str, invite_code: str) -> dict[str, Any]:
    normalized_invite_code = (invite_code or "").strip().upper()
    if not normalized_invite_code:
        raise HTTPException(status_code=400, detail="missing invite code")

    user = _fetch_user(conn, user_id)
    if user.email_verified_at is not None:
        raise HTTPException(status_code=409, detail="邮箱已验证，当前账号不能再绑定邀请码")
    inviter = _fetch_optional_one(
        conn,
        _APP_USER_SELECT + " WHERE invite_code = %s LIMIT 1",
        [normalized_invite_code],
    )
    if inviter is None:
        raise HTTPException(status_code=404, detail="invite code not found")
    if inviter["user_id"] == user_id:
        raise HTTPException(status_code=400, detail="不能绑定自己的邀请码")

    existing = _fetch_user_referral_binding(conn, user_id)
    if existing is not None:
        if existing.get("inviter_user_id") != inviter["user_id"]:
            raise HTTPException(status_code=409, detail="当前账号已绑定其他邀请人")
        return existing

    _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.user_referral_binding (
            binding_id, inviter_user_id, invited_user_id, invite_code,
            status, activated_at, rewarded_at, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, 'bound', NULL, NULL, NOW(), NOW())
        RETURNING binding_id
        """,
        [_generate_id("ref_bind"), inviter["user_id"], user_id, normalized_invite_code],
    )
    binding = _fetch_user_referral_binding(conn, user_id)
    if binding is None:
        raise HTTPException(status_code=500, detail="failed to bind invite code")
    return binding


def _build_identity_verification_summary(conn, user_id: str) -> dict[str, Any]:
    user = _fetch_user(conn, user_id)
    binding = _fetch_user_referral_binding(conn, user_id)
    email_verified = user.email_verified_at is not None
    return {
        "email": user.email,
        "email_verified": email_verified,
        "email_verified_at": user.email_verified_at,
        "email_verification_required_before_portal_use": _portal_email_verification_gate_enabled(),
        "invite_code": user.invite_code,
        "invited_by": binding,
        "can_bind_invite_code": binding is None and not email_verified,
    }


def _provision_user_identity(conn, request: Request) -> tuple[RequestUser, UserAPIKey, UserCreditAccount]:
    user = _upsert_user(conn, request)
    user_api_key = _ensure_user_api_key(conn, user)
    credit_account = _ensure_user_credit_account_state(conn, user)
    return user, user_api_key, credit_account
