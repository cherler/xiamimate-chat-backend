"""HTTP-layer helpers: response builders, idempotency, rate limiting, auth.

Depends on ``infra.settings`` and ``infra.postgres``.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder

try:
    import psycopg2.extras
except ImportError:
    pass

from data_platform.chat_backend.infra.settings import (
    ADMIN_BACKOFFICE_TOKEN,
    ADMIN_OPERATOR_HEADER_NAME,
    API_RESPONSE_SCHEMA,
    IDEMPOTENCY_KEY_HEADER_NAME,
    INTERNAL_RATE_LIMIT_MAX_REQUESTS,
    INTERNAL_RATE_LIMIT_WINDOW_SECONDS,
    INTERNAL_SERVICE_SECRET,
    INTERNAL_SERVICE_SECRET_HEADER_NAME,
    INTERNAL_SERVICE_NAME_HEADER_NAME,
    TRUSTED_ADMIN_SERVICE_NAME,
    TRUSTED_ADMIN_SESSION_HEADER_NAME,
    _utc_now_iso,
)
from data_platform.chat_backend.infra.postgres import (
    _fetch_optional_one,
    _run_pg_dict_query,
)


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------

def _response_meta(endpoint: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = {
        "endpoint": endpoint,
        "api_version": "2026-04-13",
        "response_schema": API_RESPONSE_SCHEMA,
        "generated_at": _utc_now_iso(),
    }
    if extra:
        meta.update(extra)
    return meta


def _success_response(endpoint: str, data: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "success": True,
        "code": "OK",
        "message": message,
        "data": data,
        "meta": _response_meta(endpoint),
    }


def _error_response(endpoint: str, code: str, message: str) -> dict[str, Any]:
    return {
        "success": False,
        "code": code,
        "message": message,
        "data": {},
        "meta": _response_meta(endpoint),
    }


# ---------------------------------------------------------------------------
# Idempotency helpers
# ---------------------------------------------------------------------------

def _payload_to_dict(payload: Any) -> dict[str, Any]:
    if hasattr(payload, "dict"):
        return payload.dict()
    if isinstance(payload, dict):
        return payload
    return {"value": payload}


def _build_request_hash(payload: Any) -> str:
    serialized = json.dumps(jsonable_encoder(_payload_to_dict(payload)), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _begin_idempotent_request(conn, scope: str, idempotency_key: str, request_hash: str) -> dict[str, Any] | None:
    inserted = _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.idempotency_request (
            scope, idempotency_key, request_hash, response_json, status_code, created_at, updated_at
        ) VALUES (%s, %s, %s, NULL, NULL, NOW(), NOW())
        ON CONFLICT (scope, idempotency_key) DO NOTHING
        RETURNING scope, idempotency_key
        """,
        [scope, idempotency_key, request_hash],
    )
    if inserted:
        return None

    existing = _fetch_optional_one(
        conn,
        """
        SELECT scope, idempotency_key, request_hash, response_json, status_code
        FROM app.idempotency_request
        WHERE scope = %s AND idempotency_key = %s
        LIMIT 1
        """,
        [scope, idempotency_key],
    )
    if existing is None:
        raise HTTPException(status_code=409, detail="idempotency request conflict")
    if existing["request_hash"] != request_hash:
        raise HTTPException(status_code=409, detail="idempotency key reused with different payload")
    if existing["response_json"] is None:
        raise HTTPException(status_code=409, detail="idempotent request is still in progress")
    return existing["response_json"]


def _complete_idempotent_request(conn, scope: str, idempotency_key: str, response_json: dict[str, Any]) -> None:
    serializable_response = jsonable_encoder(response_json)
    _run_pg_dict_query(
        conn,
        """
        UPDATE app.idempotency_request
        SET response_json = %s,
            status_code = 200,
            updated_at = NOW()
        WHERE scope = %s AND idempotency_key = %s
        RETURNING scope
        """,
        [psycopg2.extras.Json(serializable_response), scope, idempotency_key],
    )


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

_internal_rate_limit_lock = threading.Lock()
_internal_rate_limit_buckets: dict[str, deque[float]] = defaultdict(deque)


def _enforce_internal_rate_limit(scope: str, service_name: str) -> None:
    bucket_key = f"{service_name}:{scope}"
    now = time.monotonic()
    with _internal_rate_limit_lock:
        bucket = _internal_rate_limit_buckets[bucket_key]
        while bucket and bucket[0] <= now - INTERNAL_RATE_LIMIT_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= INTERNAL_RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(status_code=429, detail="internal request rate limit exceeded")
        bucket.append(now)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _require_idempotency_key(request: Request) -> str:
    idempotency_key = (request.headers.get(IDEMPOTENCY_KEY_HEADER_NAME) or "").strip()
    if not idempotency_key:
        raise HTTPException(status_code=400, detail=f"missing header: {IDEMPOTENCY_KEY_HEADER_NAME}")
    return idempotency_key


def _require_internal_service(request: Request, scope: str) -> str:
    if not INTERNAL_SERVICE_SECRET:
        raise HTTPException(status_code=500, detail="CHAT_BACKEND_SERVICE_SECRET is not configured")
    provided_secret = (request.headers.get(INTERNAL_SERVICE_SECRET_HEADER_NAME) or "").strip()
    if not provided_secret or not secrets.compare_digest(provided_secret, INTERNAL_SERVICE_SECRET):
        raise HTTPException(status_code=401, detail="invalid internal service secret")
    service_name = (request.headers.get(INTERNAL_SERVICE_NAME_HEADER_NAME) or "internal-client").strip()
    _enforce_internal_rate_limit(scope=scope, service_name=service_name or "internal-client")
    return service_name or "internal-client"


def _require_admin_operator(request: Request) -> str:
    operator_id = (request.headers.get(ADMIN_OPERATOR_HEADER_NAME) or "").strip()
    if INTERNAL_SERVICE_SECRET:
        provided_secret = (request.headers.get(INTERNAL_SERVICE_SECRET_HEADER_NAME) or "").strip()
        service_name = (request.headers.get(INTERNAL_SERVICE_NAME_HEADER_NAME) or "").strip()
        trusted_admin_verified = (request.headers.get(TRUSTED_ADMIN_SESSION_HEADER_NAME) or "").strip()
        if (
            provided_secret
            and secrets.compare_digest(provided_secret, INTERNAL_SERVICE_SECRET)
            and service_name == TRUSTED_ADMIN_SERVICE_NAME
            and trusted_admin_verified == "1"
        ):
            if not operator_id:
                raise HTTPException(status_code=400, detail=f"missing header: {ADMIN_OPERATOR_HEADER_NAME}")
            _enforce_internal_rate_limit(scope=request.url.path, service_name=service_name)
            return operator_id

    if not ADMIN_BACKOFFICE_TOKEN:
        raise HTTPException(status_code=503, detail="CHAT_BACKEND_ADMIN_TOKEN is not configured")
    authorization = (request.headers.get("Authorization") or "").strip()
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    provided_token = authorization.split(" ", 1)[1].strip()
    if not provided_token or not secrets.compare_digest(provided_token, ADMIN_BACKOFFICE_TOKEN):
        raise HTTPException(status_code=403, detail="invalid admin token")
    if not operator_id:
        raise HTTPException(status_code=400, detail=f"missing header: {ADMIN_OPERATOR_HEADER_NAME}")
    return operator_id
