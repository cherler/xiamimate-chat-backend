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
    session_id = row.get("session_id")
    session_ids = list(row.get("session_ids") or ([session_id] if session_id else []))
    return {
        "session_id": session_id,
        "session_ids": session_ids,
        "session_count": int(row.get("session_count") or max(1, len(session_ids))),
        "active_session_count": int(row.get("active_session_count") or (0 if row.get("revoked_at") else 1)),
        "revoked_session_count": int(row.get("revoked_session_count") or 0),
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


def _reuse_recent_matching_device_session(conn, user_id: str, raw_token: str, request: Request) -> dict[str, Any] | None:
    device_label = _request_device_label(request)
    user_agent = str(request.headers.get("user-agent") or "")
    client_ip = _request_client_ip(request)
    if not user_agent or not client_ip or client_ip == "unknown":
        return None
    rows = _run_pg_dict_query(
        conn,
        """
        WITH candidate AS (
            SELECT s.session_id
            FROM app.user_device_session s
            JOIN app.app_user u ON u.user_id = s.user_id
            WHERE s.user_id = %s
              AND s.revoked_at IS NULL
              AND s.session_version = u.auth_session_version
              AND s.created_at >= NOW() - (%s * INTERVAL '1 second')
              AND s.device_label = %s
              AND COALESCE(s.user_agent, '') = %s
              AND COALESCE(s.last_seen_ip, s.created_ip, '') = %s
            ORDER BY s.last_seen_at DESC NULLS LAST, s.updated_at DESC NULLS LAST, s.created_at DESC
            LIMIT 1
            FOR UPDATE OF s SKIP LOCKED
        )
        UPDATE app.user_device_session s
        SET session_token_hash = %s,
            last_seen_at = NOW(),
            last_seen_ip = %s,
            device_label = %s,
            user_agent = %s,
            updated_at = NOW()
        FROM candidate
        WHERE s.session_id = candidate.session_id
        RETURNING s.session_id, s.user_id, s.session_version, s.device_label, s.user_agent,
                  s.created_ip, s.last_seen_ip, s.last_seen_at, s.elevated_until,
                  s.last_verified_at, s.revoked_at, s.revoked_reason,
                  s.created_at, s.updated_at
        """,
        [
            user_id,
            DEVICE_SESSION_TTL_SECONDS,
            device_label,
            user_agent,
            client_ip,
            _hash_device_session_token(raw_token),
            client_ip,
            device_label,
            user_agent,
        ],
    )
    return rows[0] if rows else None


def _bootstrap_device_session(conn, user_id: str, request: Request) -> tuple[dict[str, Any] | None, str | None, bool]:
    evaluated = _evaluate_device_session_request(conn, user_id, request, touch=True)
    if evaluated["status"] == "ok":
        return evaluated["session"], evaluated["raw_token"], False

    raw_token = secrets.token_urlsafe(32)
    reused_session = _reuse_recent_matching_device_session(conn, user_id, raw_token, request)
    if reused_session is not None:
        return reused_session, raw_token, False

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


def _revoke_device_session(
    conn,
    user_id: str,
    session_id: str,
    reason: str,
    *,
    current_session_id: str | None = None,
) -> dict[str, Any] | None:
    target = _fetch_optional_one(
        conn,
        """
        SELECT session_id, user_id, session_version, device_label, user_agent,
               created_ip, last_seen_ip, last_seen_at, elevated_until,
               last_verified_at, revoked_at, revoked_reason,
               created_at, updated_at
        FROM app.user_device_session
        WHERE user_id = %s
          AND session_id = %s
          AND revoked_at IS NULL
        LIMIT 1
        """,
        [user_id, session_id],
    )
    if target is None:
        return None
    target_ip_key = str(target.get("last_seen_ip") or target.get("created_ip") or "")
    rows = _run_pg_dict_query(
        conn,
        """
        UPDATE app.user_device_session
        SET revoked_at = NOW(),
            revoked_reason = %s,
            updated_at = NOW()
        WHERE user_id = %s
          AND revoked_at IS NULL
          AND session_id <> COALESCE(%s, '')
          AND device_label = %s
          AND COALESCE(user_agent, '') = %s
          AND COALESCE(last_seen_ip, created_ip, '') = %s
        RETURNING session_id, user_id, session_version, device_label, user_agent,
                  created_ip, last_seen_ip, last_seen_at, elevated_until,
                  last_verified_at, revoked_at, revoked_reason,
                  created_at, updated_at
        """,
        [
            reason,
            user_id,
            current_session_id,
            str(target.get("device_label") or ""),
            str(target.get("user_agent") or ""),
            target_ip_key,
        ],
    )
    revoked_session_ids = [str(row.get("session_id") or "") for row in rows if row.get("session_id")]
    result = dict(target)
    result["revoked_at"] = rows[0].get("revoked_at") if rows else target.get("revoked_at")
    result["revoked_reason"] = reason
    result["revoked_session_ids"] = revoked_session_ids
    result["revoked_session_count"] = len(revoked_session_ids)
    return result


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


def _device_session_group_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("device_label") or ""),
        str(row.get("user_agent") or ""),
        str(row.get("last_seen_ip") or row.get("created_ip") or ""),
    )


def _latest_session_time(row: dict[str, Any]) -> Any:
    return row.get("last_seen_at") or row.get("updated_at") or row.get("created_at")


def _aggregate_device_session_rows(
    rows: list[dict[str, Any]],
    *,
    current_session_id: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    grouped_rows: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped_rows.setdefault(_device_session_group_key(row), []).append(row)

    serialized_groups: list[dict[str, Any]] = []
    for group in grouped_rows.values():
        current_rows = [row for row in group if current_session_id and row.get("session_id") == current_session_id]
        active_rows = [row for row in group if not row.get("revoked_at")]
        representative_pool = current_rows or active_rows or group
        representative = max(representative_pool, key=lambda row: str(_latest_session_time(row) or ""))
        created_values = [row.get("created_at") for row in group if row.get("created_at") is not None]
        seen_values = [row.get("last_seen_at") for row in group if row.get("last_seen_at") is not None]
        representative = dict(representative)
        representative["session_ids"] = [row.get("session_id") for row in group if row.get("session_id")]
        representative["session_count"] = len(group)
        representative["active_session_count"] = len(active_rows)
        representative["revoked_session_count"] = len(group) - len(active_rows)
        if created_values:
            representative["created_at"] = min(created_values)
        if seen_values:
            representative["last_seen_at"] = max(seen_values)
        serialized = _serialize_device_session(representative, current_session_id=current_session_id)
        if serialized is not None:
            serialized_groups.append(serialized)

    serialized_groups.sort(
        key=lambda session: (
            1 if session.get("is_current") else 0,
            str(session.get("last_seen_at") or session.get("updated_at") or session.get("created_at") or ""),
        ),
        reverse=True,
    )
    return serialized_groups[: max(1, int(limit or 10))]


def _list_recent_device_sessions(conn, user_id: str, *, current_session_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    raw_limit = max(max(1, int(limit or 10)) * 4, 40)
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
        [user_id, DEVICE_SESSION_TTL_SECONDS, raw_limit],
    )
    return _aggregate_device_session_rows(rows, current_session_id=current_session_id, limit=limit)
