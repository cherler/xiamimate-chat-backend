"""Data-access layer for the workspace domain.

纯 CRUD，所有 SQL 都收敛在此处；service 层只负责编排与业务规则。
入参 ``conn`` 由调用方通过 ``_postgres_conn()`` 提供（事务边界在调用方）。
"""
from __future__ import annotations

from typing import Any

import psycopg2.extras

from data_platform.chat_backend.infra.postgres import (
    _fetch_optional_one,
    _run_pg_dict_query,
)


def _json(value: dict[str, Any] | None) -> Any:
    return psycopg2.extras.Json(value or {})


# ---------------------------------------------------------------------------
# workspace
# ---------------------------------------------------------------------------

def lock_user_theme(conn, user_id: str, theme_key: str) -> None:
    """事务级 advisory 锁，避免同一 (user, theme) 并发 upsert 产生重复工作台。"""
    _run_pg_dict_query(
        conn,
        "SELECT pg_advisory_xact_lock(hashtext(%s))",
        [f"workspace:{user_id}:{theme_key}"],
    )


def find_active_workspace_by_theme(conn, user_id: str, theme_key: str) -> dict[str, Any] | None:
    return _fetch_optional_one(
        conn,
        """
        SELECT * FROM app.workspace
        WHERE user_id = %s AND theme_key = %s AND status = 'active'
        LIMIT 1
        """,
        [user_id, theme_key],
    )


def insert_workspace(
    conn,
    *,
    workspace_id: str,
    user_id: str,
    theme_key: str,
    title: str,
    source_run_id: str | None,
    brief: dict[str, Any] | None,
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    rows = _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.workspace (
            workspace_id, user_id, theme_key, title, source_run_id,
            brief_json, evidence_json, status, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', NOW(), NOW())
        RETURNING *
        """,
        [
            workspace_id,
            user_id,
            theme_key,
            title,
            source_run_id,
            _json(brief),
            _json(evidence),
        ],
    )
    return rows[0]


def update_workspace_payload(
    conn,
    *,
    workspace_id: str,
    title: str,
    source_run_id: str | None,
    brief: dict[str, Any] | None,
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    rows = _run_pg_dict_query(
        conn,
        """
        UPDATE app.workspace
        SET title = %s,
            source_run_id = COALESCE(%s, source_run_id),
            brief_json = %s,
            evidence_json = %s,
            updated_at = NOW()
        WHERE workspace_id = %s
        RETURNING *
        """,
        [title, source_run_id, _json(brief), _json(evidence), workspace_id],
    )
    return rows[0]


def get_workspace_for_user(conn, user_id: str, workspace_id: str) -> dict[str, Any] | None:
    return _fetch_optional_one(
        conn,
        """
        SELECT * FROM app.workspace
        WHERE workspace_id = %s AND user_id = %s
        LIMIT 1
        """,
        [workspace_id, user_id],
    )


def get_workspace_by_id(conn, workspace_id: str) -> dict[str, Any] | None:
    """按 workspace_id 取（不带 user 过滤）。仅供已验签的公开证据图路由使用。"""
    return _fetch_optional_one(
        conn,
        "SELECT * FROM app.workspace WHERE workspace_id = %s LIMIT 1",
        [workspace_id],
    )


def list_workspaces_for_user(conn, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT * FROM app.workspace
        WHERE user_id = %s AND status = 'active'
        ORDER BY updated_at DESC
        LIMIT %s
        """,
        [user_id, max(1, min(int(limit), 200))],
    )


# ---------------------------------------------------------------------------
# workspace_asset
# ---------------------------------------------------------------------------

def insert_asset(
    conn,
    *,
    asset_id: str,
    workspace_id: str,
    asset_type: str,
    title: str | None,
    content: dict[str, Any] | None,
) -> dict[str, Any]:
    rows = _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.workspace_asset (
            asset_id, workspace_id, asset_type, title, content_json,
            status, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, 'ready', NOW(), NOW())
        RETURNING *
        """,
        [asset_id, workspace_id, asset_type, title, _json(content)],
    )
    return rows[0]


def list_assets(conn, workspace_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT * FROM app.workspace_asset
        WHERE workspace_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        [workspace_id, max(1, min(int(limit), 200))],
    )


# ---------------------------------------------------------------------------
# workspace_watch
# ---------------------------------------------------------------------------

def upsert_watch(
    conn,
    *,
    workspace_id: str,
    user_id: str,
    watch_enabled: bool,
    watch_config: dict[str, Any] | None,
) -> dict[str, Any]:
    rows = _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.workspace_watch (
            workspace_id, user_id, watch_enabled, watch_config_json,
            created_at, updated_at
        ) VALUES (%s, %s, %s, %s, NOW(), NOW())
        ON CONFLICT (workspace_id) DO UPDATE
        SET watch_enabled = EXCLUDED.watch_enabled,
            watch_config_json = EXCLUDED.watch_config_json,
            updated_at = NOW()
        RETURNING *
        """,
        [workspace_id, user_id, watch_enabled, _json(watch_config)],
    )
    return rows[0]


def get_watch(conn, workspace_id: str) -> dict[str, Any] | None:
    return _fetch_optional_one(
        conn,
        "SELECT * FROM app.workspace_watch WHERE workspace_id = %s LIMIT 1",
        [workspace_id],
    )


# ---------------------------------------------------------------------------
# workspace_alert
# ---------------------------------------------------------------------------

def list_alerts_for_user(conn, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT * FROM app.workspace_alert
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        [user_id, max(1, min(int(limit), 200))],
    )
