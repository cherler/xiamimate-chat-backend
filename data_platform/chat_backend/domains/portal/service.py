"""Portal domain — short-lived token management."""
from __future__ import annotations

import os
import secrets
import threading
import time

import requests as http_requests
from fastapi import HTTPException, Request

from data_platform.chat_backend.infra.settings import (
    PORTAL_INTERNAL_BASE_URL,
    PORTAL_PUBLIC_BASE_URL,
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


def _portal_public_base_url() -> str:
    if PORTAL_PUBLIC_BASE_URL:
        return PORTAL_PUBLIC_BASE_URL.rstrip("/")
    return _backend_base_url()


def _portal_internal_base_url() -> str:
    if PORTAL_INTERNAL_BASE_URL:
        return PORTAL_INTERNAL_BASE_URL.rstrip("/")
    if PORTAL_PUBLIC_BASE_URL:
        return PORTAL_PUBLIC_BASE_URL.rstrip("/")
    return _backend_base_url()


def _portal_base_url() -> str:
    return _portal_public_base_url()


def _backend_base_url() -> str:
    backend_base_url = (os.environ.get("CHAT_BACKEND_BASE_URL") or "").strip()
    if backend_base_url:
        return backend_base_url.rstrip("/")
    port = os.environ.get("CHAT_BACKEND_PORT", os.environ.get("PORT", "8200"))
    return f"http://localhost:{port}"


def _resolve_openwebui_access_token_user(token: str) -> tuple[str, str, str] | None:
    normalized = str(token or "").strip()
    if not normalized:
        return None
    try:
        response = http_requests.get(
            f"{_portal_internal_base_url()}/api/v1/auths/",
            headers={"Authorization": f"Bearer {normalized}"},
            timeout=5,
        )
    except Exception:
        return None
    if response.status_code != 200:
        return None
    try:
        user_data = response.json()
    except Exception:
        return None

    user_id = str(user_data.get("id") or "").strip()
    if not user_id:
        return None
    email = str(user_data.get("email") or "").strip()
    display_name = str(user_data.get("name") or "").strip() or user_id
    return user_id, email, display_name


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
    if user_id is not None:
        return user_id

    resolved_user = _resolve_openwebui_access_token_user(token)
    if resolved_user is None:
        raise HTTPException(status_code=401, detail="invalid or expired portal token")

    user_id, email, display_name = resolved_user
    from data_platform.chat_backend.domains.identity.service import _ensure_user_record
    from data_platform.chat_backend.infra.postgres import _postgres_conn

    with _postgres_conn() as conn:
        _ensure_user_record(conn, user_id=user_id, email=email, display_name=display_name)
    return user_id
