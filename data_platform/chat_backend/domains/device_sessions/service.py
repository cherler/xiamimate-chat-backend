"""Device session domain for browser-scoped security controls."""
from __future__ import annotations

import secrets
from typing import Any

from fastapi import HTTPException, Request, Response

from data_platform.chat_backend.infra.postgres import (
    _fetch_optional_one,
    _run_pg_dict_query,
)
from data_platform.chat_backend.infra.settings import (
    DEVICE_SESSION_COOKIE_NAME,
    DEVICE_SESSION_ELEVATION_TTL_SECONDS,
    DEVICE_SESSION_TTL_SECONDS,
    _generate_id,
    _hash_text,
    _utc_now,
)


def _request_client_ip(request: Request) -> str:
    x_real_ip = (request.headers.get("x-real-ip") or "").strip()
    if x_real_ip:
        return x_real_ip
    forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if request.client and request.client.host:
        return str(request.client.host).strip()
    return "unknown"


def _device_session_cookie_value(request: Request) -> str:
    return str(request.cookies.get(DEVICE_SESSION_COOKIE_NAME) or "").strip()


def _hash_device_session_token(raw_token: str) -> str:
    return _hash_text(f"device_session:{str(raw_token or '').strip()}")


def _build_browser_name(user_agent: str, sec_ch_ua: str = "") -> str:
    normalized = str(user_agent or "").strip()
    lower = normalized.lower()
    sec_ch_ua_lower = str(sec_ch_ua or "").lower()

    if '"microsoft edge"' in sec_ch_ua_lower or "edg/" in lower:
        return "Edge"
    if '"opera"' in sec_ch_ua_lower or '"opera gx"' in sec_ch_ua_lower or "opr/" in lower or "opera/" in lower:
        return "Opera"
    if '"brave"' in sec_ch_ua_lower or "brave/" in lower:
        return "Brave"
    if '"arc"' in sec_ch_ua_lower or "arc/" in lower:
        return "Arc"
    if '"google chrome"' in sec_ch_ua_lower or "crios/" in lower or "chrome/" in lower or "chromium/" in lower:
        return "Chrome"
    if "firefox/" in lower or "fxios/" in lower:
        return "Firefox"
    if "safari/" in lower and "chrome/" not in lower and "chromium/" not in lower and "crios/" not in lower:
        return "Safari"
    return "Browser"


def _build_device_label(user_agent: str, sec_ch_ua: str = "") -> str:
    normalized = str(user_agent or "").strip()
    lower = normalized.lower()

    browser = _build_browser_name(user_agent, sec_ch_ua)

    if "iphone" in lower or "ipad" in lower or "ios" in lower:
        platform = "iOS"
    elif "mac os x" in lower or "macintosh" in lower:
        platform = "macOS"
    elif "windows" in lower:
        platform = "Windows"
    elif "android" in lower:
        platform = "Android"
    elif "linux" in lower:
        platform = "Linux"
    else:
        platform = "Unknown OS"

    return f"{browser} / {platform}"


def _request_device_label(request: Request) -> str:
    return _build_device_label(
        str(request.headers.get("user-agent") or ""),
        str(request.headers.get("sec-ch-ua") or ""),
    )


def _set_device_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        DEVICE_SESSION_COOKIE_NAME,
        raw_token,
        max_age=DEVICE_SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _clear_device_session_cookie(response: Response) -> None:
    response.delete_cookie(DEVICE_SESSION_COOKIE_NAME, path="/")


def _serialize_device_session(row: dict[str, Any] | None, *, current_session_id: str | None = None) -> dict[str, Any] | None:
    if row is None:
        return None
    elevated_until = row.get("elevated_until")
    return {
        "session_id": row.get("session_id"),
        "device_label": row.get("device_label") or "当前设备",
        "user_agent": row.get("user_agent") or "",
        "created_ip": row.get("created_ip"),
        "last_seen_ip": row.get("last_seen_ip"),
        "last_seen_at": row.get("last_seen_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "revoked_at": row.get("revoked_at"),
        "revoked_reason": row.get("revoked_reason"),
        "last_verified_at": row.get("last_verified_at"),
        "elevated_until": elevated_until,
        "is_elevated": bool(elevated_until and elevated_until > _utc_now()),
        "is_current": bool(current_session_id and row.get("session_id") == current_session_id),
    }


def _fetch_active_device_session(conn, user_id: str, raw_token: str) -> dict[str, Any] | None:
    normalized_token = str(raw_token or "").strip()
    if not normalized_token:
        return None
    return _fetch_optional_one(
        conn,
        """
        SELECT s.session_id, s.user_id, s.session_version, s.device_label, s.user_agent,
               s.created_ip, s.last_seen_ip, s.last_seen_at, s.elevated_until,
               s.last_verified_at, s.revoked_at, s.revoked_reason,
               s.created_at, s.updated_at, u.auth_session_version
        FROM app.user_device_session s
        JOIN app.app_user u ON u.user_id = s.user_id
        WHERE s.user_id = %s
          AND s.session_token_hash = %s
          AND s.revoked_at IS NULL
          AND s.session_version = u.auth_session_version
          AND s.created_at >= NOW() - (%s * INTERVAL '1 second')
        LIMIT 1
        """,
        [user_id, _hash_device_session_token(normalized_token), DEVICE_SESSION_TTL_SECONDS],
    )


def _touch_device_session(conn, session_id: str, request: Request) -> dict[str, Any] | None:
    device_label = _request_device_label(request)
    rows = _run_pg_dict_query(
        conn,
        """
        UPDATE app.user_device_session
        SET last_seen_at = NOW(),
            last_seen_ip = %s,
            device_label = %s,
            user_agent = %s,
            updated_at = NOW()
        WHERE session_id = %s
        RETURNING session_id, user_id, session_version, device_label, user_agent,
                  created_ip, last_seen_ip, last_seen_at, elevated_until,
                  last_verified_at, revoked_at, revoked_reason,
                  created_at, updated_at
        """,
        [_request_client_ip(request), device_label, str(request.headers.get("user-agent") or ""), session_id],
    )
    return rows[0] if rows else None


def _evaluate_device_session_request(conn, user_id: str, request: Request, *, touch: bool = True) -> dict[str, Any]:
    raw_token = _device_session_cookie_value(request)
    if not raw_token:
        return {"status": "missing", "raw_token": "", "session": None}
    session_row = _fetch_active_device_session(conn, user_id, raw_token)
    if session_row is None:
        return {"status": "invalid", "raw_token": raw_token, "session": None}
    if touch:
        touched = _touch_device_session(conn, str(session_row["session_id"]), request)
        if touched is not None:
            session_row = touched
    return {"status": "ok", "raw_token": raw_token, "session": session_row}


def _bootstrap_device_session(conn, user_id: str, request: Request) -> tuple[dict[str, Any] | None, str | None, bool]:
    evaluated = _evaluate_device_session_request(conn, user_id, request, touch=True)
    if evaluated["status"] == "ok":
        return evaluated["session"], evaluated["raw_token"], False

    raw_token = secrets.token_urlsafe(32)
    device_label = _request_device_label(request)
    rows = _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.user_device_session (
            session_id, user_id, session_token_hash, session_version,
            device_label, user_agent, created_ip, last_seen_ip,
            last_seen_at, elevated_until, last_verified_at,
            revoked_at, revoked_reason, created_at, updated_at
        )
        SELECT %s, user_id, %s, auth_session_version,
               %s, %s, %s, %s,
               NOW(), NULL, NULL,
               NULL, NULL, NOW(), NOW()
        FROM app.app_user
        WHERE user_id = %s
        RETURNING session_id, user_id, session_version, device_label, user_agent,
                  created_ip, last_seen_ip, last_seen_at, elevated_until,
                  last_verified_at, revoked_at, revoked_reason,
                  created_at, updated_at
        """,
        [
            _generate_id("devsess"),
            _hash_device_session_token(raw_token),
            device_label,
            str(request.headers.get("user-agent") or ""),
            _request_client_ip(request),
            _request_client_ip(request),
            user_id,
        ],
    )
    return (rows[0] if rows else None), raw_token, True


def _current_device_session_or_raise(conn, user_id: str, request: Request) -> dict[str, Any]:
    evaluated = _evaluate_device_session_request(conn, user_id, request, touch=True)
    if evaluated["status"] != "ok" or evaluated["session"] is None:
        raise HTTPException(status_code=409, detail="current device session expired")
    return evaluated["session"]


def _rotate_user_auth_session_version(conn, user_id: str, *, password_reset: bool = False) -> dict[str, Any]:
    rows = _run_pg_dict_query(
        conn,
        """
        UPDATE app.app_user
        SET auth_session_version = auth_session_version + 1,
            last_password_reset_at = CASE
                WHEN %s THEN NOW()
                ELSE last_password_reset_at
            END,
            updated_at = NOW()
        WHERE user_id = %s
        RETURNING user_id, auth_session_version, last_password_reset_at
        """,
        [password_reset, user_id],
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"user not found: {user_id}")
    return rows[0]


def _revoke_all_device_sessions(conn, user_id: str, reason: str) -> int:
    return len(
        _run_pg_dict_query(
            conn,
            """
            UPDATE app.user_device_session
            SET revoked_at = NOW(),
                revoked_reason = %s,
                updated_at = NOW()
            WHERE user_id = %s
              AND revoked_at IS NULL
            RETURNING session_id
            """,
            [reason, user_id],
        )
    )


def _revoke_other_device_sessions(conn, user_id: str, current_session_id: str, reason: str) -> int:
    return len(
        _run_pg_dict_query(
            conn,
            """
            UPDATE app.user_device_session
            SET revoked_at = NOW(),
                revoked_reason = %s,
                updated_at = NOW()
            WHERE user_id = %s
              AND revoked_at IS NULL
              AND session_id <> %s
            RETURNING session_id
            """,
            [reason, user_id, current_session_id],
        )
    )


def _revoke_device_session(conn, user_id: str, session_id: str, reason: str) -> dict[str, Any] | None:
    rows = _run_pg_dict_query(
        conn,
        """
        UPDATE app.user_device_session
        SET revoked_at = NOW(),
            revoked_reason = %s,
            updated_at = NOW()
        WHERE user_id = %s
          AND session_id = %s
          AND revoked_at IS NULL
        RETURNING session_id, user_id, session_version, device_label, user_agent,
                  created_ip, last_seen_ip, last_seen_at, elevated_until,
                  last_verified_at, revoked_at, revoked_reason,
                  created_at, updated_at
        """,
        [reason, user_id, session_id],
    )
    return rows[0] if rows else None


def _elevate_device_session(conn, session_id: str, *, ttl_seconds: int = DEVICE_SESSION_ELEVATION_TTL_SECONDS) -> dict[str, Any]:
    rows = _run_pg_dict_query(
        conn,
        """
        UPDATE app.user_device_session
        SET elevated_until = NOW() + (%s * INTERVAL '1 second'),
            last_verified_at = NOW(),
            updated_at = NOW()
        WHERE session_id = %s
          AND revoked_at IS NULL
        RETURNING session_id, user_id, session_version, device_label, user_agent,
                  created_ip, last_seen_ip, last_seen_at, elevated_until,
                  last_verified_at, revoked_at, revoked_reason,
                  created_at, updated_at
        """,
        [max(60, int(ttl_seconds or DEVICE_SESSION_ELEVATION_TTL_SECONDS)), session_id],
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"device session not found: {session_id}")
    return rows[0]


def _require_elevated_device_session(conn, user_id: str, request: Request) -> dict[str, Any]:
    session_row = _current_device_session_or_raise(conn, user_id, request)
    elevated_until = session_row.get("elevated_until")
    if elevated_until is None or elevated_until <= _utc_now():
        raise HTTPException(status_code=403, detail="security verification required for this action")
    return session_row


def _list_recent_device_sessions(conn, user_id: str, *, current_session_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    rows = _run_pg_dict_query(
        conn,
        """
        SELECT session_id, user_id, session_version, device_label, user_agent,
               created_ip, last_seen_ip, last_seen_at, elevated_until,
               last_verified_at, revoked_at, revoked_reason,
               created_at, updated_at
        FROM app.user_device_session
        WHERE user_id = %s
          AND created_at >= NOW() - (%s * INTERVAL '1 second')
        ORDER BY last_seen_at DESC, session_id DESC
        LIMIT %s
        """,
        [user_id, DEVICE_SESSION_TTL_SECONDS, max(1, int(limit or 10))],
    )
    return [
        _serialize_device_session(row, current_session_id=current_session_id)
        for row in rows
    ]
