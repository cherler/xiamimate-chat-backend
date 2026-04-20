"""Site config domain — admin-editable key-value settings.

Covers: contact email, enterprise WeChat QR code, feedback URL, etc.
Stores values in app.site_config with an in-memory TTL cache.
"""
from __future__ import annotations

import base64
import threading
import time
from pathlib import Path
from typing import Any

from data_platform.chat_backend.infra.postgres import (
    _postgres_conn,
    _run_pg_dict_query,
)

# ---------------------------------------------------------------------------
# Default values (used to seed DB on first startup)
# ---------------------------------------------------------------------------

_WECHAT_QR_IMAGE_PATH = Path(__file__).resolve().parents[4] / "微信二维码.jpg"

DEFAULT_SITE_CONFIG: list[dict[str, str]] = [
    {
        "config_key": "contact_email",
        "display_name": "联系邮箱",
        "config_value": "xiamijun88@qq.com",
    },
    {
        "config_key": "wechat_qr_base64",
        "display_name": "企微二维码 (base64)",
        "config_value": "",  # will be populated from file at seed time
    },
    {
        "config_key": "feedback_url",
        "display_name": "意见反馈链接",
        "config_value": "https://my.feishu.cn/share/base/form/shrcnQVnRPvEuOGjz9ojf05tD1d",
    },
]


# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------

_SITE_CONFIG_CACHE: dict[str, dict[str, Any]] = {}
_SITE_CONFIG_CACHE_LOCK = threading.Lock()
_SITE_CONFIG_CACHE_TS: float = 0.0
_SITE_CONFIG_CACHE_TTL: float = 60.0
_HIDDEN_SITE_CONFIG_KEYS = {"wechat_id"}


def _invalidate_site_config_cache() -> None:
    global _SITE_CONFIG_CACHE_TS
    with _SITE_CONFIG_CACHE_LOCK:
        _SITE_CONFIG_CACHE.clear()
        _SITE_CONFIG_CACHE_TS = 0.0


def _load_site_config_from_db(conn) -> dict[str, dict[str, Any]]:
    rows = _run_pg_dict_query(
        conn,
        """
        SELECT config_key, config_value, display_name, updated_at
        FROM app.site_config
        ORDER BY config_key ASC
        """,
    )
    return {row["config_key"]: row for row in rows}


def _get_site_config(conn) -> dict[str, dict[str, Any]]:
    global _SITE_CONFIG_CACHE, _SITE_CONFIG_CACHE_TS
    now = time.monotonic()
    if _SITE_CONFIG_CACHE and (now - _SITE_CONFIG_CACHE_TS) < _SITE_CONFIG_CACHE_TTL:
        return _SITE_CONFIG_CACHE
    with _SITE_CONFIG_CACHE_LOCK:
        if _SITE_CONFIG_CACHE and (time.monotonic() - _SITE_CONFIG_CACHE_TS) < _SITE_CONFIG_CACHE_TTL:
            return _SITE_CONFIG_CACHE
        loaded = _load_site_config_from_db(conn)
        _SITE_CONFIG_CACHE.clear()
        _SITE_CONFIG_CACHE.update(loaded)
        _SITE_CONFIG_CACHE_TS = time.monotonic()
        return _SITE_CONFIG_CACHE


def _get_site_config_value(conn, key: str, default: str = "") -> str:
    """Return a single config value by key, with fallback."""
    cfg = _get_site_config(conn)
    row = cfg.get(key)
    if row is None:
        return default
    return str(row.get("config_value") or default)


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

def _seed_site_config(conn) -> None:
    """Insert default rows if missing. Load QR image from file for initial seed."""
    for item in DEFAULT_SITE_CONFIG:
        value = item["config_value"]
        # For wechat_qr_base64, load from file on first seed
        if item["config_key"] == "wechat_qr_base64" and not value:
            if _WECHAT_QR_IMAGE_PATH.exists():
                raw = _WECHAT_QR_IMAGE_PATH.read_bytes()
                value = f"data:image/jpeg;base64,{base64.b64encode(raw).decode('ascii')}"
        _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.site_config (config_key, config_value, display_name, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (config_key) DO UPDATE
            SET display_name = EXCLUDED.display_name
            RETURNING config_key
            """,
            [item["config_key"], value, item["display_name"]],
        )
    _invalidate_site_config_cache()


# ---------------------------------------------------------------------------
# Admin update
# ---------------------------------------------------------------------------

def _update_site_config(conn, config_key: str, config_value: str) -> dict[str, Any] | None:
    rows = _run_pg_dict_query(
        conn,
        """
        UPDATE app.site_config
        SET config_value = %s, updated_at = NOW()
        WHERE config_key = %s
        RETURNING config_key, config_value, display_name, updated_at
        """,
        [config_value, config_key],
    )
    if not rows:
        return None
    _invalidate_site_config_cache()
    return rows[0]


def _list_site_config(conn) -> list[dict[str, Any]]:
    rows = _run_pg_dict_query(
        conn,
        """
        SELECT config_key, config_value, display_name, updated_at
        FROM app.site_config
        ORDER BY config_key ASC
        """,
    )
    return [row for row in rows if row.get("config_key") not in _HIDDEN_SITE_CONFIG_KEYS]


# ---------------------------------------------------------------------------
# Convenience: get contact config dict for portal rendering
# ---------------------------------------------------------------------------

def _get_contact_config(conn) -> dict[str, str]:
    """Return a flat dict of contact-related config values."""
    cfg = _get_site_config(conn)
    wechat_qr_base64 = (cfg.get("wechat_qr_base64") or {}).get("config_value", "")
    if not wechat_qr_base64 and _WECHAT_QR_IMAGE_PATH.exists():
        raw = _WECHAT_QR_IMAGE_PATH.read_bytes()
        wechat_qr_base64 = f"data:image/jpeg;base64,{base64.b64encode(raw).decode('ascii')}"
    return {
        "contact_email": (cfg.get("contact_email") or {}).get("config_value", ""),
        "wechat_qr_base64": wechat_qr_base64,
        "feedback_url": (cfg.get("feedback_url") or {}).get("config_value", ""),
    }
