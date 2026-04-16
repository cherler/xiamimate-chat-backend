"""Portal domain — short-lived token management."""
from __future__ import annotations

import os
import secrets
import threading
import time

from fastapi import HTTPException, Request

from data_platform.chat_backend.infra.settings import (
    PORTAL_BASE_URL,
    PORTAL_TOKEN_TTL_SECONDS,
    PORTAL_USER_ID_HEADER_NAME,
)

_PORTAL_TOKEN_STORE: dict[str, dict] = {}
_PORTAL_TOKEN_LOCK = threading.Lock()


def _generate_portal_token(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _PORTAL_TOKEN_LOCK:
        expired = [k for k, v in _PORTAL_TOKEN_STORE.items() if now - v["created_at"] > PORTAL_TOKEN_TTL_SECONDS]
        for k in expired:
            _PORTAL_TOKEN_STORE.pop(k, None)
        _PORTAL_TOKEN_STORE[token] = {"user_id": user_id, "created_at": now}
    return token


def _verify_portal_token(token: str) -> str | None:
    """Return user_id if valid, else None."""
    now = time.time()
    with _PORTAL_TOKEN_LOCK:
        entry = _PORTAL_TOKEN_STORE.get(token)
        if entry is None:
            return None
        if now - entry["created_at"] > PORTAL_TOKEN_TTL_SECONDS:
            _PORTAL_TOKEN_STORE.pop(token, None)
            return None
        return entry["user_id"]


def _portal_base_url() -> str:
    if PORTAL_BASE_URL:
        return PORTAL_BASE_URL.rstrip("/")
    return _backend_base_url()


def _backend_base_url() -> str:
    backend_base_url = (os.environ.get("CHAT_BACKEND_BASE_URL") or "").strip()
    if backend_base_url:
        return backend_base_url.rstrip("/")
    port = os.environ.get("CHAT_BACKEND_PORT", os.environ.get("PORT", "8200"))
    return f"http://localhost:{port}"


def _require_portal_user(request: Request) -> str:
    """Validate portal user from nginx session header (preferred) or Bearer token (fallback).

    When accessed through nginx, the auth_request subrequest sets X-Portal-User-Id.
    When accessed directly (e.g. dev/test), Bearer token auth is used as fallback.
    """
    # Preferred: nginx session auth (X-Portal-User-Id header set by auth_request_set)
    user_id = (request.headers.get(PORTAL_USER_ID_HEADER_NAME) or "").strip()
    if user_id:
        return user_id

    # Fallback: Bearer token auth (for backward compatibility and direct access)
    token = ""
    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        token = (request.query_params.get("t") or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")
    user_id = _verify_portal_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired portal token")
    return user_id
