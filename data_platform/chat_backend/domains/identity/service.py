"""Identity domain — service functions.

Depends on: infra.settings, infra.postgres, identity.models,
            api_keys.service, billing.service.
"""
from __future__ import annotations

import logging
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from html import escape as html_escape
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import bcrypt
from fastapi import HTTPException, Request

from data_platform.chat_backend.infra.settings import (
    DEFAULT_USER_EMAIL,
    DEFAULT_USER_ID,
    DEFAULT_USER_NAME,
    DEMO_FALLBACK_ENABLED,
    EMAIL_VERIFICATION_CODE_TTL_SECONDS,
    EMAIL_VERIFICATION_RESEND_INTERVAL_SECONDS,
    OPENWEBUI_DB_PATH,
    PASSWORD_RESET_MIN_LENGTH,
    PROJECT_ROOT,
    USER_ID_HEADER_NAME,
    USER_EMAIL_HEADER_NAME,
    USER_NAME_HEADER_NAME,
    _generate_id,
    _generate_invite_code,
    _generate_numeric_code,
    _hash_text,
    _portal_email_verification_gate_enabled,
    _reset_timezone,
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
from data_platform.chat_backend.domains.device_sessions.service import (
    _revoke_all_device_sessions,
    _rotate_user_auth_session_version,
)
from data_platform.chat_backend.domains.site_config import _get_email_verification_security_config
from data_platform.chat_backend.domains.portal.service import _portal_public_base_url


_APP_USER_SELECT = """
    SELECT user_id, email, display_name, status, plan_tier,
           created_at, updated_at, source_state, source_last_seen_at,
           source_orphaned_at, source_recovered_at, auth_session_version,
           last_password_reset_at, invite_code, email_verified_at
    FROM app.app_user
"""

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_EMAIL_CHALLENGE_PURPOSE_SIGNUP = "signup_email_verify"
_EMAIL_CHALLENGE_PURPOSE_PASSWORD_RESET = "password_reset"
_EMAIL_CHALLENGE_PURPOSE_SECURITY_VERIFY = "security_verify"
_OPENWEBUI_DB_LOCK = threading.Lock()
_LOGGER = logging.getLogger(__name__)
_PG_RETRYABLE_CONCURRENCY_CODES = {"40P01", "40001"}


def _is_retryable_pg_concurrency_error(exc: Exception) -> bool:
    return str(getattr(exc, "pgcode", "") or "") in _PG_RETRYABLE_CONCURRENCY_CODES


def _execute_app_user_upsert(
    conn,
    *,
    user_id: str,
    normalized_email: str,
    display_name: str,
    effective_plan_tier: str,
    invite_code: str,
) -> list[dict[str, Any]]:
    _run_pg_dict_query(conn, "SELECT pg_advisory_xact_lock(90210508, hashtext(%s))", [user_id])
    return _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.app_user (
            user_id, email, display_name, status, plan_tier, invite_code,
            source_state, source_last_seen_at, source_orphaned_at, source_recovered_at,
            auth_session_version, last_password_reset_at,
            email_verified_at, created_at, updated_at
        ) VALUES (
            %s, %s, %s, 'active', %s, %s,
            'active', NOW(), NULL, NULL,
            1, NULL,
            NULL, NOW(), NOW()
        )
        ON CONFLICT (user_id) DO UPDATE SET
            email = EXCLUDED.email,
            display_name = EXCLUDED.display_name,
            invite_code = COALESCE(app.app_user.invite_code, EXCLUDED.invite_code),
            source_state = 'active',
            source_last_seen_at = NOW(),
            source_orphaned_at = NULL,
            source_recovered_at = CASE
                WHEN app.app_user.source_state = 'orphaned' THEN NOW()
                ELSE app.app_user.source_recovered_at
            END,
            email_verified_at = CASE
                WHEN app.app_user.email IS DISTINCT FROM EXCLUDED.email THEN NULL
                ELSE app.app_user.email_verified_at
            END,
            updated_at = NOW()
        RETURNING user_id, email, display_name, status, plan_tier,
                  created_at, updated_at, source_state, source_last_seen_at,
                  source_orphaned_at, source_recovered_at, auth_session_version,
                  last_password_reset_at, invite_code, email_verified_at
        """,
        [user_id, normalized_email, display_name, effective_plan_tier, invite_code],
    )


def _execute_app_user_upsert_with_retry(
    conn,
    *,
    user_id: str,
    normalized_email: str,
    display_name: str,
    effective_plan_tier: str,
    invite_code: str,
) -> list[dict[str, Any]]:
    max_attempts = 3
    for attempt_index in range(max_attempts):
        savepoint_name = f"app_user_upsert_{attempt_index}"
        with conn.cursor() as cursor:
            cursor.execute(f"SAVEPOINT {savepoint_name}")
        try:
            rows = _execute_app_user_upsert(
                conn,
                user_id=user_id,
                normalized_email=normalized_email,
                display_name=display_name,
                effective_plan_tier=effective_plan_tier,
                invite_code=invite_code,
            )
            with conn.cursor() as cursor:
                cursor.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            return rows
        except Exception as exc:
            with conn.cursor() as cursor:
                cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                cursor.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            if not _is_retryable_pg_concurrency_error(exc) or attempt_index >= max_attempts - 1:
                raise
            _LOGGER.warning(
                "retrying app_user upsert after PostgreSQL concurrency error",
                extra={"user_id": user_id, "pgcode": getattr(exc, "pgcode", None), "attempt": attempt_index + 1},
            )
            time.sleep(0.05 * (attempt_index + 1))
    raise RuntimeError("unreachable app_user upsert retry state")


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


def _build_email_challenge_code_hash(user_id: str, email: str, code: str, purpose: str) -> str:
    return _hash_text(f"{purpose}:{user_id}:{email.strip().lower()}:{code.strip()}")


def _build_email_verification_code_hash(user_id: str, email: str, code: str) -> str:
    return _build_email_challenge_code_hash(user_id, email, code, _EMAIL_CHALLENGE_PURPOSE_SIGNUP)


def _build_email_challenge_token_hash(user_id: str, email: str, token: str, purpose: str) -> str:
    return _hash_text(f"{purpose}:link:{user_id}:{email.strip().lower()}:{token.strip()}")


def _email_verification_ttl_minutes() -> int:
    return max(1, (EMAIL_VERIFICATION_CODE_TTL_SECONDS + 59) // 60)


def _build_public_portal_url(path: str, params: dict[str, str] | None = None) -> str:
    base_url = _portal_public_base_url().rstrip("/")
    normalized_path = path if path.startswith("/") else f"/{path}"
    if not params:
        return f"{base_url}{normalized_path}"
    return f"{base_url}{normalized_path}?{urlencode(params)}"


def _build_email_challenge_bodies(
    *,
    recipient_name: str,
    title: str,
    purpose_label: str,
    intro: str,
    code: str,
    caution: str,
    action_label: str | None = None,
    action_url: str | None = None,
) -> tuple[str, str]:
    ttl_minutes = _email_verification_ttl_minutes()
    safe_name = (recipient_name or "用户").strip() or "用户"
    text_lines = [
        f"你好，{safe_name}。",
        "",
        intro,
        f"验证目的：{purpose_label}",
        f"验证码是：{code}",
        f"验证码 {ttl_minutes} 分钟内有效。",
    ]
    if action_url:
        text_lines.extend([
            "",
            f"也可以点击下面的链接完成验证：{action_url}",
        ])
    text_lines.extend(["", caution])
    text_body = "\n".join(text_lines)

    action_html = ""
    link_hint_html = ""
    if action_url:
        escaped_url = html_escape(action_url, quote=True)
        escaped_label = html_escape(action_label or "完成验证")
        action_html = (
            '<div style="text-align:center;margin:28px 0 22px;">'
            f'<a href="{escaped_url}" style="display:inline-block;background:#2563eb;color:#ffffff;'
            'text-decoration:none;font-weight:700;border-radius:12px;padding:14px 28px;'
            'font-size:16px;line-height:1.2;">'
            f'{escaped_label}</a></div>'
        )
        link_hint_html = (
            '<p style="margin:18px 0 0;color:#64748b;font-size:13px;line-height:1.7;">'
            '如果按钮无法打开，请复制此链接到浏览器：<br />'
            f'<a href="{escaped_url}" style="color:#2563eb;word-break:break-all;">{escaped_url}</a></p>'
        )

    html_body = f"""<!DOCTYPE html>
<html lang="zh-CN">
<body style="margin:0;padding:0;background:#f7f8fb;font-family:Arial,'PingFang SC','Microsoft YaHei',sans-serif;color:#172033;">
    <div style="max-width:680px;margin:0 auto;padding:24px 14px;">
        <div style="background:#ffffff;border:1px solid rgba(23,32,51,0.10);border-radius:18px;overflow:hidden;box-shadow:0 18px 48px rgba(15,23,42,0.08);">
            <div style="background:#2563eb;padding:28px 30px;color:#ffffff;">
                <div style="font-size:13px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;opacity:0.9;">Xiamimate</div>
                <h1 style="margin:8px 0 0;font-size:24px;line-height:1.3;">{html_escape(title)}</h1>
                <div style="margin-top:8px;font-size:15px;opacity:0.92;">{html_escape(purpose_label)}</div>
            </div>
            <div style="padding:30px;">
                <p style="margin:0 0 18px;font-size:16px;line-height:1.75;">你好，{html_escape(safe_name)}。</p>
                <p style="margin:0 0 18px;font-size:16px;line-height:1.75;">{html_escape(intro)}</p>
                <div style="border:1px solid rgba(37,99,235,0.18);background:rgba(37,99,235,0.06);border-radius:14px;padding:18px 20px;margin:22px 0;">
                    <div style="font-size:13px;color:#64748b;font-weight:700;">邮箱验证码</div>
                    <div style="margin-top:8px;font-size:30px;line-height:1.2;letter-spacing:6px;font-weight:800;color:#172033;">{html_escape(code)}</div>
                    <div style="margin-top:10px;font-size:13px;color:#64748b;">{ttl_minutes} 分钟内有效</div>
                </div>
                {action_html}
                <div style="border:1px solid rgba(15,118,110,0.18);background:rgba(15,118,110,0.06);border-radius:14px;padding:16px 18px;margin-top:22px;">
                    <div style="font-weight:700;color:#0f766e;margin-bottom:8px;">注意</div>
                    <div style="font-size:14px;line-height:1.7;color:#334155;">{html_escape(caution)}</div>
                </div>
                {link_hint_html}
            </div>
        </div>
    </div>
</body>
</html>"""
    return text_body, html_body


def _email_verification_day_window(now: datetime) -> tuple[datetime, datetime]:
    local_now = now.astimezone(_reset_timezone())
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _count_email_verification_sends(
    conn,
    *,
    purpose: str,
    user_id: str | None = None,
    email: str | None = None,
    start_at: datetime,
    end_at: datetime,
) -> int:
    conditions = [
        "purpose = %s",
        "last_sent_at >= %s",
        "last_sent_at < %s",
    ]
    params: list[Any] = [purpose, start_at, end_at]
    if user_id:
        conditions.append("user_id = %s")
        params.append(user_id)
    if email:
        conditions.append("email = %s")
        params.append(email)
    row = _fetch_optional_one(
        conn,
        f"""
        SELECT COUNT(*)::INT AS total
        FROM app.email_verification_challenge
        WHERE {' AND '.join(conditions)}
        """,
        params,
    )
    return int((row or {}).get("total") or 0)


def _format_retry_after_seconds(seconds: int) -> str:
    normalized = max(1, int(seconds))
    if normalized < 60:
        return f"{normalized} 秒"
    minutes = (normalized + 59) // 60
    return f"{minutes} 分钟"


def _enforce_email_verification_send_quota(conn, user_id: str, email: str, now: datetime) -> dict[str, int]:
    limits = _get_email_verification_security_config(conn)
    start_at, end_at = _email_verification_day_window(now)
    per_user_limit = int(limits.get("daily_send_limit_per_user") or 0)
    if per_user_limit > 0:
        sent_by_user = _count_email_verification_sends(
            conn,
            purpose=_EMAIL_CHALLENGE_PURPOSE_SIGNUP,
            user_id=user_id,
            start_at=start_at,
            end_at=end_at,
        )
        if sent_by_user >= per_user_limit:
            raise HTTPException(status_code=429, detail="今日邮箱验证码发送次数已达单用户上限，请明天再试")

    per_email_limit = int(limits.get("daily_send_limit_per_email") or 0)
    if per_email_limit > 0:
        sent_by_email = _count_email_verification_sends(
            conn,
            purpose=_EMAIL_CHALLENGE_PURPOSE_SIGNUP,
            email=email,
            start_at=start_at,
            end_at=end_at,
        )
        if sent_by_email >= per_email_limit:
            raise HTTPException(status_code=429, detail="今日邮箱验证码发送次数已达单邮箱上限，请明天再试")

    return limits


def _enforce_email_challenge_send_quota(conn, *, purpose: str, user_id: str, email: str, now: datetime) -> dict[str, int]:
    limits = _get_email_verification_security_config(conn)
    start_at, end_at = _email_verification_day_window(now)
    per_user_limit = int(limits.get("daily_send_limit_per_user") or 0)
    if per_user_limit > 0:
        sent_by_user = _count_email_verification_sends(
            conn,
            purpose=purpose,
            user_id=user_id,
            start_at=start_at,
            end_at=end_at,
        )
        if sent_by_user >= per_user_limit:
            raise HTTPException(status_code=429, detail="今日邮箱验证码发送次数已达单用户上限，请明天再试")

    per_email_limit = int(limits.get("daily_send_limit_per_email") or 0)
    if per_email_limit > 0:
        sent_by_email = _count_email_verification_sends(
            conn,
            purpose=purpose,
            email=email,
            start_at=start_at,
            end_at=end_at,
        )
        if sent_by_email >= per_email_limit:
            raise HTTPException(status_code=429, detail="今日邮箱验证码发送次数已达单邮箱上限，请明天再试")

    return limits


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
    rows = _execute_app_user_upsert_with_retry(
        conn,
        user_id=user_id,
        normalized_email=normalized_email,
        display_name=display_name,
        effective_plan_tier=effective_plan_tier,
        invite_code=invite_code,
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
            safe_email = (email or existing.get("email") or f"{user_id}@local").strip().lower()
            safe_display_name = (display_name or existing.get("display_name") or user_id).strip() or user_id
            existing_email = str(existing.get("email") or "").strip().lower()
            existing_display_name = str(existing.get("display_name") or "").strip()
            source_state = str(existing.get("source_state") or "active").strip().lower()
            needs_source_recovery = source_state != "active" or existing.get("source_orphaned_at") is not None
            needs_identity_update = safe_email != existing_email or safe_display_name != existing_display_name
            if not needs_identity_update and not needs_source_recovery:
                existing = _ensure_invite_code_for_row(conn, existing)
                return RequestUser(**existing)
            return _upsert_user_row(
                conn,
                user_id=user_id,
                email=safe_email,
                display_name=safe_display_name,
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


def _fetch_user_by_email(conn, email: str) -> RequestUser | None:
    normalized_email = _validate_email_address(email)
    row = _fetch_optional_one(
        conn,
        _APP_USER_SELECT + " WHERE LOWER(email) = %s ORDER BY created_at DESC LIMIT 1",
        [normalized_email],
    )
    if row is None:
        return None
    row = _ensure_invite_code_for_row(conn, row)
    return RequestUser(**row)


def _fetch_user_by_invite_code(conn, invite_code: str) -> RequestUser | None:
    normalized_invite_code = (invite_code or "").strip().upper()
    if not normalized_invite_code:
        return None
    row = _fetch_optional_one(
        conn,
        _APP_USER_SELECT + " WHERE invite_code = %s LIMIT 1",
        [normalized_invite_code],
    )
    if row is None:
        return None
    row = _ensure_invite_code_for_row(conn, row)
    return RequestUser(**row)


def _resolve_openwebui_db_path() -> Path:
    configured = (OPENWEBUI_DB_PATH or "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="Open WebUI 账号库路径未配置，暂时无法找回密码")
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    if not path.exists():
        raise HTTPException(status_code=503, detail="Open WebUI 账号库不存在，暂时无法找回密码")
    return path


def _fetch_openwebui_user_identity_map_by_user_ids(user_ids: list[str]) -> dict[str, tuple[str, str, str]]:
    normalized_user_ids = [str(user_id or "").strip() for user_id in user_ids if str(user_id or "").strip()]
    if not normalized_user_ids:
        return {}
    db_path = _resolve_openwebui_db_path()
    placeholders = ", ".join(["?"] * len(normalized_user_ids))
    with _OPENWEBUI_DB_LOCK:
        conn = sqlite3.connect(str(db_path), timeout=5)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 5000")
            rows = conn.execute(
                f"""
                SELECT auth.id AS user_id,
                       LOWER(auth.email) AS email,
                       COALESCE(user.name, user.email, auth.email) AS display_name,
                       auth.active AS active
                FROM auth
                LEFT JOIN user ON user.id = auth.id
                WHERE auth.id IN ({placeholders})
                """,
                normalized_user_ids,
            ).fetchall()
        finally:
            conn.close()
    identities: dict[str, tuple[str, str, str]] = {}
    for row in rows:
        if not int(row["active"] or 0):
            continue
        user_id = str(row["user_id"] or "").strip()
        if not user_id:
            continue
        email = str(row["email"] or "").strip().lower()
        display_name = str(row["display_name"] or row["email"] or user_id)
        identities[user_id] = (user_id, email, display_name)
    return identities


def _reconcile_openwebui_user_sources(conn, user_ids: list[str]) -> dict[str, int]:
    normalized_user_ids = [str(user_id or "").strip() for user_id in user_ids if str(user_id or "").strip()]
    if not normalized_user_ids:
        return {"revived": 0, "orphaned": 0}

    identities = _fetch_openwebui_user_identity_map_by_user_ids(normalized_user_ids)
    revived = 0
    for user_id, email, display_name in identities.values():
        _ensure_user_record(conn, user_id=user_id, email=email, display_name=display_name)
        revived += 1

    orphaned_user_ids = [user_id for user_id in normalized_user_ids if user_id not in identities]
    orphaned = 0
    if orphaned_user_ids:
        orphaned = len(
            _run_pg_dict_query(
                conn,
                """
                UPDATE app.app_user
                SET source_state = 'orphaned',
                    source_orphaned_at = COALESCE(source_orphaned_at, NOW()),
                    updated_at = NOW()
                WHERE user_id = ANY(%s)
                  AND source_state <> 'orphaned'
                RETURNING user_id
                """,
                [orphaned_user_ids],
            )
        )
    return {"revived": revived, "orphaned": orphaned}


def _reconcile_openwebui_user_sources_for_admin(conn, *, query: str | None = None, scan_limit: int = 100) -> dict[str, int]:
    normalized_scan_limit = max(1, int(scan_limit or 100))
    normalized_query = (query or "").strip()
    if normalized_query:
        like_query = f"%{normalized_query}%"
        candidate_rows = _run_pg_dict_query(
            conn,
            """
            SELECT user_id
            FROM app.app_user
            WHERE user_id ILIKE %s OR email ILIKE %s OR display_name ILIKE %s
            ORDER BY updated_at DESC, user_id DESC
            LIMIT %s
            """,
            [like_query, like_query, like_query, normalized_scan_limit],
        )
    else:
        candidate_rows = _run_pg_dict_query(
            conn,
            """
            SELECT user_id
            FROM app.app_user
            ORDER BY updated_at DESC, user_id DESC
            LIMIT %s
            """,
            [normalized_scan_limit],
        )
    return _reconcile_openwebui_user_sources(conn, [row["user_id"] for row in candidate_rows])


def _fetch_openwebui_user_identity_by_email(email: str) -> tuple[str, str, str] | None:
    normalized_email = _validate_email_address(email)
    db_path = _resolve_openwebui_db_path()
    with _OPENWEBUI_DB_LOCK:
        conn = sqlite3.connect(str(db_path), timeout=5)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 5000")
            row = conn.execute(
                """
                SELECT auth.id AS user_id,
                       LOWER(auth.email) AS email,
                       COALESCE(user.name, user.email, auth.email) AS display_name,
                       auth.active AS active
                FROM auth
                LEFT JOIN user ON user.id = auth.id
                WHERE LOWER(auth.email) = ?
                LIMIT 1
                """,
                [normalized_email],
            ).fetchone()
        finally:
            conn.close()
    if row is None or not int(row["active"] or 0):
        return None
    return str(row["user_id"]), str(row["email"]), str(row["display_name"] or row["email"] or normalized_email)


def _ensure_password_reset_user(conn, email: str) -> RequestUser | None:
    identity = _fetch_openwebui_user_identity_by_email(email)
    if identity is None:
        return None
    user_id, resolved_email, display_name = identity
    existing = _fetch_user_by_email(conn, resolved_email)
    if existing is not None and existing.user_id == user_id:
        return _ensure_user_record(conn, user_id=user_id, email=resolved_email, display_name=display_name)
    return _ensure_user_record(conn, user_id=user_id, email=resolved_email, display_name=display_name)


def _validate_password_reset_password(password: str) -> str:
    candidate = password or ""
    if not candidate.strip():
        raise HTTPException(status_code=400, detail="新密码不能为空")
    if len(candidate) < PASSWORD_RESET_MIN_LENGTH:
        raise HTTPException(status_code=400, detail=f"新密码长度不能少于 {PASSWORD_RESET_MIN_LENGTH} 位")
    if len(candidate.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="新密码不能超过 72 字节")
    return candidate


def _hash_openwebui_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def _update_openwebui_password_by_email(email: str, new_password: str) -> bool:
    normalized_email = _validate_email_address(email)
    hashed_password = _hash_openwebui_password(new_password)
    db_path = _resolve_openwebui_db_path()
    with _OPENWEBUI_DB_LOCK:
        conn = sqlite3.connect(str(db_path), timeout=5)
        try:
            conn.execute("PRAGMA busy_timeout = 5000")
            cursor = conn.execute(
                "UPDATE auth SET password = ? WHERE LOWER(email) = ? AND active = 1",
                [hashed_password, normalized_email],
            )
            conn.commit()
            return int(cursor.rowcount or 0) == 1
        finally:
            conn.close()


def _request_password_reset(conn, email: str) -> dict[str, Any]:
    normalized_email = _validate_email_address(email)
    user = _ensure_password_reset_user(conn, normalized_email)
    if user is None:
        _LOGGER.info("password reset rejected for unregistered email", extra={"email": normalized_email})
        raise HTTPException(status_code=404, detail="当前邮箱尚未注册，无法找回密码")

    latest = _fetch_optional_one(
        conn,
        """
        SELECT challenge_id, user_id, email, expires_at, consumed_at, last_sent_at, created_at,
               failed_attempt_count, locked_until, last_failed_at
        FROM app.email_verification_challenge
        WHERE user_id = %s
          AND email = %s
          AND purpose = %s
          AND consumed_at IS NULL
          AND expires_at >= NOW()
        ORDER BY created_at DESC
        LIMIT 1
        """,
        [user.user_id, normalized_email, _EMAIL_CHALLENGE_PURPOSE_PASSWORD_RESET],
    )
    now = _utc_now()
    if latest and latest.get("locked_until") is not None and latest["locked_until"] > now:
        remaining = int((latest["locked_until"] - now).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"验证码已被锁定，请在{_format_retry_after_seconds(remaining)}后重新获取",
        )
    _enforce_email_challenge_send_quota(
        conn,
        purpose=_EMAIL_CHALLENGE_PURPOSE_PASSWORD_RESET,
        user_id=user.user_id,
        email=normalized_email,
        now=now,
    )
    if latest and latest.get("last_sent_at") is not None:
        cooldown = (now - latest["last_sent_at"]).total_seconds()
        if cooldown < EMAIL_VERIFICATION_RESEND_INTERVAL_SECONDS:
            remaining = int(EMAIL_VERIFICATION_RESEND_INTERVAL_SECONDS - cooldown)
            raise HTTPException(status_code=429, detail=f"请在 {remaining} 秒后再重新发送验证码")

    code = _generate_numeric_code(6)
    challenge_id = _generate_id("password_reset")
    expires_at = now + timedelta(seconds=EMAIL_VERIFICATION_CODE_TTL_SECONDS)
    _run_pg_dict_query(
        conn,
        """
        UPDATE app.email_verification_challenge
        SET consumed_at = NOW(),
            updated_at = NOW()
        WHERE user_id = %s
          AND purpose = %s
          AND consumed_at IS NULL
        RETURNING challenge_id
        """,
        [user.user_id, _EMAIL_CHALLENGE_PURPOSE_PASSWORD_RESET],
    )
    _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.email_verification_challenge (
            challenge_id, user_id, email, purpose, code_hash, failed_attempt_count,
            locked_until, last_failed_at, expires_at,
            consumed_at, last_sent_at, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, 0, NULL, NULL, %s, NULL, NOW(), NOW(), NOW())
        RETURNING challenge_id
        """,
        [
            challenge_id,
            user.user_id,
            normalized_email,
            _EMAIL_CHALLENGE_PURPOSE_PASSWORD_RESET,
            _build_email_challenge_code_hash(user.user_id, normalized_email, code, _EMAIL_CHALLENGE_PURPOSE_PASSWORD_RESET),
            expires_at,
        ],
    )
    try:
        text_body, html_body = _build_email_challenge_bodies(
            recipient_name=user.display_name or user.user_id,
            title="找回密码邮箱验证",
            purpose_label="找回并重置虾密小助手登录密码",
            intro="你正在找回虾密小助手的账户密码，请在密码找回页输入下方验证码并设置新密码。",
            code=code,
            caution="如果这不是你本人操作，请忽略此邮件，原密码不会被自动修改。",
            action_label="打开密码找回页面",
            action_url=_build_public_portal_url("/portal/recover-password"),
        )
        _send_email_message(
            normalized_email,
            "虾密小助手密码找回验证码",
            text_body,
            html_body,
        )
        _LOGGER.info(
            "password reset email sent",
            extra={"email": normalized_email, "user_id": user.user_id, "challenge_id": challenge_id},
        )
    except RuntimeError as exc:
        _LOGGER.exception(
            "password reset email unavailable",
            extra={"email": normalized_email, "user_id": user.user_id, "challenge_id": challenge_id},
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        _LOGGER.exception(
            "password reset email failed",
            extra={"email": normalized_email, "user_id": user.user_id, "challenge_id": challenge_id},
        )
        raise HTTPException(status_code=502, detail=f"failed to send verification email: {exc}") from exc
    return {
        "email": normalized_email,
        "accepted": True,
        "challenge_id": challenge_id,
        "expires_in_seconds": EMAIL_VERIFICATION_CODE_TTL_SECONDS,
    }


def _request_security_verification(conn, user_id: str) -> dict[str, Any]:
    user = _fetch_user(conn, user_id)
    email = _validate_email_address(user.email)

    latest = _fetch_optional_one(
        conn,
        """
        SELECT challenge_id, user_id, email, expires_at, consumed_at, last_sent_at, created_at,
               failed_attempt_count, locked_until, last_failed_at
        FROM app.email_verification_challenge
        WHERE user_id = %s
          AND email = %s
          AND purpose = %s
          AND consumed_at IS NULL
          AND expires_at >= NOW()
        ORDER BY created_at DESC
        LIMIT 1
        """,
        [user_id, email, _EMAIL_CHALLENGE_PURPOSE_SECURITY_VERIFY],
    )
    now = _utc_now()
    if latest and latest.get("locked_until") is not None and latest["locked_until"] > now:
        remaining = int((latest["locked_until"] - now).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"验证码已被锁定，请在{_format_retry_after_seconds(remaining)}后重新获取",
        )

    _enforce_email_challenge_send_quota(
        conn,
        purpose=_EMAIL_CHALLENGE_PURPOSE_SECURITY_VERIFY,
        user_id=user_id,
        email=email,
        now=now,
    )
    if latest and latest.get("last_sent_at") is not None:
        cooldown = (now - latest["last_sent_at"]).total_seconds()
        if cooldown < EMAIL_VERIFICATION_RESEND_INTERVAL_SECONDS:
            remaining = int(EMAIL_VERIFICATION_RESEND_INTERVAL_SECONDS - cooldown)
            raise HTTPException(status_code=429, detail=f"请在 {remaining} 秒后再重新发送验证码")

    code = _generate_numeric_code(6)
    challenge_id = _generate_id("security_verify")
    expires_at = now + timedelta(seconds=EMAIL_VERIFICATION_CODE_TTL_SECONDS)
    _run_pg_dict_query(
        conn,
        """
        UPDATE app.email_verification_challenge
        SET consumed_at = NOW(),
            updated_at = NOW()
        WHERE user_id = %s
          AND purpose = %s
          AND consumed_at IS NULL
        RETURNING challenge_id
        """,
        [user_id, _EMAIL_CHALLENGE_PURPOSE_SECURITY_VERIFY],
    )
    _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.email_verification_challenge (
            challenge_id, user_id, email, purpose, code_hash, failed_attempt_count,
            locked_until, last_failed_at, expires_at,
            consumed_at, last_sent_at, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, 0, NULL, NULL, %s, NULL, NOW(), NOW(), NOW())
        RETURNING challenge_id
        """,
        [
            challenge_id,
            user_id,
            email,
            _EMAIL_CHALLENGE_PURPOSE_SECURITY_VERIFY,
            _build_email_challenge_code_hash(user_id, email, code, _EMAIL_CHALLENGE_PURPOSE_SECURITY_VERIFY),
            expires_at,
        ],
    )
    try:
        text_body, html_body = _build_email_challenge_bodies(
            recipient_name=user.display_name or user.user_id,
            title="账户安全验证",
            purpose_label="确认当前设备上的账户安全敏感操作",
            intro="你正在执行账户安全敏感操作，请在当前页面输入下方验证码完成二次确认。",
            code=code,
            caution="如果这不是你本人操作，请忽略此邮件，并检查账户登录设备。",
        )
        _send_email_message(
            email,
            "虾密小助手安全验证验证码",
            text_body,
            html_body,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"failed to send verification email: {exc}") from exc
    return {
        "email": email,
        "challenge_id": challenge_id,
        "expires_in_seconds": EMAIL_VERIFICATION_CODE_TTL_SECONDS,
    }


def _confirm_security_verification(conn, user_id: str, code: str) -> dict[str, Any]:
    user = _fetch_user(conn, user_id)
    email = _validate_email_address(user.email)
    normalized_code = (code or "").strip()
    if not normalized_code:
        raise HTTPException(status_code=400, detail="missing security verification code")

    limits = _get_email_verification_security_config(conn)
    max_failed_attempts = max(1, int(limits.get("max_failed_attempts") or 1))
    lock_seconds = max(0, int(limits.get("lock_seconds") or 0))
    now = _utc_now()

    challenge = _fetch_optional_one(
        conn,
        """
        SELECT challenge_id, user_id, email, code_hash, expires_at, consumed_at, created_at,
               failed_attempt_count, locked_until, last_failed_at
        FROM app.email_verification_challenge
        WHERE user_id = %s
          AND email = %s
          AND purpose = %s
          AND consumed_at IS NULL
          AND expires_at >= NOW()
        ORDER BY created_at DESC
        LIMIT 1
        """,
        [user_id, email, _EMAIL_CHALLENGE_PURPOSE_SECURITY_VERIFY],
    )
    if challenge is None:
        raise HTTPException(status_code=400, detail="验证码不存在或已过期，请重新获取")
    if challenge.get("locked_until") is not None and challenge["locked_until"] > now:
        remaining = int((challenge["locked_until"] - now).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"验证码已被锁定，请在{_format_retry_after_seconds(remaining)}后重新获取",
        )
    expected_hash = _build_email_challenge_code_hash(
        user_id,
        email,
        normalized_code,
        _EMAIL_CHALLENGE_PURPOSE_SECURITY_VERIFY,
    )
    if not challenge.get("code_hash") or challenge["code_hash"] != expected_hash:
        failed_attempt_count = int(challenge.get("failed_attempt_count") or 0) + 1
        locked_until = None
        if failed_attempt_count >= max_failed_attempts and lock_seconds > 0:
            locked_until = now + timedelta(seconds=lock_seconds)
        _run_pg_dict_query(
            conn,
            """
            UPDATE app.email_verification_challenge
            SET failed_attempt_count = %s,
                locked_until = %s,
                last_failed_at = NOW(),
                updated_at = NOW()
            WHERE challenge_id = %s
            RETURNING challenge_id
            """,
            [failed_attempt_count, locked_until, challenge["challenge_id"]],
        )
        if failed_attempt_count >= max_failed_attempts:
            raise HTTPException(
                status_code=429,
                detail=f"验证码尝试次数过多，请在{_format_retry_after_seconds(lock_seconds or 1)}后重新获取",
            )
        remaining_attempts = max_failed_attempts - failed_attempt_count
        raise HTTPException(status_code=400, detail=f"验证码错误，还可尝试 {remaining_attempts} 次")

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
    _run_pg_dict_query(
        conn,
        """
        UPDATE app.app_user
        SET updated_at = NOW()
        WHERE user_id = %s
        RETURNING user_id
        """,
        [user_id],
    )
    return {
        "email": email,
        "verified": True,
        "verified_at": now,
    }


def _confirm_password_reset(conn, email: str, code: str, new_password: str) -> dict[str, Any]:
    normalized_email = _validate_email_address(email)
    normalized_code = (code or "").strip()
    if not normalized_code:
        raise HTTPException(status_code=400, detail="missing email verification code")
    validated_password = _validate_password_reset_password(new_password)

    user = _ensure_password_reset_user(conn, normalized_email)
    if user is None:
        raise HTTPException(status_code=400, detail="验证码不存在或已过期，请重新获取")

    limits = _get_email_verification_security_config(conn)
    max_failed_attempts = max(1, int(limits.get("max_failed_attempts") or 1))
    lock_seconds = max(0, int(limits.get("lock_seconds") or 0))
    now = _utc_now()

    challenge = _fetch_optional_one(
        conn,
        """
        SELECT challenge_id, user_id, email, code_hash, expires_at, consumed_at, created_at,
               failed_attempt_count, locked_until, last_failed_at
        FROM app.email_verification_challenge
        WHERE user_id = %s
          AND email = %s
          AND purpose = %s
          AND consumed_at IS NULL
          AND expires_at >= NOW()
        ORDER BY created_at DESC
        LIMIT 1
        """,
        [user.user_id, normalized_email, _EMAIL_CHALLENGE_PURPOSE_PASSWORD_RESET],
    )
    if challenge is None:
        raise HTTPException(status_code=400, detail="验证码不存在或已过期，请重新获取")
    if challenge.get("locked_until") is not None and challenge["locked_until"] > now:
        remaining = int((challenge["locked_until"] - now).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"验证码已被锁定，请在{_format_retry_after_seconds(remaining)}后重新获取",
        )
    expected_hash = _build_email_challenge_code_hash(
        user.user_id,
        normalized_email,
        normalized_code,
        _EMAIL_CHALLENGE_PURPOSE_PASSWORD_RESET,
    )
    if not challenge.get("code_hash") or challenge["code_hash"] != expected_hash:
        failed_attempt_count = int(challenge.get("failed_attempt_count") or 0) + 1
        locked_until = None
        if failed_attempt_count >= max_failed_attempts and lock_seconds > 0:
            locked_until = now + timedelta(seconds=lock_seconds)
        _run_pg_dict_query(
            conn,
            """
            UPDATE app.email_verification_challenge
            SET failed_attempt_count = %s,
                locked_until = %s,
                last_failed_at = NOW(),
                updated_at = NOW()
            WHERE challenge_id = %s
            RETURNING challenge_id
            """,
            [failed_attempt_count, locked_until, challenge["challenge_id"]],
        )
        if failed_attempt_count >= max_failed_attempts:
            raise HTTPException(
                status_code=429,
                detail=f"验证码尝试次数过多，请在{_format_retry_after_seconds(lock_seconds or 1)}后重新获取",
            )
        remaining_attempts = max_failed_attempts - failed_attempt_count
        raise HTTPException(status_code=400, detail=f"验证码错误，还可尝试 {remaining_attempts} 次")

    updated = _update_openwebui_password_by_email(normalized_email, validated_password)
    if not updated:
        raise HTTPException(status_code=502, detail="密码回写 Open WebUI 失败，请稍后重试")

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
    _run_pg_dict_query(
        conn,
        """
        UPDATE app.app_user
        SET updated_at = NOW()
        WHERE user_id = %s
        RETURNING user_id
        """,
        [user.user_id],
    )
    _rotate_user_auth_session_version(conn, user.user_id, password_reset=True)
    _revoke_all_device_sessions(conn, user.user_id, "password_reset")
    return {
        "email": normalized_email,
        "password_reset": True,
        "force_relogin": True,
    }


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
                SELECT challenge_id, user_id, email, expires_at, consumed_at, last_sent_at, created_at,
                             failed_attempt_count, locked_until, last_failed_at
        FROM app.email_verification_challenge
        WHERE user_id = %s
          AND email = %s
                    AND purpose = %s
          AND consumed_at IS NULL
          AND expires_at >= NOW()
        ORDER BY created_at DESC
        LIMIT 1
        """,
                [user_id, email, _EMAIL_CHALLENGE_PURPOSE_SIGNUP],
    )
    now = _utc_now()
    if latest and latest.get("locked_until") is not None and latest["locked_until"] > now:
        remaining = int((latest["locked_until"] - now).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"验证码已被锁定，请在{_format_retry_after_seconds(remaining)}后重新获取",
        )
    _enforce_email_verification_send_quota(conn, user_id=user_id, email=email, now=now)
    if latest and latest.get("last_sent_at") is not None:
        cooldown = (now - latest["last_sent_at"]).total_seconds()
        if cooldown < EMAIL_VERIFICATION_RESEND_INTERVAL_SECONDS:
            remaining = int(EMAIL_VERIFICATION_RESEND_INTERVAL_SECONDS - cooldown)
            raise HTTPException(status_code=429, detail=f"请在 {remaining} 秒后再重新发送验证码")

    code = _generate_numeric_code(6)
    confirm_token = secrets.token_urlsafe(32)
    challenge_id = _generate_id("email_verify")
    expires_at = now + timedelta(seconds=EMAIL_VERIFICATION_CODE_TTL_SECONDS)
    _run_pg_dict_query(
        conn,
        """
        UPDATE app.email_verification_challenge
        SET consumed_at = NOW(),
            updated_at = NOW()
        WHERE user_id = %s
                    AND purpose = %s
          AND consumed_at IS NULL
        RETURNING challenge_id
        """,
                [user_id, _EMAIL_CHALLENGE_PURPOSE_SIGNUP],
    )
    _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.email_verification_challenge (
            challenge_id, user_id, email, purpose, code_hash, confirm_token_hash, failed_attempt_count,
            locked_until, last_failed_at, expires_at,
            consumed_at, last_sent_at, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, 0, NULL, NULL, %s, NULL, NOW(), NOW(), NOW())
        RETURNING challenge_id, email, expires_at, last_sent_at, created_at
        """,
        [
            challenge_id,
            user_id,
            email,
            _EMAIL_CHALLENGE_PURPOSE_SIGNUP,
            _build_email_verification_code_hash(user_id, email, code),
            _build_email_challenge_token_hash(user_id, email, confirm_token, _EMAIL_CHALLENGE_PURPOSE_SIGNUP),
            expires_at,
        ],
    )
    try:
        confirm_url = _build_public_portal_url(
            "/portal/email-verification/confirm",
            {"challenge_id": challenge_id, "token": confirm_token},
        )
        text_body, html_body = _build_email_challenge_bodies(
            recipient_name=user.display_name or user.user_id,
            title="注册邮箱验证",
            purpose_label="完成注册并激活虾密小助手账户权益",
            intro="你正在注册或首次激活虾密小助手账户。请点击按钮完成邮箱验证，或在账户页输入下方验证码。",
            code=code,
            caution="如果这不是你本人操作，请忽略此邮件，当前邮箱不会被自动绑定到其他账户。",
            action_label="完成邮箱验证",
            action_url=confirm_url,
        )
        _send_email_message(
            email,
            "虾密小助手注册邮箱验证",
            text_body,
            html_body,
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
        "verification_link_available": True,
    }


def _confirm_email_verification(conn, user_id: str, code: str) -> RequestUser:
    user = _fetch_user(conn, user_id)
    email = _validate_email_address(user.email)
    normalized_code = (code or "").strip()
    if not normalized_code:
        raise HTTPException(status_code=400, detail="missing email verification code")
    if user.email_verified_at is not None:
        return user

    limits = _get_email_verification_security_config(conn)
    max_failed_attempts = max(1, int(limits.get("max_failed_attempts") or 1))
    lock_seconds = max(0, int(limits.get("lock_seconds") or 0))
    now = _utc_now()

    challenge = _fetch_optional_one(
        conn,
        """
        SELECT challenge_id, user_id, email, code_hash, expires_at, consumed_at, created_at,
               failed_attempt_count, locked_until, last_failed_at
        FROM app.email_verification_challenge
        WHERE user_id = %s
          AND email = %s
                    AND purpose = %s
          AND consumed_at IS NULL
          AND expires_at >= NOW()
        ORDER BY created_at DESC
        LIMIT 1
        """,
                [user_id, email, _EMAIL_CHALLENGE_PURPOSE_SIGNUP],
    )
    if challenge is None:
        raise HTTPException(status_code=400, detail="验证码不存在或已过期，请重新获取")
    if challenge.get("locked_until") is not None and challenge["locked_until"] > now:
        remaining = int((challenge["locked_until"] - now).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"验证码已被锁定，请在{_format_retry_after_seconds(remaining)}后重新获取",
        )
    if not challenge.get("code_hash") or challenge["code_hash"] != _build_email_verification_code_hash(user_id, email, normalized_code):
        failed_attempt_count = int(challenge.get("failed_attempt_count") or 0) + 1
        locked_until = None
        if failed_attempt_count >= max_failed_attempts and lock_seconds > 0:
            locked_until = now + timedelta(seconds=lock_seconds)
        _run_pg_dict_query(
            conn,
            """
            UPDATE app.email_verification_challenge
            SET failed_attempt_count = %s,
                locked_until = %s,
                last_failed_at = NOW(),
                updated_at = NOW()
            WHERE challenge_id = %s
            RETURNING challenge_id
            """,
            [failed_attempt_count, locked_until, challenge["challenge_id"]],
        )
        if failed_attempt_count >= max_failed_attempts:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"验证码尝试次数过多，请在{_format_retry_after_seconds(lock_seconds or 1)}后重新获取"
                ),
            )
        remaining_attempts = max_failed_attempts - failed_attempt_count
        raise HTTPException(status_code=400, detail=f"验证码错误，还可尝试 {remaining_attempts} 次")

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


def _confirm_email_verification_link(conn, challenge_id: str, token: str) -> RequestUser:
    normalized_challenge_id = (challenge_id or "").strip()
    normalized_token = (token or "").strip()
    if not normalized_challenge_id or not normalized_token:
        raise HTTPException(status_code=400, detail="missing email verification link token")

    challenge = _fetch_optional_one(
        conn,
        """
        SELECT challenge_id, user_id, email, confirm_token_hash, expires_at, consumed_at, created_at,
               failed_attempt_count, locked_until, last_failed_at
        FROM app.email_verification_challenge
        WHERE challenge_id = %s
          AND purpose = %s
        LIMIT 1
        """,
        [normalized_challenge_id, _EMAIL_CHALLENGE_PURPOSE_SIGNUP],
    )
    if challenge is None:
        raise HTTPException(status_code=400, detail="邮箱验证链接不存在或已过期")

    user_id = str(challenge.get("user_id") or "").strip()
    email = _validate_email_address(str(challenge.get("email") or ""))
    user = _fetch_user(conn, user_id)
    if (user.email or "").strip().lower() != email:
        raise HTTPException(status_code=409, detail="当前账号邮箱已变化，请重新发送验证邮件")
    if user.email_verified_at is not None:
        if challenge.get("consumed_at") is None:
            _run_pg_dict_query(
                conn,
                """
                UPDATE app.email_verification_challenge
                SET consumed_at = NOW(),
                    updated_at = NOW()
                WHERE challenge_id = %s
                RETURNING challenge_id
                """,
                [normalized_challenge_id],
            )
        return user

    now = _utc_now()
    if challenge.get("consumed_at") is not None or challenge.get("expires_at") is None or challenge["expires_at"] < now:
        raise HTTPException(status_code=400, detail="邮箱验证链接不存在或已过期，请重新获取")
    if challenge.get("locked_until") is not None and challenge["locked_until"] > now:
        remaining = int((challenge["locked_until"] - now).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"邮箱验证链接已被锁定，请在{_format_retry_after_seconds(remaining)}后重新获取",
        )

    expected_hash = _build_email_challenge_token_hash(
        user_id,
        email,
        normalized_token,
        _EMAIL_CHALLENGE_PURPOSE_SIGNUP,
    )
    if not challenge.get("confirm_token_hash") or challenge["confirm_token_hash"] != expected_hash:
        limits = _get_email_verification_security_config(conn)
        max_failed_attempts = max(1, int(limits.get("max_failed_attempts") or 1))
        lock_seconds = max(0, int(limits.get("lock_seconds") or 0))
        failed_attempt_count = int(challenge.get("failed_attempt_count") or 0) + 1
        locked_until = None
        if failed_attempt_count >= max_failed_attempts and lock_seconds > 0:
            locked_until = now + timedelta(seconds=lock_seconds)
        _run_pg_dict_query(
            conn,
            """
            UPDATE app.email_verification_challenge
            SET failed_attempt_count = %s,
                locked_until = %s,
                last_failed_at = NOW(),
                updated_at = NOW()
            WHERE challenge_id = %s
            RETURNING challenge_id
            """,
            [failed_attempt_count, locked_until, normalized_challenge_id],
        )
        raise HTTPException(status_code=400, detail="邮箱验证链接无效，请重新获取")

    _run_pg_dict_query(
        conn,
        """
        UPDATE app.email_verification_challenge
        SET consumed_at = NOW(),
            updated_at = NOW()
        WHERE challenge_id = %s
        RETURNING challenge_id
        """,
        [normalized_challenge_id],
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
    invite_code = user.invite_code
    invite_link = None
    if invite_code:
        invite_link = f"{_portal_public_base_url()}/portal/invite?code={quote(invite_code)}"
    return {
        "email": user.email,
        "email_verified": email_verified,
        "email_verified_at": user.email_verified_at,
        "email_verification_required_before_portal_use": _portal_email_verification_gate_enabled(),
        "invite_code": invite_code,
        "invite_link": invite_link,
        "invited_by": binding,
        "can_bind_invite_code": binding is None and not email_verified,
    }


def _provision_user_identity(conn, request: Request) -> tuple[RequestUser, UserAPIKey, UserCreditAccount]:
    user = _upsert_user(conn, request)
    user_api_key = _ensure_user_api_key(conn, user)
    credit_account = _ensure_user_credit_account_state(conn, user)
    return user, user_api_key, credit_account
