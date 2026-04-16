"""API-key domain — service functions.

Depends on: infra.settings, infra.postgres, api_keys.models.
"""
from __future__ import annotations

from typing import Any

from data_platform.chat_backend.infra.settings import (
    _build_api_key,
    _generate_id,
    _hash_api_key,
)
from data_platform.chat_backend.infra.postgres import (
    _fetch_optional_one,
    _run_pg_dict_query,
)
from data_platform.chat_backend.domains.api_keys.models import UserAPIKey
from data_platform.chat_backend.domains.identity.models import RequestUser


def _build_public_api_key_payload(api_key_row: UserAPIKey | dict[str, Any]) -> dict[str, Any]:
    if isinstance(api_key_row, UserAPIKey):
        row = api_key_row.__dict__
    else:
        row = api_key_row
    raw_key = str(row.get("api_key_raw") or "")
    prefix = str(row.get("api_key_prefix") or raw_key[:18])
    return {
        "user_id": row.get("user_id"),
        "api_key_id": row.get("api_key_id"),
        "api_key_prefix": prefix,
        "api_key_last4": raw_key[-4:] if raw_key else "",
        "status": row.get("status"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "last_used_at": row.get("last_used_at"),
        "revoked_at": row.get("revoked_at"),
    }


def _ensure_user_api_key(conn, user: RequestUser) -> UserAPIKey:
    existing = _fetch_optional_one(
        conn,
        """
        SELECT user_id, api_key_id, api_key_prefix, api_key_raw, status, created_at, updated_at, last_used_at, revoked_at
        FROM app.user_api_key
        WHERE user_id = %s
        LIMIT 1
        """,
        [user.user_id],
    )
    if existing is not None:
        return UserAPIKey(**existing)

    api_key_raw = _build_api_key()
    api_key_id = _generate_id("uak")
    api_key_prefix = api_key_raw[: min(len(api_key_raw), 18)]
    api_key_hash = _hash_api_key(api_key_raw)
    row = _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.user_api_key (
            user_id, api_key_id, api_key_prefix, api_key_hash, api_key_raw, status, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, 'active', NOW(), NOW())
        RETURNING user_id, api_key_id, api_key_prefix, api_key_raw, status, created_at, updated_at, last_used_at, revoked_at
        """,
        [user.user_id, api_key_id, api_key_prefix, api_key_hash, api_key_raw],
    )[0]
    return UserAPIKey(**row)


def _list_api_keys_for_user(conn, user_id: str) -> list[dict[str, Any]]:
    rows = _run_pg_dict_query(
        conn,
        """
        SELECT user_id, api_key_id, api_key_prefix, api_key_raw, status, created_at, updated_at, last_used_at, revoked_at
        FROM app.user_api_key
        WHERE user_id = %s
        ORDER BY created_at DESC, api_key_id DESC
        """,
        [user_id],
    )
    return [_build_public_api_key_payload(row) for row in rows]


def _resolve_user_api_key(conn, api_key: str) -> dict[str, Any] | None:
    api_key_hash = _hash_api_key(api_key)
    return _fetch_optional_one(
        conn,
        """
        SELECT user_id, api_key_id, api_key_prefix, api_key_raw, status, created_at, updated_at, last_used_at, revoked_at
        FROM app.user_api_key
        WHERE api_key_hash = %s
        LIMIT 1
        """,
        [api_key_hash],
    )


def _touch_user_api_key(conn, api_key_id: str) -> None:
    _run_pg_dict_query(
        conn,
        """
        UPDATE app.user_api_key
        SET last_used_at = NOW(), updated_at = NOW()
        WHERE api_key_id = %s
        RETURNING api_key_id
        """,
        [api_key_id],
    )
