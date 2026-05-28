from __future__ import annotations

import contextlib
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import string
import threading
import time
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, validator
import requests

try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool
except ImportError:
    psycopg2 = None  # type: ignore[assignment]

from data_platform.llm_client import ROOT_ENV_FILE, load_env_file_if_present
from data_platform.api.chat_backend_admin_html import render_admin_backoffice_html
from data_platform.api.chat_backend_portal_html import render_portal_html


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INIT_APP_TABLES_SQL = PROJECT_ROOT / "postgres" / "init_app_tables.sql"
API_RESPONSE_SCHEMA = "xiamimate_chat_backend_v1"
USER_ID_HEADER_NAME = "X-User-Id"
USER_EMAIL_HEADER_NAME = "X-User-Email"
USER_NAME_HEADER_NAME = "X-User-Name"
USER_API_KEY_HEADER_NAME = "X-Xia-User-Key"
INTERNAL_SERVICE_SECRET_HEADER_NAME = "X-Internal-Service-Secret"
INTERNAL_SERVICE_NAME_HEADER_NAME = "X-Internal-Service-Name"
IDEMPOTENCY_KEY_HEADER_NAME = "Idempotency-Key"
ADMIN_OPERATOR_HEADER_NAME = "X-Admin-Operator"
DEFAULT_USER_ID = os.environ.get("CHAT_BACKEND_DEFAULT_USER_ID", "demo-user")
DEFAULT_USER_EMAIL = os.environ.get("CHAT_BACKEND_DEFAULT_USER_EMAIL", "demo-user@local")
DEFAULT_USER_NAME = os.environ.get("CHAT_BACKEND_DEFAULT_USER_NAME", "Demo User")
DEFAULT_PLAN_TIER = os.environ.get("CHAT_BACKEND_DEFAULT_PLAN_TIER", "free")
SIGNUP_GIFT_POINTS = max(0, int(os.environ.get("CHAT_BACKEND_SIGNUP_GIFT_POINTS", "50")))
USER_API_KEY_PREFIX = os.environ.get("CHAT_BACKEND_USER_API_KEY_PREFIX", "xia_user_")
USER_API_KEY_LENGTH = max(24, int(os.environ.get("CHAT_BACKEND_USER_API_KEY_LENGTH", "40")))
DEFAULT_PAYMENT_PROVIDER = os.environ.get("CHAT_BACKEND_PAYMENT_PROVIDER", "manual").strip() or "manual"
INTERNAL_SERVICE_SECRET = os.environ.get("CHAT_BACKEND_SERVICE_SECRET", "").strip()
ADMIN_BACKOFFICE_TOKEN = os.environ.get("CHAT_BACKEND_ADMIN_TOKEN", "").strip()
INTERNAL_RATE_LIMIT_MAX_REQUESTS = max(1, int(os.environ.get("CHAT_BACKEND_INTERNAL_RATE_LIMIT_MAX_REQUESTS", "300")))
INTERNAL_RATE_LIMIT_WINDOW_SECONDS = max(1, int(os.environ.get("CHAT_BACKEND_INTERNAL_RATE_LIMIT_WINDOW_SECONDS", "60")))
AGENT_OPENAI_TIMEOUT = max(1, int(os.environ.get("AGENT_OPENAI_TIMEOUT", os.environ.get("DIFY_REQUEST_TIMEOUT", "180"))))
DEMO_FALLBACK_ENABLED = os.environ.get("CHAT_BACKEND_DISABLE_DEMO_FALLBACK", "false").strip().lower() not in {
    "1",
    "true",
    "yes",
    "on",
}
GUEST_DAILY_POINTS = max(0, int(os.environ.get("CHAT_BACKEND_GUEST_DAILY_POINTS", "500")))
GUEST_DAILY_USER_ALIASES = tuple(
    alias.strip().lower()
    for alias in (os.environ.get("CHAT_BACKEND_GUEST_DAILY_USERNAMES", "guest")).split(",")
    if alias.strip()
)
DAILY_RESET_TIMEZONE = os.environ.get("CHAT_BACKEND_DAILY_RESET_TIMEZONE", "Asia/Shanghai").strip() or "Asia/Shanghai"

POINTS_PRICE_VERSION = "v2_db_pricing"

DEFAULT_EVENT_PRICING: list[dict[str, Any]] = [
    {"event_type": "llm_request",      "display_name": "LLM请求",      "points_per_unit": 1, "display_order": 10},
    {"event_type": "workflow_run",     "display_name": "workflow请求", "points_per_unit": 8, "display_order": 20},
    {"event_type": "kb_retrieve",      "display_name": "知识库检索",    "points_per_unit": 2, "display_order": 30},
    {"event_type": "product_api_call", "display_name": "商品API检索",  "points_per_unit": 2, "display_order": 40},
    {"event_type": "web_search",       "display_name": "网络搜索",      "points_per_unit": 2, "display_order": 50},
]

_EVENT_PRICING_CACHE: dict[str, dict[str, Any]] = {}
_EVENT_PRICING_CACHE_LOCK = threading.Lock()
_EVENT_PRICING_CACHE_TS: float = 0.0
_EVENT_PRICING_CACHE_TTL: float = 60.0

# ---------------------------------------------------------------------------
# Portal tokens – short-lived tokens that allow users to access a self-service
# portal page without separate login. Tokens are generated via internal API
# (called from the pipeline) and consumed by the browser.
# ---------------------------------------------------------------------------
PORTAL_TOKEN_TTL_SECONDS = int(os.environ.get("CHAT_BACKEND_PORTAL_TOKEN_TTL", "1800"))  # 30 min
_PORTAL_TOKEN_STORE: dict[str, dict[str, Any]] = {}  # token -> {"user_id", "created_at"}
_PORTAL_TOKEN_LOCK = threading.Lock()
PORTAL_BASE_URL = os.environ.get("CHAT_BACKEND_PORTAL_BASE_URL", "").strip()  # e.g. http://localhost:8200

WORKFLOW_BUNDLED_NON_BILLABLE_EVENT_TYPES = {
    "kb_retrieve",
    "product_api_call",
    "llm_request",
}

THEME_API_OPERATION_PATHS: dict[str, str] = {
    "resolve_candidates": "/api/product-theme/resolve-candidates",
    "candidate_pool_stats": "/api/product-theme/candidate-pool-stats",
    "candidate_pool_trends": "/api/product-theme/candidate-pool-trends",
    "candidate_pool_weak_forecast": "/api/product-theme/candidate-pool-weak-forecast",
    "top_asin_drilldown": "/api/product-theme/top-asin-drilldown",
    "category_benchmark": "/api/product-theme/category-benchmark",
    "keepa_asin_lookup": "/api/product-theme/keepa-asin-lookup",
}

DEFAULT_BILLING_PACKAGES: list[dict[str, Any]] = [
    {
        "package_code": "credit_pack_s",
        "package_name": "Points Pack S",
        "product_type": "credit_pack",
        "price_cents": 2900,
        "points_amount": 300,
        "period_days": 0,
        "display_order": 10,
        "meta_json": {"display_price": "29 RMB", "display_points": "300 points"},
    },
    {
        "package_code": "credit_pack_m",
        "package_name": "Points Pack M",
        "product_type": "credit_pack",
        "price_cents": 7900,
        "points_amount": 900,
        "period_days": 0,
        "display_order": 20,
        "meta_json": {"display_price": "79 RMB", "display_points": "900 points"},
    },
    {
        "package_code": "credit_pack_l",
        "package_name": "Points Pack L",
        "product_type": "credit_pack",
        "price_cents": 19900,
        "points_amount": 2500,
        "period_days": 0,
        "display_order": 30,
        "meta_json": {"display_price": "199 RMB", "display_points": "2500 points"},
    },
    {
        "package_code": "monthly_basic",
        "package_name": "Monthly Basic",
        "product_type": "monthly_subscription",
        "price_cents": 9900,
        "points_amount": 1200,
        "period_days": 30,
        "display_order": 40,
        "meta_json": {"display_price": "99 RMB / month", "display_points": "1200 points / month"},
    },
]

PLAN_LIMITS: dict[str, dict[str, Any]] = {
    "free": {"daily_theme_runs": 10, "history_retention_days": 7},
    "guest": {"daily_theme_runs": 20, "history_retention_days": 7, "daily_points": GUEST_DAILY_POINTS},
    "standard": {"daily_theme_runs": 100, "history_retention_days": 30},
    "pro": {"daily_theme_runs": 1000, "history_retention_days": 365},
    "admin": {"daily_theme_runs": None, "history_retention_days": None},
}

TERMINAL_RUN_STATUSES = {"completed", "failed", "canceled"}
ALLOWED_RUN_STATUSES = {"queued", "running", "completed", "failed", "canceled"}
ALLOWED_SESSION_STATUSES = {"active", "closed", "archived"}
ALLOWED_MESSAGE_ROLES = {"user", "assistant", "system"}

load_env_file_if_present(ROOT_ENV_FILE)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def _build_api_key(prefix: str = USER_API_KEY_PREFIX, length: int = USER_API_KEY_LENGTH) -> str:
    alphabet = string.ascii_letters + string.digits
    token = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{prefix}{token}"


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


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


class CreateSessionRequest(BaseModel):
    title: str | None = None
    target_platform: str = Field(..., min_length=1)
    target_market: str | None = None
    validation_marketplace: str | None = None


class CreateMessageRequest(BaseModel):
    content: str = Field(..., min_length=1)
    role: str = Field(default="user")
    message_type: str = Field(default="text", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @validator("role")
    def _validate_role(cls, value: str) -> str:  # noqa: N805
        normalized = value.strip().lower()
        if normalized not in ALLOWED_MESSAGE_ROLES:
            raise ValueError(f"unsupported role: {value}")
        return normalized


class CreateThemeRunRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    message_id: str | None = None
    product_query: str = Field(..., min_length=1)
    analysis_goal: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)


class CallbackArtifact(BaseModel):
    artifact_type: str = Field(..., min_length=1)
    artifact_key: str = Field(..., min_length=1)
    artifact_payload: dict[str, Any] = Field(default_factory=dict)


class CallbackUsageEvent(BaseModel):
    event_type: str = Field(..., min_length=1)
    units: int = Field(default=1, ge=1)
    meta: dict[str, Any] = Field(default_factory=dict)


class GrantPointsRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    points: int = Field(..., ge=1)
    entry_type: str = Field(default="admin_grant", min_length=1)
    user_email: str | None = None
    display_name: str | None = None
    plan_tier: str | None = None
    description: str | None = None
    reference_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class AdminGrantPointsRequest(BaseModel):
    points: int = Field(..., ge=1)
    entry_type: str = Field(default="admin_grant", min_length=1)
    description: str | None = None
    reference_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class IdentityExchangeRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    email: str | None = None
    display_name: str | None = None


class ChargePointsEvent(BaseModel):
    event_type: str = Field(..., min_length=1)
    units: int = Field(default=1, ge=1)
    reference_id: str | None = None
    description: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ChargePointsRequest(BaseModel):
    api_key: str = Field(..., min_length=1)
    events: list[ChargePointsEvent] = Field(..., min_length=1)


class RefundPointsRequest(BaseModel):
    api_key: str = Field(..., min_length=1)
    event_type: str = Field(..., min_length=1)
    points: int = Field(..., ge=1)
    units: int = Field(default=1, ge=1)
    reference_id: str | None = None
    description: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class CreatePaymentOrderRequest(BaseModel):
    package_code: str = Field(..., min_length=1)
    provider: str = Field(default=DEFAULT_PAYMENT_PROVIDER, min_length=1)


class PaymentProviderCallbackRequest(BaseModel):
    order_id: str = Field(..., min_length=1)
    provider_order_id: str | None = None
    provider_trade_no: str | None = None
    provider_subscription_id: str | None = None
    paid_amount_cents: int | None = Field(default=None, ge=1)
    period_start: datetime | None = None
    period_end: datetime | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class GrantSubscriptionRequest(BaseModel):
    period_start: datetime
    period_end: datetime
    provider_trade_no: str | None = None
    order_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class InternalWorkflowRunRequest(BaseModel):
    query: str = Field(..., min_length=1)
    user: str = Field(..., min_length=1)


class InternalKnowledgeRetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class InternalThemeAPICallRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class InternalMinimaxRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class DifyRunCallbackRequest(BaseModel):
    run_id: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)
    dify_run_id: str | None = None
    final_answer_text: str | None = None
    assistant_message: str | None = None
    assistant_message_type: str = Field(default="analysis_result", min_length=1)
    artifacts: list[CallbackArtifact] = Field(default_factory=list)
    usage_events: list[CallbackUsageEvent] = Field(default_factory=list)

    @validator("status")
    def _validate_status(cls, value: str) -> str:  # noqa: N805
        normalized = value.strip().lower()
        if normalized not in ALLOWED_RUN_STATUSES:
            raise ValueError(f"unsupported run status: {value}")
        return normalized


@dataclass
class RequestUser:
    user_id: str
    email: str
    display_name: str
    status: str
    plan_tier: str
    created_at: Any
    updated_at: Any


@dataclass
class UserAPIKey:
    user_id: str
    api_key_id: str
    api_key_prefix: str
    api_key_raw: str
    status: str
    created_at: Any
    updated_at: Any
    last_used_at: Any
    revoked_at: Any


@dataclass
class UserCreditAccount:
    user_id: str
    balance_points: int
    reserved_points: int
    lifetime_granted_points: int
    lifetime_purchased_points: int
    lifetime_spent_points: int
    created_at: Any
    updated_at: Any


_pg_pool_lock = threading.Lock()
_pg_pool = None
_internal_rate_limit_lock = threading.Lock()
_internal_rate_limit_buckets: dict[str, deque[float]] = defaultdict(deque)


def _get_pg_connect_kwargs() -> dict[str, Any]:
    return {
        "host": os.environ.get("PG_HOST", "localhost"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "dbname": os.environ.get("PG_DB", "xiamimate"),
        "user": os.environ.get("PG_USER", "xiamimate"),
        "password": os.environ.get("PG_PASSWORD", "xiamimate"),
    }


def _get_pg_pool():
    if psycopg2 is None:
        raise HTTPException(status_code=500, detail="psycopg2 is required for chat backend")

    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool

    with _pg_pool_lock:
        if _pg_pool is not None:
            return _pg_pool
        minconn = max(1, int(os.environ.get("CHAT_BACKEND_PG_POOL_MIN", "1")))
        maxconn = max(minconn, int(os.environ.get("CHAT_BACKEND_PG_POOL_MAX", "8")))
        _pg_pool = psycopg2.pool.ThreadedConnectionPool(minconn, maxconn, **_get_pg_connect_kwargs())
        return _pg_pool


@contextlib.contextmanager
def _postgres_conn():
    pool = _get_pg_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = False
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _run_pg_dict_query(conn, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql, params or [])
        return [dict(row) for row in cursor.fetchall()]


def _fetch_optional_one(conn, sql: str, params: list[Any] | None = None) -> dict[str, Any] | None:
    rows = _run_pg_dict_query(conn, sql, params)
    return rows[0] if rows else None


def _ensure_app_schema(conn) -> None:
    if not INIT_APP_TABLES_SQL.exists():
        raise FileNotFoundError(f"init_app_tables.sql not found: {INIT_APP_TABLES_SQL}")
    with conn.cursor() as cursor:
        cursor.execute(INIT_APP_TABLES_SQL.read_text(encoding="utf-8"))


def _reset_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(DAILY_RESET_TIMEZONE)
    except Exception:
        return ZoneInfo("UTC")


def _current_quota_date() -> date:
    return datetime.now(_reset_timezone()).date()


def _email_local_part(email: str) -> str:
    return (email or "").split("@", 1)[0].strip().lower()


def _is_guest_identity(user_id: str, email: str, display_name: str, plan_tier: str | None = None) -> bool:
    if (plan_tier or "").strip().lower() == "guest":
        return True
    aliases = set(GUEST_DAILY_USER_ALIASES)
    if not aliases:
        return False
    candidates = {
        (user_id or "").strip().lower(),
        (display_name or "").strip().lower(),
        _email_local_part(email or ""),
    }
    return any(candidate in aliases for candidate in candidates if candidate)


def _resolve_initial_plan_tier(user_id: str, email: str, display_name: str) -> str:
    if _is_guest_identity(user_id=user_id, email=email, display_name=display_name):
        return "guest"
    return DEFAULT_PLAN_TIER


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


def _upsert_user_row(
    conn,
    user_id: str,
    email: str,
    display_name: str,
    plan_tier: str | None = None,
) -> RequestUser:
    effective_plan_tier = (plan_tier or "").strip() or _resolve_initial_plan_tier(
        user_id=user_id,
        email=email,
        display_name=display_name,
    )
    rows = _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.app_user (
            user_id, email, display_name, status, plan_tier, created_at, updated_at
        ) VALUES (
            %s, %s, %s, 'active', %s, NOW(), NOW()
        )
        ON CONFLICT (user_id) DO UPDATE SET
            email = EXCLUDED.email,
            display_name = EXCLUDED.display_name,
            updated_at = NOW()
        RETURNING user_id, email, display_name, status, plan_tier, created_at, updated_at
        """,
        [user_id, email, display_name, effective_plan_tier],
    )
    row = rows[0]
    return RequestUser(**row)


def _upsert_user(conn, request: Request) -> RequestUser:
    user_id, email, display_name = _normalize_user_headers(request)
    return _upsert_user_row(conn, user_id=user_id, email=email, display_name=display_name)


def _fetch_user(conn, user_id: str) -> RequestUser:
    row = _fetch_optional_one(
        conn,
        """
        SELECT user_id, email, display_name, status, plan_tier, created_at, updated_at
        FROM app.app_user
        WHERE user_id = %s
        LIMIT 1
        """,
        [user_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"user not found: {user_id}")
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
        """
        SELECT user_id, email, display_name, status, plan_tier, created_at, updated_at
        FROM app.app_user
        WHERE user_id = %s
        LIMIT 1
        """,
        [user_id],
    )
    if existing is not None:
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


def _ensure_credit_account(conn, user_id: str) -> UserCreditAccount:
    row = _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.user_credit_account (
            user_id, balance_points, reserved_points, lifetime_granted_points,
            lifetime_purchased_points, lifetime_spent_points, created_at, updated_at
        ) VALUES (%s, 0, 0, 0, 0, 0, NOW(), NOW())
        ON CONFLICT (user_id) DO UPDATE SET updated_at = app.user_credit_account.updated_at
        RETURNING user_id, balance_points, reserved_points, lifetime_granted_points,
                  lifetime_purchased_points, lifetime_spent_points, created_at, updated_at
        """,
        [user_id],
    )[0]
    return UserCreditAccount(**row)


def _get_credit_account(conn, user_id: str, for_update: bool) -> dict[str, Any]:
    clause = " FOR UPDATE" if for_update else ""
    row = _fetch_optional_one(
        conn,
        f"""
        SELECT user_id, balance_points, reserved_points, lifetime_granted_points,
               lifetime_purchased_points, lifetime_spent_points, created_at, updated_at
        FROM app.user_credit_account
        WHERE user_id = %s
        LIMIT 1{clause}
        """,
        [user_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"credit account not found: {user_id}")
    return row


def _create_ledger_entry(
    conn,
    user_id: str,
    api_key_id: str | None,
    entry_type: str,
    event_type: str | None,
    units: int,
    points_delta: int,
    balance_after_points: int,
    reference_id: str | None,
    description: str | None,
    meta_json: dict[str, Any],
) -> dict[str, Any]:
    return _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.credit_ledger_entry (
            entry_id, user_id, api_key_id, entry_type, event_type, units, points_delta,
            balance_after_points, reference_id, description, meta_json, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING entry_id, user_id, api_key_id, entry_type, event_type, units,
                  points_delta, balance_after_points, reference_id, description, meta_json, created_at
        """,
        [
            _generate_id("ledger"),
            user_id,
            api_key_id,
            entry_type,
            event_type,
            units,
            points_delta,
            balance_after_points,
            reference_id,
            description,
            psycopg2.extras.Json(meta_json),
        ],
    )[0]


def _credit_points_account(
    conn,
    user_id: str,
    points: int,
    granted_points: int = 0,
    purchased_points: int = 0,
) -> dict[str, Any]:
    _ensure_credit_account(conn, user_id)
    account = _get_credit_account(conn, user_id, for_update=True)
    balance_after = int(account["balance_points"]) + points
    return _run_pg_dict_query(
        conn,
        """
        UPDATE app.user_credit_account
        SET balance_points = %s,
            lifetime_granted_points = lifetime_granted_points + %s,
            lifetime_purchased_points = lifetime_purchased_points + %s,
            updated_at = NOW()
        WHERE user_id = %s
        RETURNING user_id, balance_points, reserved_points, lifetime_granted_points,
                  lifetime_purchased_points, lifetime_spent_points, created_at, updated_at
        """,
        [balance_after, granted_points, purchased_points, user_id],
    )[0]


def _grant_points_with_ledger(
    conn,
    user_id: str,
    points: int,
    entry_type: str,
    event_type: str,
    reference_id: str | None,
    description: str | None,
    meta_json: dict[str, Any],
    api_key_id: str | None = None,
    granted_points: int = 0,
    purchased_points: int = 0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated_account = _credit_points_account(
        conn,
        user_id=user_id,
        points=points,
        granted_points=granted_points,
        purchased_points=purchased_points,
    )
    ledger_entry = _create_ledger_entry(
        conn=conn,
        user_id=user_id,
        api_key_id=api_key_id,
        entry_type=entry_type,
        event_type=event_type,
        units=1,
        points_delta=points,
        balance_after_points=int(updated_account["balance_points"]),
        reference_id=reference_id,
        description=description,
        meta_json=meta_json,
    )
    return updated_account, ledger_entry


def _record_usage_event(
    conn,
    user_id: str,
    event_type: str,
    units: int,
    meta_json: dict[str, Any],
    session_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    return _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.usage_event (
            event_id, user_id, session_id, run_id, event_type, units, meta_json, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING event_id, user_id, session_id, run_id, event_type, units, meta_json, created_at
        """,
        [
            _generate_id("usage"),
            user_id,
            session_id,
            run_id,
            event_type,
            units,
            psycopg2.extras.Json(meta_json),
        ],
    )[0]


def _fetch_daily_credit_quota_state(conn, user_id: str, quota_date: date) -> dict[str, Any] | None:
    return _fetch_optional_one(
        conn,
        """
        SELECT user_id, quota_date, quota_points, applied_delta_points, consumed_points,
               reset_reference_id, created_at, updated_at
        FROM app.daily_credit_quota_state
        WHERE user_id = %s AND quota_date = %s
        LIMIT 1
        """,
        [user_id, quota_date],
    )


def _fetch_latest_daily_credit_quota_state(conn, user_id: str) -> dict[str, Any] | None:
    return _fetch_optional_one(
        conn,
        """
        SELECT user_id, quota_date, quota_points, applied_delta_points, consumed_points,
               reset_reference_id, created_at, updated_at
        FROM app.daily_credit_quota_state
        WHERE user_id = %s
        ORDER BY quota_date DESC, updated_at DESC
        LIMIT 1
        """,
        [user_id],
    )


def _is_guest_daily_quota_user(user: RequestUser) -> bool:
    return _is_guest_identity(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        plan_tier=user.plan_tier,
    )


def _adjust_daily_credit_quota_consumed(conn, user_id: str, delta_points: int) -> None:
    if delta_points == 0:
        return
    quota_date = _current_quota_date()
    _run_pg_dict_query(
        conn,
        """
        UPDATE app.daily_credit_quota_state
        SET consumed_points = GREATEST(0, consumed_points + %s),
            updated_at = NOW()
        WHERE user_id = %s AND quota_date = %s
        RETURNING user_id, quota_date
        """,
        [delta_points, user_id, quota_date],
    )


def _apply_guest_daily_quota_if_needed(conn, user: RequestUser) -> UserCreditAccount:
    _ensure_credit_account(conn, user.user_id)
    quota_date = _current_quota_date()
    existing_state = _fetch_daily_credit_quota_state(conn, user.user_id, quota_date)
    if existing_state is not None:
        return UserCreditAccount(**_get_credit_account(conn, user.user_id, for_update=False))

    account = _get_credit_account(conn, user.user_id, for_update=True)
    target_points = GUEST_DAILY_POINTS
    current_balance = int(account["balance_points"])
    delta_points = target_points - current_balance
    updated_account = account
    reference_id = f"guest_daily_quota:{user.user_id}:{quota_date.isoformat()}"

    if delta_points > 0:
        updated_account = _credit_points_account(
            conn,
            user_id=user.user_id,
            points=delta_points,
            granted_points=delta_points,
        )
    elif delta_points < 0:
        updated_account = _run_pg_dict_query(
            conn,
            """
            UPDATE app.user_credit_account
            SET balance_points = %s,
                updated_at = NOW()
            WHERE user_id = %s
            RETURNING user_id, balance_points, reserved_points, lifetime_granted_points,
                      lifetime_purchased_points, lifetime_spent_points, created_at, updated_at
            """,
            [target_points, user.user_id],
        )[0]

    if delta_points != 0:
        _create_ledger_entry(
            conn=conn,
            user_id=user.user_id,
            api_key_id=None,
            entry_type="daily_quota_reset",
            event_type="daily_quota_reset",
            units=1,
            points_delta=delta_points,
            balance_after_points=int(updated_account["balance_points"]),
            reference_id=reference_id,
            description=f"guest daily quota reset to {target_points} points",
            meta_json={
                "policy": "guest_daily_points",
                "quota_date": quota_date.isoformat(),
                "quota_points": target_points,
                "points_price_version": POINTS_PRICE_VERSION,
            },
        )

    _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.daily_credit_quota_state (
            user_id, quota_date, quota_points, applied_delta_points, consumed_points,
            reset_reference_id, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
        RETURNING user_id, quota_date
        """,
        [user.user_id, quota_date, target_points, delta_points, 0, reference_id],
    )
    return UserCreditAccount(**updated_account)


def _ensure_user_credit_account_state(conn, user: RequestUser) -> UserCreditAccount:
    if _is_guest_daily_quota_user(user):
        return _apply_guest_daily_quota_if_needed(conn, user)
    return _grant_signup_gift_if_needed(conn, user.user_id)


def _audit_admin_action(
    conn,
    operator_id: str,
    action: str,
    target_type: str,
    target_id: str | None,
    request_json: dict[str, Any],
    result_json: dict[str, Any],
) -> dict[str, Any]:
    return _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.admin_audit_log (
            audit_id, operator_id, action, target_type, target_id, request_json, result_json, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING audit_id, operator_id, action, target_type, target_id, request_json, result_json, created_at
        """,
        [
            _generate_id("admin_audit"),
            operator_id,
            action,
            target_type,
            target_id,
            psycopg2.extras.Json(request_json),
            psycopg2.extras.Json(result_json),
        ],
    )[0]


def _seed_billing_packages(conn) -> None:
    for package in DEFAULT_BILLING_PACKAGES:
        _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.billing_package (
                package_code, package_name, product_type, price_cents, points_amount,
                period_days, status, display_order, meta_json, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, 'active', %s, %s, NOW(), NOW())
            ON CONFLICT (package_code) DO UPDATE SET
                package_name = EXCLUDED.package_name,
                product_type = EXCLUDED.product_type,
                price_cents = EXCLUDED.price_cents,
                points_amount = EXCLUDED.points_amount,
                period_days = EXCLUDED.period_days,
                display_order = EXCLUDED.display_order,
                meta_json = EXCLUDED.meta_json,
                updated_at = NOW()
            RETURNING package_code
            """,
            [
                package["package_code"],
                package["package_name"],
                package["product_type"],
                package["price_cents"],
                package["points_amount"],
                package["period_days"],
                package["display_order"],
                psycopg2.extras.Json(package.get("meta_json") or {}),
            ],
        )


def _fetch_billing_package(conn, package_code: str) -> dict[str, Any]:
    row = _fetch_optional_one(
        conn,
        """
        SELECT package_code, package_name, product_type, price_cents, points_amount,
               period_days, status, display_order, meta_json, created_at, updated_at
        FROM app.billing_package
        WHERE package_code = %s
        LIMIT 1
        """,
        [package_code],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"billing package not found: {package_code}")
    if row["status"] != "active":
        raise HTTPException(status_code=409, detail=f"billing package is not active: {package_code}")
    return row


def _list_billing_packages(conn) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT package_code, package_name, product_type, price_cents, points_amount,
               period_days, status, display_order, meta_json, created_at, updated_at
        FROM app.billing_package
        WHERE status = 'active'
        ORDER BY display_order ASC, created_at ASC, package_code ASC
        """,
    )


def _seed_billing_event_pricing(conn) -> None:
    for row in DEFAULT_EVENT_PRICING:
        _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.billing_event_pricing (
                event_type, display_name, points_per_unit, status, display_order, created_at, updated_at
            ) VALUES (%s, %s, %s, 'active', %s, NOW(), NOW())
            ON CONFLICT (event_type) DO NOTHING
            RETURNING event_type
            """,
            [row["event_type"], row["display_name"], row["points_per_unit"], row["display_order"]],
        )


def _load_event_pricing_from_db(conn) -> dict[str, dict[str, Any]]:
    rows = _run_pg_dict_query(
        conn,
        """
        SELECT event_type, display_name, points_per_unit, status, display_order
        FROM app.billing_event_pricing
        WHERE status = 'active'
        ORDER BY display_order ASC, event_type ASC
        """,
    )
    return {row["event_type"]: row for row in rows}


def _get_event_pricing(conn=None) -> dict[str, dict[str, Any]]:
    global _EVENT_PRICING_CACHE, _EVENT_PRICING_CACHE_TS
    now = time.monotonic()
    if _EVENT_PRICING_CACHE and (now - _EVENT_PRICING_CACHE_TS) < _EVENT_PRICING_CACHE_TTL:
        return _EVENT_PRICING_CACHE
    with _EVENT_PRICING_CACHE_LOCK:
        if _EVENT_PRICING_CACHE and (now - _EVENT_PRICING_CACHE_TS) < _EVENT_PRICING_CACHE_TTL:
            return _EVENT_PRICING_CACHE
        try:
            if conn is not None:
                pricing = _load_event_pricing_from_db(conn)
            else:
                with _postgres_conn() as c:
                    pricing = _load_event_pricing_from_db(c)
            if pricing:
                _EVENT_PRICING_CACHE = pricing
                _EVENT_PRICING_CACHE_TS = time.monotonic()
        except Exception:
            pass
    if not _EVENT_PRICING_CACHE:
        _EVENT_PRICING_CACHE = {
            row["event_type"]: {
                "event_type": row["event_type"],
                "display_name": row["display_name"],
                "points_per_unit": row["points_per_unit"],
                "status": "active",
                "display_order": row["display_order"],
            }
            for row in DEFAULT_EVENT_PRICING
        }
        _EVENT_PRICING_CACHE_TS = time.monotonic()
    return _EVENT_PRICING_CACHE


def _invalidate_event_pricing_cache() -> None:
    global _EVENT_PRICING_CACHE_TS
    _EVENT_PRICING_CACHE_TS = 0.0


def _get_point_cost_by_event() -> dict[str, int]:
    pricing = _get_event_pricing()
    return {k: v["points_per_unit"] for k, v in pricing.items()}


# ---------------------------------------------------------------------------
# Portal token helpers
# ---------------------------------------------------------------------------

def _generate_portal_token(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _PORTAL_TOKEN_LOCK:
        # Purge expired tokens lazily
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
    port = os.environ.get("CHAT_BACKEND_PORT", os.environ.get("PORT", "8200"))
    return f"http://localhost:{port}"


def _fetch_payment_order(conn, order_id: str) -> dict[str, Any]:
    row = _fetch_optional_one(
        conn,
        """
        SELECT order_id, user_id, package_code, product_type, provider, amount_cents,
               points_amount, status, provider_order_id, provider_trade_no,
               callback_payload_json, paid_at, created_at, updated_at
        FROM app.payment_order
        WHERE order_id = %s
        LIMIT 1
        """,
        [order_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"payment order not found: {order_id}")
    return row


def _fetch_payment_order_for_user(conn, order_id: str, user_id: str) -> dict[str, Any]:
    row = _fetch_optional_one(
        conn,
        """
        SELECT order_id, user_id, package_code, product_type, provider, amount_cents,
               points_amount, status, provider_order_id, provider_trade_no,
               callback_payload_json, paid_at, created_at, updated_at
        FROM app.payment_order
        WHERE order_id = %s AND user_id = %s
        LIMIT 1
        """,
        [order_id, user_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"payment order not found: {order_id}")
    return row


def _fetch_subscription(conn, subscription_id: str) -> dict[str, Any]:
    row = _fetch_optional_one(
        conn,
        """
        SELECT subscription_id, user_id, package_code, provider, provider_subscription_id,
               status, monthly_points, current_period_start, current_period_end,
               next_grant_at, last_grant_at, cancel_at_period_end, meta_json,
               created_at, updated_at
        FROM app.billing_subscription
        WHERE subscription_id = %s
        LIMIT 1
        """,
        [subscription_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"subscription not found: {subscription_id}")
    return row


def _fetch_subscriptions_for_user(conn, user_id: str) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT subscription_id, user_id, package_code, provider, provider_subscription_id,
               status, monthly_points, current_period_start, current_period_end,
               next_grant_at, last_grant_at, cancel_at_period_end, meta_json,
               created_at, updated_at
        FROM app.billing_subscription
        WHERE user_id = %s
        ORDER BY updated_at DESC, created_at DESC
        """,
        [user_id],
    )


def _build_user_account_overview(
    conn,
    user_id: str,
    *,
    ledger_limit: int = 20,
    usage_limit: int = 20,
    order_limit: int = 10,
    session_limit: int = 10,
    run_limit: int = 10,
) -> dict[str, Any]:
    user = _fetch_user(conn, user_id)
    _ensure_credit_account(conn, user_id)
    if _is_guest_daily_quota_user(user):
        _apply_guest_daily_quota_if_needed(conn, user)
    points_account = _get_credit_account(conn, user_id, for_update=False)
    api_keys = _list_api_keys_for_user(conn, user_id)
    recent_ledger = _run_pg_dict_query(
        conn,
        """
        SELECT entry_id, entry_type, event_type, units, points_delta, balance_after_points,
               reference_id, description, meta_json, created_at
        FROM app.credit_ledger_entry
        WHERE user_id = %s
        ORDER BY created_at DESC, entry_id DESC
        LIMIT %s
        """,
        [user_id, ledger_limit],
    )
    usage_summary = _run_pg_dict_query(
        conn,
        """
        SELECT
            COALESCE(SUM(units) FILTER (WHERE created_at >= NOW() - INTERVAL '1 day'), 0) AS units_1d,
            COALESCE(SUM(units) FILTER (WHERE created_at >= NOW() - INTERVAL '7 day'), 0) AS units_7d,
            COALESCE(SUM(units) FILTER (WHERE created_at >= NOW() - INTERVAL '30 day'), 0) AS units_30d,
            COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '30 day') AS event_count_30d
        FROM app.usage_event
        WHERE user_id = %s
        """,
        [user_id],
    )[0]
    usage_by_type_30d = _run_pg_dict_query(
        conn,
        """
        SELECT event_type, COALESCE(SUM(units), 0) AS total_units
        FROM app.usage_event
        WHERE user_id = %s
          AND created_at >= NOW() - INTERVAL '30 day'
        GROUP BY event_type
        ORDER BY total_units DESC, event_type ASC
        """,
        [user_id],
    )
    recent_usage_events = _run_pg_dict_query(
        conn,
        """
        SELECT event_id, session_id, run_id, event_type, units, meta_json, created_at
        FROM app.usage_event
        WHERE user_id = %s
        ORDER BY created_at DESC, event_id DESC
        LIMIT %s
        """,
        [user_id, usage_limit],
    )
    recent_orders = _run_pg_dict_query(
        conn,
        """
        SELECT order_id, package_code, product_type, provider, amount_cents, points_amount,
               status, provider_order_id, provider_trade_no, paid_at, created_at, updated_at
        FROM app.payment_order
        WHERE user_id = %s
        ORDER BY created_at DESC, order_id DESC
        LIMIT %s
        """,
        [user_id, order_limit],
    )
    recent_sessions = _run_pg_dict_query(
        conn,
        """
        SELECT session_id, title, target_platform, target_market, validation_marketplace,
               status, created_at, updated_at, closed_at
        FROM app.chat_session
        WHERE user_id = %s
        ORDER BY updated_at DESC, session_id DESC
        LIMIT %s
        """,
        [user_id, session_limit],
    )
    recent_runs = _run_pg_dict_query(
        conn,
        """
        SELECT r.run_id, r.session_id, r.message_id, r.product_query, r.analysis_goal,
               r.status, r.dify_run_id, r.started_at, r.finished_at, r.created_at, r.updated_at,
               s.title AS session_title
        FROM app.analysis_run r
        JOIN app.chat_session s ON r.session_id = s.session_id
        WHERE s.user_id = %s
        ORDER BY r.updated_at DESC, r.run_id DESC
        LIMIT %s
        """,
        [user_id, run_limit],
    )
    daily_quota_state = _fetch_latest_daily_credit_quota_state(conn, user_id)
    return {
        "user": user.__dict__,
        "plan_tier": user.plan_tier,
        "entitlements": PLAN_LIMITS.get(user.plan_tier, {}),
        "api_keys": api_keys,
        "points_account": points_account,
        "daily_quota_state": daily_quota_state,
        "recent_ledger": recent_ledger,
        "usage_summary": usage_summary,
        "usage_by_type_30d": usage_by_type_30d,
        "recent_usage_events": recent_usage_events,
        "recent_orders": recent_orders,
        "subscriptions": _fetch_subscriptions_for_user(conn, user_id),
        "recent_sessions": recent_sessions,
        "recent_runs": recent_runs,
        "pricing_version": POINTS_PRICE_VERSION,
        "point_cost_by_event": _get_point_cost_by_event(),
        "event_pricing_display": {k: v["display_name"] for k, v in _get_event_pricing().items()},
    }


def _build_admin_overview(conn) -> dict[str, Any]:
    metrics = _run_pg_dict_query(
        conn,
        """
        SELECT
            (SELECT COUNT(*) FROM app.app_user) AS total_users,
            (SELECT COUNT(*) FROM app.user_api_key WHERE status = 'active') AS active_api_keys,
            (SELECT COUNT(*) FROM app.payment_order WHERE status = 'paid') AS paid_orders,
            (SELECT COUNT(*) FROM app.billing_subscription WHERE status = 'active') AS active_subscriptions,
            (SELECT COUNT(*) FROM app.analysis_run WHERE status = 'running') AS running_analysis_runs,
            (SELECT COALESCE(SUM(balance_points), 0) FROM app.user_credit_account) AS total_balance_points
        """,
    )[0]
    recent_ledger = _run_pg_dict_query(
        conn,
        """
        SELECT l.entry_id, l.user_id, u.display_name, l.entry_type, l.event_type, l.points_delta,
               l.balance_after_points, l.description, l.created_at
        FROM app.credit_ledger_entry l
        JOIN app.app_user u ON l.user_id = u.user_id
        ORDER BY l.created_at DESC, l.entry_id DESC
        LIMIT 20
        """,
    )
    recent_orders = _run_pg_dict_query(
        conn,
        """
        SELECT o.order_id, o.user_id, u.display_name, o.package_code, o.provider,
               o.amount_cents, o.points_amount, o.status, o.paid_at, o.created_at
        FROM app.payment_order o
        JOIN app.app_user u ON o.user_id = u.user_id
        ORDER BY o.created_at DESC, o.order_id DESC
        LIMIT 20
        """,
    )
    event_pricing = _load_event_pricing_from_db(conn)
    return {
        "metrics": metrics,
        "recent_ledger": recent_ledger,
        "recent_orders": recent_orders,
        "event_pricing": list(event_pricing.values()),
    }


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


def _require_idempotency_key(request: Request) -> str:
    idempotency_key = (request.headers.get(IDEMPOTENCY_KEY_HEADER_NAME) or "").strip()
    if not idempotency_key:
        raise HTTPException(status_code=400, detail=f"missing header: {IDEMPOTENCY_KEY_HEADER_NAME}")
    return idempotency_key


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
    if not ADMIN_BACKOFFICE_TOKEN:
        raise HTTPException(status_code=503, detail="CHAT_BACKEND_ADMIN_TOKEN is not configured")
    authorization = (request.headers.get("Authorization") or "").strip()
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    provided_token = authorization.split(" ", 1)[1].strip()
    if not provided_token or not secrets.compare_digest(provided_token, ADMIN_BACKOFFICE_TOKEN):
        raise HTTPException(status_code=403, detail="invalid admin token")
    operator_id = (request.headers.get(ADMIN_OPERATOR_HEADER_NAME) or "").strip()
    if not operator_id:
        raise HTTPException(status_code=400, detail=f"missing header: {ADMIN_OPERATOR_HEADER_NAME}")
    return operator_id


def _theme_api_base_url() -> str:
    base = (os.environ.get("XIAMIMATE_THEME_API_BASE_URL") or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=500, detail="XIAMIMATE_THEME_API_BASE_URL is not configured")
    return base


def _theme_api_key() -> str:
    api_key = (os.environ.get("XIAMIMATE_THEME_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="XIAMIMATE_THEME_API_KEY is not configured")
    return api_key


def _theme_api_timeout() -> int:
    return max(1, int(os.environ.get("XIAMIMATE_THEME_API_TIMEOUT", "120")))


def _dify_base_url() -> str:
    base = (os.environ.get("DIFY_BASE_URL") or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=500, detail="DIFY_BASE_URL is not configured")
    if base.endswith("/v1"):
        return base[:-3]
    return base


def _dify_timeout() -> int:
    return max(1, int(os.environ.get("DIFY_REQUEST_TIMEOUT", "180")))


def _dify_workflow_api_key() -> str:
    api_key = (os.environ.get("DIFY_WORKFLOW_APP_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="DIFY_WORKFLOW_APP_API_KEY is not configured")
    return api_key


def _dify_dataset_api_key() -> str:
    api_key = (os.environ.get("DIFY_DATASET_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="DIFY_DATASET_API_KEY is not configured")
    return api_key


def _dify_dataset_ids() -> list[str]:
    dataset_ids = [value.strip() for value in (os.environ.get("DIFY_DATASET_IDS") or "").split(",") if value.strip()]
    if not dataset_ids:
        raise HTTPException(status_code=500, detail="DIFY_DATASET_IDS is not configured")
    return dataset_ids


def _openai_base_url() -> str:
    base = (os.environ.get("AGENT_OPENAI_BASE_URL") or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=500, detail="AGENT_OPENAI_BASE_URL is not configured")
    return base


def _openai_api_key() -> str:
    api_key = (os.environ.get("AGENT_OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="AGENT_OPENAI_API_KEY is not configured")
    return api_key


def _normalize_period_window(period_start: datetime | None, period_end: datetime | None, period_days: int) -> tuple[datetime, datetime]:
    start = period_start or _utc_now()
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    end = period_end or datetime.fromtimestamp(start.timestamp() + max(1, period_days) * 86400, tz=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if end <= start:
        raise HTTPException(status_code=400, detail="subscription grant period_end must be later than period_start")
    return start, end


def _grant_subscription_period(
    conn,
    subscription_row: dict[str, Any],
    period_start: datetime,
    period_end: datetime,
    reference_id: str,
    order_id: str | None,
    meta_json: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    inserted_grant = _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.subscription_grant (
            grant_id, subscription_id, user_id, order_id, period_start, period_end,
            points_amount, reference_id, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (subscription_id, period_start, period_end) DO NOTHING
        RETURNING grant_id, subscription_id, user_id, order_id, period_start, period_end,
                  points_amount, reference_id, created_at
        """,
        [
            _generate_id("subgrant"),
            subscription_row["subscription_id"],
            subscription_row["user_id"],
            order_id,
            period_start,
            period_end,
            subscription_row["monthly_points"],
            reference_id,
        ],
    )
    if not inserted_grant:
        raise HTTPException(status_code=409, detail="subscription points already granted for this period")
    grant_row = inserted_grant[0]

    updated_account, ledger_entry = _grant_points_with_ledger(
        conn=conn,
        user_id=subscription_row["user_id"],
        points=int(subscription_row["monthly_points"]),
        entry_type="subscription_grant",
        event_type="subscription_grant",
        reference_id=reference_id,
        description="subscription points granted",
        meta_json={
            **meta_json,
            "subscription_id": subscription_row["subscription_id"],
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
        },
        purchased_points=int(subscription_row["monthly_points"]),
    )
    updated_subscription = _run_pg_dict_query(
        conn,
        """
        UPDATE app.billing_subscription
        SET status = 'active',
            current_period_start = %s,
            current_period_end = %s,
            next_grant_at = %s,
            last_grant_at = NOW(),
            updated_at = NOW()
        WHERE subscription_id = %s
        RETURNING subscription_id, user_id, package_code, provider, provider_subscription_id,
                  status, monthly_points, current_period_start, current_period_end,
                  next_grant_at, last_grant_at, cancel_at_period_end, meta_json,
                  created_at, updated_at
        """,
        [period_start, period_end, period_end, subscription_row["subscription_id"]],
    )[0]
    return updated_subscription, updated_account, grant_row, ledger_entry


def _request_error_detail(response: requests.Response | None, exc: Exception) -> str:
    if response is not None:
        try:
            payload = response.json()
            return str(payload.get("message") or payload)
        except ValueError:
            if response.text:
                return response.text
    return str(exc)


def _proxy_dify_workflow_blocking(query: str, user: str) -> dict[str, Any]:
    response = None
    try:
        response = requests.post(
            f"{_dify_base_url()}/v1/chat-messages",
            json={
                "inputs": {},
                "query": query,
                "response_mode": "blocking",
                "user": user,
            },
            headers={
                "Authorization": f"Bearer {_dify_workflow_api_key()}",
                "Content-Type": "application/json",
                "Host": "localhost",
            },
            timeout=(10, _dify_timeout()),
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=_request_error_detail(response, exc)[:4000])
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"invalid Dify JSON response: {str(exc)}")


def _proxy_dify_workflow_stream(query: str, user: str) -> requests.Response:
    response = None
    try:
        response = requests.post(
            f"{_dify_base_url()}/v1/chat-messages",
            json={
                "inputs": {},
                "query": query,
                "response_mode": "streaming",
                "user": user,
            },
            headers={
                "Authorization": f"Bearer {_dify_workflow_api_key()}",
                "Content-Type": "application/json",
                "Host": "localhost",
            },
            timeout=(10, _dify_timeout()),
            stream=True,
        )
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        if response is not None:
            response.close()
        raise HTTPException(status_code=502, detail=_request_error_detail(response, exc)[:4000])


def _proxy_knowledge_retrieve(query: str, top_k: int) -> str:
    all_records: list[dict[str, Any]] = []
    errors: list[str] = []
    for dataset_id in _dify_dataset_ids():
        response = None
        try:
            response = requests.post(
                f"{_dify_base_url()}/v1/datasets/{dataset_id}/retrieve",
                json={
                    "query": query,
                    "retrieval_model": {
                        "search_method": "hybrid_search",
                        "reranking_enable": False,
                        "top_k": top_k,
                        "score_threshold_enabled": False,
                    },
                },
                headers={
                    "Authorization": f"Bearer {_dify_dataset_api_key()}",
                    "Content-Type": "application/json",
                    "Host": "localhost",
                },
                timeout=_dify_timeout(),
            )
            response.raise_for_status()
            data = response.json()
            all_records.extend(data.get("records") or [])
        except requests.RequestException as exc:
            errors.append(f"dataset {dataset_id[:8]}: {_request_error_detail(response, exc)[:500]}")
        except ValueError as exc:
            errors.append(f"dataset {dataset_id[:8]}: invalid JSON response: {str(exc)[:500]}")

    if not all_records and errors:
        raise HTTPException(status_code=502, detail=("知识库检索失败:\n" + "\n".join(errors))[:4000])
    if not all_records:
        return f'未找到与 "{query}" 相关的知识库内容。'

    all_records.sort(key=lambda item: item.get("score", 0), reverse=True)
    snippets: list[str] = []
    for index, record in enumerate(all_records[:top_k], 1):
        segment = record.get("segment") or record
        content = str(segment.get("content") or "").strip()
        if not content:
            continue
        doc = segment.get("document") or {}
        title = doc.get("name") or record.get("document_name") or ""
        score = record.get("score", 0)
        header = f"【{index}】{title} (相关度: {score:.2f})" if title else f"【{index}】(相关度: {score:.2f})"
        snippets.append(f"{header}\n{content}")

    if not snippets:
        return f'未找到与 "{query}" 相关的知识库内容。'

    result = "找到 %d 条相关知识:\n\n%s" % (len(snippets), "\n\n---\n\n".join(snippets))
    if errors:
        result += "\n\n⚠️ 部分知识库检索失败: %s" % "; ".join(errors)
    return result


def _proxy_theme_api(operation: str, payload: dict[str, Any]) -> str:
    path = THEME_API_OPERATION_PATHS.get(operation)
    if path is None:
        raise HTTPException(status_code=404, detail=f"unsupported theme_api operation: {operation}")
    response = None
    try:
        response = requests.post(
            f"{_theme_api_base_url()}{path}",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": _theme_api_key(),
            },
            timeout=_theme_api_timeout(),
        )
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False, indent=2)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=("theme_api 请求失败:\n" + _request_error_detail(response, exc))[:4000])
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"theme_api 返回了无法解析的 JSON: {str(exc)}")


def _proxy_minimax_chat_completion(payload: dict[str, Any]) -> dict[str, Any]:
    response = None
    try:
        response = requests.post(
            f"{_openai_base_url()}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {_openai_api_key()}",
                "Content-Type": "application/json",
            },
            timeout=AGENT_OPENAI_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=_request_error_detail(response, exc)[:4000])
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"invalid OpenAI-compatible JSON response: {str(exc)}")


def _proxy_minimax_chat_completion_stream(payload: dict[str, Any]) -> requests.Response:
    response = None
    try:
        response = requests.post(
            f"{_openai_base_url()}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {_openai_api_key()}",
                "Content-Type": "application/json",
            },
            timeout=(10, AGENT_OPENAI_TIMEOUT),
            stream=True,
        )
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        if response is not None:
            response.close()
        raise HTTPException(status_code=502, detail=_request_error_detail(response, exc)[:4000])


def _grant_signup_gift_if_needed(conn, user_id: str) -> UserCreditAccount:
    _ensure_credit_account(conn, user_id)
    if SIGNUP_GIFT_POINTS <= 0:
        return UserCreditAccount(**_get_credit_account(conn, user_id, for_update=False))

    existing = _fetch_optional_one(
        conn,
        """
        SELECT entry_id
        FROM app.credit_ledger_entry
        WHERE user_id = %s AND entry_type = 'signup_gift'
        LIMIT 1
        """,
        [user_id],
    )
    if existing is not None:
        return UserCreditAccount(**_get_credit_account(conn, user_id, for_update=False))

    _grant_points_with_ledger(
        conn=conn,
        user_id=user_id,
        entry_type="signup_gift",
        event_type="signup_gift",
        reference_id=user_id,
        description="signup gift points",
        meta_json={"points_price_version": POINTS_PRICE_VERSION},
        granted_points=SIGNUP_GIFT_POINTS,
        points=SIGNUP_GIFT_POINTS,
    )
    return UserCreditAccount(**_get_credit_account(conn, user_id, for_update=False))


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


def _calculate_points_for_event(event_type: str, units: int) -> int:
    pricing = _get_event_pricing()
    entry = pricing.get(event_type)
    if entry is None:
        raise HTTPException(status_code=400, detail=f"unsupported billing event_type: {event_type}")
    return int(entry["points_per_unit"]) * units


def _provision_user_identity(conn, request: Request) -> tuple[RequestUser, UserAPIKey, UserCreditAccount]:
    user = _upsert_user(conn, request)
    user_api_key = _ensure_user_api_key(conn, user)
    credit_account = _ensure_user_credit_account_state(conn, user)
    return user, user_api_key, credit_account


def _fetch_session_for_user(conn, session_id: str, user_id: str) -> dict[str, Any]:
    rows = _run_pg_dict_query(
        conn,
        """
        SELECT session_id, user_id, title, target_platform, target_market, validation_marketplace,
               status, created_at, updated_at, closed_at
        FROM app.chat_session
        WHERE session_id = %s AND user_id = %s
        LIMIT 1
        """,
        [session_id, user_id],
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"chat session not found: {session_id}")
    return rows[0]


def _fetch_run_for_user(conn, run_id: str, user_id: str) -> dict[str, Any]:
    rows = _run_pg_dict_query(
        conn,
        """
        SELECT
            r.run_id,
            r.session_id,
            r.message_id,
            r.product_query,
            r.analysis_goal,
            r.input_payload_json,
            r.status,
            r.dify_run_id,
            r.final_answer_text,
            r.started_at,
            r.finished_at,
            r.created_at,
            r.updated_at
        FROM app.analysis_run r
        JOIN app.chat_session s ON r.session_id = s.session_id
        WHERE r.run_id = %s AND s.user_id = %s
        LIMIT 1
        """,
        [run_id, user_id],
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"analysis run not found: {run_id}")
    return rows[0]


def _require_active_session(session_row: dict[str, Any]) -> None:
    if session_row["status"] != "active":
        raise HTTPException(status_code=409, detail=f"chat session is not active: {session_row['session_id']}")


app = FastAPI(title="xiamimate Chat Backend", version="2026-04-13")


@app.on_event("startup")
def initialize_chat_backend() -> None:
    with _postgres_conn() as conn:
        _ensure_app_schema(conn)
        _seed_billing_packages(conn)
        _seed_billing_event_pricing(conn)
        _get_event_pricing(conn)


@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = "REQUEST_ERROR" if exc.status_code < 500 else "INTERNAL_ERROR"
    return JSONResponse(status_code=exc.status_code, content=_error_response(request.url.path, code, str(exc.detail)))


@app.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content=_error_response(request.url.path, "INTERNAL_ERROR", str(exc)))


@app.get("/health")
def health() -> dict[str, Any]:
    with _postgres_conn() as conn:
        _ensure_app_schema(conn)
        _seed_billing_packages(conn)
        _seed_billing_event_pricing(conn)
        _run_pg_dict_query(conn, "SELECT 1 AS ok")
    return _success_response(
        "/health",
        {
            "status": "ok",
            "online_store": {
                "type": "postgresql",
                "schema": "app",
                "host": os.environ.get("PG_HOST", "localhost"),
                "port": int(os.environ.get("PG_PORT", "5432")),
                "dbname": os.environ.get("PG_DB", "xiamimate"),
            },
            "user_headers": {
                "user_id": USER_ID_HEADER_NAME,
                "user_email": USER_EMAIL_HEADER_NAME,
                "user_name": USER_NAME_HEADER_NAME,
                "user_api_key": USER_API_KEY_HEADER_NAME,
                "default_user_id": DEFAULT_USER_ID,
                "demo_fallback_enabled": DEMO_FALLBACK_ENABLED,
            },
            "points_billing": {
                "pricing_version": POINTS_PRICE_VERSION,
                "point_cost_by_event": _get_point_cost_by_event(),
                "signup_gift_points": SIGNUP_GIFT_POINTS,
                "guest_daily_points": GUEST_DAILY_POINTS,
                "guest_daily_user_aliases": sorted(GUEST_DAILY_USER_ALIASES),
                "daily_reset_timezone": DAILY_RESET_TIMEZONE,
                "workflow_bundled_non_billable_event_types": sorted(WORKFLOW_BUNDLED_NON_BILLABLE_EVENT_TYPES),
            },
            "internal_security": {
                "service_secret_header": INTERNAL_SERVICE_SECRET_HEADER_NAME,
                "service_name_header": INTERNAL_SERVICE_NAME_HEADER_NAME,
                "idempotency_key_header": IDEMPOTENCY_KEY_HEADER_NAME,
                "service_secret_configured": bool(INTERNAL_SERVICE_SECRET),
                "admin_backoffice_configured": bool(ADMIN_BACKOFFICE_TOKEN),
                "internal_rate_limit_max_requests": INTERNAL_RATE_LIMIT_MAX_REQUESTS,
                "internal_rate_limit_window_seconds": INTERNAL_RATE_LIMIT_WINDOW_SECONDS,
            },
            "provider_dispatch": {
                "chat_backend_owns_upstream_keys": True,
                "dify_base_url": os.environ.get("DIFY_BASE_URL"),
                "theme_api_base_url": os.environ.get("XIAMIMATE_THEME_API_BASE_URL"),
                "agent_openai_base_url": os.environ.get("AGENT_OPENAI_BASE_URL"),
            },
        },
        "service is healthy",
    )


@app.post("/internal/identity/exchange-webui-user")
def internal_exchange_webui_user(request: Request, payload: IdentityExchangeRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    with _postgres_conn() as conn:
        user = _ensure_user_record(
            conn,
            user_id=payload.user_id,
            email=payload.email,
            display_name=payload.display_name,
        )
        user_api_key = _ensure_user_api_key(conn, user)
        credit_account = _ensure_user_credit_account_state(conn, user)
    return _success_response(
        "/internal/identity/exchange-webui-user",
        {
            "user": user.__dict__,
            "api_key": user_api_key.__dict__,
            "points_account": credit_account.__dict__,
            "pricing_version": POINTS_PRICE_VERSION,
            "point_cost_by_event": _get_point_cost_by_event(),
        },
        "webui user exchanged",
    )


@app.get("/v1/me")
def get_me(request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, user_api_key, credit_account = _provision_user_identity(conn, request)
    return _success_response(
        "/v1/me",
        {
            "user": user.__dict__,
            "api_key": _build_public_api_key_payload(user_api_key),
            "points_account": credit_account.__dict__,
            "pricing_version": POINTS_PRICE_VERSION,
            "point_cost_by_event": _get_point_cost_by_event(),
        },
        "current user loaded",
    )


@app.get("/v1/me/account-overview")
def get_my_account_overview(request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        overview = _build_user_account_overview(conn, user.user_id)
    return _success_response(
        "/v1/me/account-overview",
        overview,
        "account overview loaded",
    )


@app.get("/v1/me/usage")
def get_my_usage(request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        summary = _run_pg_dict_query(
            conn,
            """
            SELECT
                COALESCE(SUM(units) FILTER (WHERE created_at >= NOW() - INTERVAL '1 day'), 0) AS units_1d,
                COALESCE(SUM(units) FILTER (WHERE created_at >= NOW() - INTERVAL '7 day'), 0) AS units_7d,
                COALESCE(SUM(units) FILTER (WHERE created_at >= NOW() - INTERVAL '30 day'), 0) AS units_30d,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '30 day') AS event_count_30d
            FROM app.usage_event
            WHERE user_id = %s
            """,
            [user.user_id],
        )[0]
        by_type = _run_pg_dict_query(
            conn,
            """
            SELECT event_type, COALESCE(SUM(units), 0) AS total_units
            FROM app.usage_event
            WHERE user_id = %s
              AND created_at >= NOW() - INTERVAL '30 day'
            GROUP BY event_type
            ORDER BY total_units DESC, event_type ASC
            """,
            [user.user_id],
        )
    return _success_response(
        "/v1/me/usage",
        {
            "user_id": user.user_id,
            "usage": summary,
            "usage_by_type_30d": by_type,
        },
        "usage loaded",
    )


@app.get("/v1/me/plan")
def get_my_plan(request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
    return _success_response(
        "/v1/me/plan",
        {
            "user_id": user.user_id,
            "plan_tier": user.plan_tier,
            "entitlements": PLAN_LIMITS.get(user.plan_tier, {}),
        },
        "plan loaded",
    )


@app.get("/v1/me/api-key")
def get_my_api_key(request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, user_api_key, credit_account = _provision_user_identity(conn, request)
    return _success_response(
        "/v1/me/api-key",
        {
            "user_id": user.user_id,
            "api_key": _build_public_api_key_payload(user_api_key),
            "api_keys": [_build_public_api_key_payload(user_api_key)],
            "points_account": credit_account.__dict__,
            "pricing_version": POINTS_PRICE_VERSION,
            "point_cost_by_event": _get_point_cost_by_event(),
        },
        "user api key loaded",
    )


@app.get("/v1/me/points")
def get_my_points(request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, credit_account = _provision_user_identity(conn, request)
        ledger_rows = _run_pg_dict_query(
            conn,
            """
            SELECT entry_id, entry_type, event_type, units, points_delta, balance_after_points,
                   reference_id, description, meta_json, created_at
            FROM app.credit_ledger_entry
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 20
            """,
            [user.user_id],
        )
    return _success_response(
        "/v1/me/points",
        {
            "user_id": user.user_id,
            "points_account": credit_account.__dict__,
            "recent_ledger": ledger_rows,
            "pricing_version": POINTS_PRICE_VERSION,
            "point_cost_by_event": _get_point_cost_by_event(),
        },
        "points loaded",
    )


@app.get("/v1/billing/packages")
def list_billing_packages(request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        packages = _list_billing_packages(conn)
    return _success_response(
        "/v1/billing/packages",
        {
            "user_id": user.user_id,
            "packages": packages,
        },
        "billing packages loaded",
    )


@app.post("/v1/payments/orders")
def create_payment_order(request: Request, payload: CreatePaymentOrderRequest) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        package = _fetch_billing_package(conn, payload.package_code)
        order_id = _generate_id("order")
        order_row = _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.payment_order (
                order_id, user_id, package_code, product_type, provider, amount_cents,
                points_amount, status, callback_payload_json, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s, NOW(), NOW())
            RETURNING order_id, user_id, package_code, product_type, provider, amount_cents,
                      points_amount, status, provider_order_id, provider_trade_no,
                      callback_payload_json, paid_at, created_at, updated_at
            """,
            [
                order_id,
                user.user_id,
                package["package_code"],
                package["product_type"],
                payload.provider,
                package["price_cents"],
                package["points_amount"],
                psycopg2.extras.Json(
                    {
                        "package_name": package["package_name"],
                        "package_meta": package.get("meta_json") or {},
                        "created_via": "/v1/payments/orders",
                    }
                ),
            ],
        )[0]
    return _success_response(
        "/v1/payments/orders",
        {
            "order": order_row,
            "package": package,
        },
        "payment order created",
    )


@app.get("/v1/payments/orders/{order_id}")
def get_payment_order(order_id: str, request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        order_row = _fetch_payment_order_for_user(conn, order_id, user.user_id)
        package = _fetch_billing_package(conn, order_row["package_code"])
    return _success_response(
        f"/v1/payments/orders/{order_id}",
        {
            "order": order_row,
            "package": package,
        },
        "payment order loaded",
    )


@app.get("/v1/me/subscription")
def get_my_subscription(request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        subscriptions = _fetch_subscriptions_for_user(conn, user.user_id)
    return _success_response(
        "/v1/me/subscription",
        {
            "user_id": user.user_id,
            "subscriptions": subscriptions,
        },
        "subscription state loaded",
    )


@app.get("/admin/backoffice")
def admin_backoffice_page() -> HTMLResponse:
    return HTMLResponse(render_admin_backoffice_html())


# ---------------------------------------------------------------------------
# Portal – user self-service (token-based auth)
# ---------------------------------------------------------------------------

@app.get("/portal")
def portal_page() -> HTMLResponse:
    return HTMLResponse(render_portal_html())


@app.post("/internal/portal/create-token")
def create_portal_token(request: Request) -> dict[str, Any]:
    """Called by the pipeline to issue a short-lived portal token for a user."""
    _require_internal_service(request, "/internal/portal/create-token")
    user_id = (request.headers.get(USER_ID_HEADER_NAME) or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="missing X-User-Id header")
    with _postgres_conn() as conn:
        _fetch_user(conn, user_id)  # ensure user exists
    token = _generate_portal_token(user_id)
    portal_url = f"{_portal_base_url()}/portal?t={token}"
    return _success_response(
        "/internal/portal/create-token",
        {"token": token, "portal_url": portal_url, "ttl_seconds": PORTAL_TOKEN_TTL_SECONDS},
        "portal token created",
    )


def _require_portal_user(request: Request) -> str:
    """Validate portal token from Authorization header or query param, return user_id."""
    token = ""
    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        token = (request.query_params.get("t") or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing portal token")
    user_id = _verify_portal_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired portal token")
    return user_id


@app.get("/portal/api/account")
def portal_get_account(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        overview = _build_user_account_overview(conn, user_id, ledger_limit=50, usage_limit=50)
    return _success_response("/portal/api/account", overview, "account loaded")


@app.get("/portal/api/ledger")
def portal_get_ledger(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    page = max(1, int(request.query_params.get("page", "1")))
    page_size = min(100, max(1, int(request.query_params.get("page_size", "30"))))
    offset = (page - 1) * page_size
    with _postgres_conn() as conn:
        rows = _run_pg_dict_query(
            conn,
            """
            SELECT entry_id, entry_type, event_type, units, points_delta, balance_after_points,
                   description, created_at
            FROM app.credit_ledger_entry
            WHERE user_id = %s
            ORDER BY created_at DESC, entry_id DESC
            LIMIT %s OFFSET %s
            """,
            [user_id, page_size, offset],
        )
        total_row = _fetch_optional_one(
            conn,
            "SELECT COUNT(*) AS cnt FROM app.credit_ledger_entry WHERE user_id = %s",
            [user_id],
        )
    total = int((total_row or {}).get("cnt", 0))
    return _success_response(
        "/portal/api/ledger",
        {"rows": rows, "page": page, "page_size": page_size, "total": total},
        "ledger loaded",
    )


@app.get("/portal/api/usage-daily")
def portal_get_usage_daily(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    days = min(90, max(1, int(request.query_params.get("days", "30"))))
    with _postgres_conn() as conn:
        rows = _run_pg_dict_query(
            conn,
            """
            SELECT DATE(created_at AT TIME ZONE 'Asia/Shanghai') AS day,
                   event_type,
                   COUNT(*) AS event_count,
                   COALESCE(SUM(units), 0) AS total_units
            FROM app.usage_event
            WHERE user_id = %s
              AND created_at >= NOW() - make_interval(days => %s)
            GROUP BY day, event_type
            ORDER BY day DESC, event_type
            """,
            [user_id, days],
        )
    return _success_response("/portal/api/usage-daily", {"rows": rows, "days": days}, "daily usage loaded")


@app.get("/admin/api/overview")
def admin_backoffice_overview(request: Request) -> dict[str, Any]:
    _require_admin_operator(request)
    with _postgres_conn() as conn:
        overview = _build_admin_overview(conn)
    return _success_response(
        "/admin/api/overview",
        overview,
        "admin overview loaded",
    )


@app.get("/admin/api/users")
def admin_backoffice_users(request: Request) -> dict[str, Any]:
    _require_admin_operator(request)
    query = (request.query_params.get("query") or "").strip()
    raw_limit = (request.query_params.get("limit") or "20").strip()
    try:
        limit = max(1, min(int(raw_limit), 100))
    except ValueError:
        raise HTTPException(status_code=400, detail="limit must be an integer")

    with _postgres_conn() as conn:
        if query:
            like_query = f"%{query}%"
            rows = _run_pg_dict_query(
                conn,
                """
                SELECT u.user_id, u.email, u.display_name, u.status, u.plan_tier,
                       u.created_at, u.updated_at,
                       COALESCE(a.balance_points, 0) AS balance_points,
                       k.last_used_at AS api_key_last_used_at
                FROM app.app_user u
                LEFT JOIN app.user_credit_account a ON u.user_id = a.user_id
                LEFT JOIN app.user_api_key k ON u.user_id = k.user_id
                WHERE u.user_id ILIKE %s OR u.email ILIKE %s OR u.display_name ILIKE %s
                ORDER BY u.updated_at DESC, u.user_id DESC
                LIMIT %s
                """,
                [like_query, like_query, like_query, limit],
            )
        else:
            rows = _run_pg_dict_query(
                conn,
                """
                SELECT u.user_id, u.email, u.display_name, u.status, u.plan_tier,
                       u.created_at, u.updated_at,
                       COALESCE(a.balance_points, 0) AS balance_points,
                       k.last_used_at AS api_key_last_used_at
                FROM app.app_user u
                LEFT JOIN app.user_credit_account a ON u.user_id = a.user_id
                LEFT JOIN app.user_api_key k ON u.user_id = k.user_id
                ORDER BY u.updated_at DESC, u.user_id DESC
                LIMIT %s
                """,
                [limit],
            )
    return _success_response(
        "/admin/api/users",
        {"query": query, "users": rows},
        "admin users loaded",
    )


@app.get("/admin/api/users/{user_id}")
def admin_backoffice_user_detail(user_id: str, request: Request) -> dict[str, Any]:
    _require_admin_operator(request)
    with _postgres_conn() as conn:
        overview = _build_user_account_overview(
            conn,
            user_id,
            ledger_limit=50,
            usage_limit=50,
            order_limit=20,
            session_limit=20,
            run_limit=20,
        )
    return _success_response(
        f"/admin/api/users/{user_id}",
        overview,
        "admin user detail loaded",
    )


@app.post("/admin/api/users/{user_id}/grant-points")
def admin_backoffice_grant_points(user_id: str, request: Request, payload: AdminGrantPointsRequest) -> dict[str, Any]:
    operator_id = _require_admin_operator(request)
    with _postgres_conn() as conn:
        user = _ensure_user_record(conn, user_id=user_id)
        reference_id = payload.reference_id or f"admin:{operator_id}:{_generate_id('grant')}"
        updated_account, ledger_entry = _grant_points_with_ledger(
            conn=conn,
            user_id=user.user_id,
            points=payload.points,
            entry_type=payload.entry_type,
            event_type=payload.entry_type,
            reference_id=reference_id,
            description=payload.description or f"admin grant by {operator_id}",
            meta_json={
                **payload.meta,
                "operator_id": operator_id,
            },
            granted_points=payload.points,
        )
        audit_log = _audit_admin_action(
            conn,
            operator_id=operator_id,
            action="grant_points",
            target_type="user",
            target_id=user.user_id,
            request_json={
                "payload": jsonable_encoder(payload),
                "reference_id": reference_id,
            },
            result_json={
                "points_account": updated_account,
                "ledger_entry": ledger_entry,
            },
        )
    return _success_response(
        f"/admin/api/users/{user_id}/grant-points",
        {
            "points_account": updated_account,
            "ledger_entry": ledger_entry,
            "audit_log": audit_log,
        },
        "admin points granted",
    )


@app.get("/admin/api/audit-logs")
def admin_backoffice_audit_logs(request: Request) -> dict[str, Any]:
    _require_admin_operator(request)
    raw_limit = (request.query_params.get("limit") or "50").strip()
    try:
        limit = max(1, min(int(raw_limit), 200))
    except ValueError:
        raise HTTPException(status_code=400, detail="limit must be an integer")
    target_id = (request.query_params.get("target_id") or "").strip()

    with _postgres_conn() as conn:
        if target_id:
            rows = _run_pg_dict_query(
                conn,
                """
                SELECT audit_id, operator_id, action, target_type, target_id, request_json, result_json, created_at
                FROM app.admin_audit_log
                WHERE target_id = %s
                ORDER BY created_at DESC, audit_id DESC
                LIMIT %s
                """,
                [target_id, limit],
            )
        else:
            rows = _run_pg_dict_query(
                conn,
                """
                SELECT audit_id, operator_id, action, target_type, target_id, request_json, result_json, created_at
                FROM app.admin_audit_log
                ORDER BY created_at DESC, audit_id DESC
                LIMIT %s
                """,
                [limit],
            )
    return _success_response(
        "/admin/api/audit-logs",
        {"target_id": target_id or None, "audit_logs": rows},
        "admin audit logs loaded",
    )


class UpdateEventPricingRequest(BaseModel):
    display_name: str | None = None
    points_per_unit: int | None = None
    status: str | None = None
    display_order: int | None = None


@app.get("/admin/api/pricing")
def admin_list_event_pricing(request: Request) -> dict[str, Any]:
    _require_admin_operator(request)
    with _postgres_conn() as conn:
        rows = _run_pg_dict_query(
            conn,
            """
            SELECT event_type, display_name, points_per_unit, status, display_order, created_at, updated_at
            FROM app.billing_event_pricing
            ORDER BY display_order ASC, event_type ASC
            """,
        )
    return _success_response(
        "/admin/api/pricing",
        {"pricing_version": POINTS_PRICE_VERSION, "event_pricing": rows},
        "event pricing loaded",
    )


@app.put("/admin/api/pricing/{event_type}")
def admin_update_event_pricing(event_type: str, request: Request, payload: UpdateEventPricingRequest) -> dict[str, Any]:
    operator_id = _require_admin_operator(request)
    updates: list[str] = []
    params: list[Any] = []
    if payload.display_name is not None:
        updates.append("display_name = %s")
        params.append(payload.display_name)
    if payload.points_per_unit is not None:
        if payload.points_per_unit < 0:
            raise HTTPException(status_code=400, detail="points_per_unit must be >= 0")
        updates.append("points_per_unit = %s")
        params.append(payload.points_per_unit)
    if payload.status is not None:
        if payload.status not in {"active", "disabled"}:
            raise HTTPException(status_code=400, detail="status must be active or disabled")
        updates.append("status = %s")
        params.append(payload.status)
    if payload.display_order is not None:
        updates.append("display_order = %s")
        params.append(payload.display_order)
    if not updates:
        raise HTTPException(status_code=400, detail="no fields to update")

    updates.append("updated_at = NOW()")
    params.append(event_type)
    with _postgres_conn() as conn:
        rows = _run_pg_dict_query(
            conn,
            f"""
            UPDATE app.billing_event_pricing
            SET {', '.join(updates)}
            WHERE event_type = %s
            RETURNING event_type, display_name, points_per_unit, status, display_order, created_at, updated_at
            """,
            params,
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"event_type not found: {event_type}")
        _audit_admin_action(
            conn,
            operator_id=operator_id,
            action="update_event_pricing",
            target_type="billing_event_pricing",
            target_id=event_type,
            request_json=jsonable_encoder(payload),
            result_json=rows[0],
        )
    _invalidate_event_pricing_cache()
    return _success_response(
        f"/admin/api/pricing/{event_type}",
        {"event_pricing": rows[0]},
        "event pricing updated",
    )


@app.post("/v1/chat/sessions")
def create_chat_session(request: Request, payload: CreateSessionRequest) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        session_id = _generate_id("sess")
        session_row = _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.chat_session (
                session_id, user_id, title, target_platform, target_market,
                validation_marketplace, status, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, 'active', NOW(), NOW())
            RETURNING session_id, user_id, title, target_platform, target_market,
                      validation_marketplace, status, created_at, updated_at, closed_at
            """,
            [
                session_id,
                user.user_id,
                payload.title,
                payload.target_platform,
                payload.target_market,
                payload.validation_marketplace,
            ],
        )[0]
    return _success_response("/v1/chat/sessions", {"session": session_row}, "chat session created")


@app.get("/v1/chat/sessions/{session_id}")
def get_chat_session(session_id: str, request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        session_row = _fetch_session_for_user(conn, session_id, user.user_id)
        counts = _run_pg_dict_query(
            conn,
            """
            SELECT
                (SELECT COUNT(*) FROM app.chat_message WHERE session_id = %s) AS message_count,
                (SELECT COUNT(*) FROM app.analysis_run WHERE session_id = %s) AS run_count
            """,
            [session_id, session_id],
        )[0]
    session_row.update(counts)
    return _success_response(f"/v1/chat/sessions/{session_id}", {"session": session_row}, "chat session loaded")


@app.get("/v1/chat/sessions/{session_id}/messages")
def list_chat_messages(session_id: str, request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        _fetch_session_for_user(conn, session_id, user.user_id)
        rows = _run_pg_dict_query(
            conn,
            """
            SELECT message_id, session_id, role, content, message_type, metadata_json, created_at
            FROM app.chat_message
            WHERE session_id = %s
            ORDER BY created_at ASC, message_id ASC
            """,
            [session_id],
        )
    return _success_response(
        f"/v1/chat/sessions/{session_id}/messages",
        {"session_id": session_id, "messages": rows},
        "chat messages loaded",
    )


@app.post("/v1/chat/sessions/{session_id}/messages")
def create_chat_message(session_id: str, request: Request, payload: CreateMessageRequest) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        session_row = _fetch_session_for_user(conn, session_id, user.user_id)
        _require_active_session(session_row)
        message_id = _generate_id("msg")
        row = _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.chat_message (
                message_id, session_id, role, content, message_type, metadata_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
            RETURNING message_id, session_id, role, content, message_type, metadata_json, created_at
            """,
            [message_id, session_id, payload.role, payload.content, payload.message_type, psycopg2.extras.Json(payload.metadata)],
        )[0]
        _run_pg_dict_query(
            conn,
            "UPDATE app.chat_session SET updated_at = NOW() WHERE session_id = %s RETURNING session_id",
            [session_id],
        )
    return _success_response(
        f"/v1/chat/sessions/{session_id}/messages",
        {"message": row},
        "chat message created",
    )


@app.post("/v1/chat/sessions/{session_id}/close")
def close_chat_session(session_id: str, request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        _fetch_session_for_user(conn, session_id, user.user_id)
        row = _run_pg_dict_query(
            conn,
            """
            UPDATE app.chat_session
            SET status = 'closed', updated_at = NOW(), closed_at = COALESCE(closed_at, NOW())
            WHERE session_id = %s AND user_id = %s
            RETURNING session_id, user_id, title, target_platform, target_market,
                      validation_marketplace, status, created_at, updated_at, closed_at
            """,
            [session_id, user.user_id],
        )[0]
    return _success_response(
        f"/v1/chat/sessions/{session_id}/close",
        {"session": row},
        "chat session closed",
    )


@app.post("/v1/analysis/theme-runs")
def create_theme_run(request: Request, payload: CreateThemeRunRequest) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        session_row = _fetch_session_for_user(conn, payload.session_id, user.user_id)
        _require_active_session(session_row)
        if payload.message_id is not None:
            message_rows = _run_pg_dict_query(
                conn,
                "SELECT message_id FROM app.chat_message WHERE message_id = %s AND session_id = %s LIMIT 1",
                [payload.message_id, payload.session_id],
            )
            if not message_rows:
                raise HTTPException(status_code=404, detail=f"chat message not found: {payload.message_id}")

        run_id = _generate_id("run")
        run_row = _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.analysis_run (
                run_id, session_id, message_id, product_query, analysis_goal,
                input_payload_json, status, started_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, 'queued', NOW(), NOW(), NOW())
            RETURNING run_id, session_id, message_id, product_query, analysis_goal,
                      input_payload_json, status, dify_run_id, final_answer_text,
                      started_at, finished_at, created_at, updated_at
            """,
            [
                run_id,
                payload.session_id,
                payload.message_id,
                payload.product_query,
                payload.analysis_goal,
                psycopg2.extras.Json(payload.input_payload),
            ],
        )[0]
        _run_pg_dict_query(
            conn,
            "UPDATE app.chat_session SET updated_at = NOW() WHERE session_id = %s RETURNING session_id",
            [payload.session_id],
        )
    return _success_response("/v1/analysis/theme-runs", {"run": run_row}, "theme analysis run created")


@app.get("/v1/analysis/theme-runs/{run_id}")
def get_theme_run(run_id: str, request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        run_row = _fetch_run_for_user(conn, run_id, user.user_id)
        counts = _run_pg_dict_query(
            conn,
            "SELECT COUNT(*) AS artifact_count FROM app.analysis_artifact WHERE run_id = %s",
            [run_id],
        )[0]
    run_row.update(counts)
    return _success_response(f"/v1/analysis/theme-runs/{run_id}", {"run": run_row}, "theme analysis run loaded")


@app.get("/v1/analysis/theme-runs/{run_id}/artifacts")
def get_theme_run_artifacts(run_id: str, request: Request) -> dict[str, Any]:
    with _postgres_conn() as conn:
        user, _, _ = _provision_user_identity(conn, request)
        _fetch_run_for_user(conn, run_id, user.user_id)
        rows = _run_pg_dict_query(
            conn,
            """
            SELECT artifact_id, run_id, artifact_type, artifact_key, artifact_payload_json, created_at
            FROM app.analysis_artifact
            WHERE run_id = %s
            ORDER BY created_at ASC, artifact_id ASC
            """,
            [run_id],
        )
    return _success_response(
        f"/v1/analysis/theme-runs/{run_id}/artifacts",
        {"run_id": run_id, "artifacts": rows},
        "analysis artifacts loaded",
    )


@app.post("/internal/dify/run-callback")
def dify_run_callback(payload: DifyRunCallbackRequest) -> dict[str, Any]:
    with _postgres_conn() as conn:
        rows = _run_pg_dict_query(
            conn,
            """
            SELECT r.run_id, r.session_id, s.user_id
            FROM app.analysis_run r
            JOIN app.chat_session s ON r.session_id = s.session_id
            WHERE r.run_id = %s
            LIMIT 1
            """,
            [payload.run_id],
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"analysis run not found: {payload.run_id}")

        run_info = rows[0]
        finished_at = _utc_now() if payload.status in TERMINAL_RUN_STATUSES else None
        run_row = _run_pg_dict_query(
            conn,
            """
            UPDATE app.analysis_run
            SET status = %s,
                dify_run_id = COALESCE(%s, dify_run_id),
                final_answer_text = COALESCE(%s, final_answer_text),
                finished_at = COALESCE(%s, finished_at),
                updated_at = NOW()
            WHERE run_id = %s
            RETURNING run_id, session_id, message_id, product_query, analysis_goal,
                      input_payload_json, status, dify_run_id, final_answer_text,
                      started_at, finished_at, created_at, updated_at
            """,
            [payload.status, payload.dify_run_id, payload.final_answer_text, finished_at, payload.run_id],
        )[0]

        assistant_message_row = None
        if payload.assistant_message:
            assistant_message_row = _run_pg_dict_query(
                conn,
                """
                INSERT INTO app.chat_message (
                    message_id, session_id, role, content, message_type, metadata_json, created_at
                ) VALUES (%s, %s, 'assistant', %s, %s, %s, NOW())
                RETURNING message_id, session_id, role, content, message_type, metadata_json, created_at
                """,
                [
                    _generate_id("msg"),
                    run_info["session_id"],
                    payload.assistant_message,
                    payload.assistant_message_type,
                    psycopg2.extras.Json({"source": "dify_callback", "run_id": payload.run_id}),
                ],
            )[0]

        artifact_rows: list[dict[str, Any]] = []
        for artifact in payload.artifacts:
            artifact_rows.append(
                _run_pg_dict_query(
                    conn,
                    """
                    INSERT INTO app.analysis_artifact (
                        artifact_id, run_id, artifact_type, artifact_key, artifact_payload_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (run_id, artifact_key) DO UPDATE SET
                        artifact_type = EXCLUDED.artifact_type,
                        artifact_payload_json = EXCLUDED.artifact_payload_json
                    RETURNING artifact_id, run_id, artifact_type, artifact_key, artifact_payload_json, created_at
                    """,
                    [
                        _generate_id("artifact"),
                        payload.run_id,
                        artifact.artifact_type,
                        artifact.artifact_key,
                        psycopg2.extras.Json(artifact.artifact_payload),
                    ],
                )[0]
            )

        usage_rows: list[dict[str, Any]] = []
        for usage_event in payload.usage_events:
            usage_meta = dict(usage_event.meta or {})
            if usage_event.event_type in WORKFLOW_BUNDLED_NON_BILLABLE_EVENT_TYPES:
                usage_meta.update(
                    {
                        "billing_status": "audit_only",
                        "billing_reason": "bundled_into_dify_workflow_run",
                        "bundled_parent_event_type": "dify_workflow_run",
                    }
                )
            usage_rows.append(
                _record_usage_event(
                    conn,
                    user_id=run_info["user_id"],
                    session_id=run_info["session_id"],
                    run_id=payload.run_id,
                    event_type=usage_event.event_type,
                    units=usage_event.units,
                    meta_json=usage_meta,
                )
            )

        _run_pg_dict_query(
            conn,
            "UPDATE app.chat_session SET updated_at = NOW() WHERE session_id = %s RETURNING session_id",
            [run_info["session_id"]],
        )

    return _success_response(
        "/internal/dify/run-callback",
        {
            "run": run_row,
            "assistant_message": assistant_message_row,
            "artifacts": artifact_rows,
            "usage_events": usage_rows,
        },
        "dify callback processed",
    )


@app.post("/internal/admin/grant-points")
def admin_grant_points(request: Request, payload: GrantPointsRequest) -> dict[str, Any]:
    scope = request.url.path
    _require_internal_service(request, scope)
    idempotency_key = _require_idempotency_key(request)
    with _postgres_conn() as conn:
        cached_response = _begin_idempotent_request(conn, scope, idempotency_key, _build_request_hash(payload))
        if cached_response is not None:
            return cached_response
        user = _ensure_user_record(
            conn,
            user_id=payload.user_id,
            email=payload.user_email,
            display_name=payload.display_name,
            plan_tier=payload.plan_tier,
        )
        updated_account, ledger_entry = _grant_points_with_ledger(
            conn=conn,
            user_id=user.user_id,
            points=payload.points,
            entry_type=payload.entry_type,
            event_type=payload.entry_type,
            reference_id=payload.reference_id,
            description=payload.description,
            meta_json=payload.meta,
            granted_points=payload.points,
        )
        response_json = _success_response(
            "/internal/admin/grant-points",
            {"points_account": updated_account, "ledger_entry": ledger_entry},
            "points granted",
        )
        _complete_idempotent_request(conn, scope, idempotency_key, response_json)
    return response_json


@app.post("/internal/billing/charge-points")
def charge_points(request: Request, payload: ChargePointsRequest) -> dict[str, Any]:
    scope = request.url.path
    _require_internal_service(request, scope)
    idempotency_key = _require_idempotency_key(request)
    with _postgres_conn() as conn:
        cached_response = _begin_idempotent_request(conn, scope, idempotency_key, _build_request_hash(payload))
        if cached_response is not None:
            return cached_response
        api_key_row = _resolve_user_api_key(conn, payload.api_key)
        if api_key_row is None:
            raise HTTPException(status_code=401, detail="invalid user api key")
        if api_key_row["status"] != "active":
            raise HTTPException(status_code=403, detail="user api key inactive")

        user = _fetch_user(conn, api_key_row["user_id"])
        if _is_guest_daily_quota_user(user):
            _apply_guest_daily_quota_if_needed(conn, user)
        account = _get_credit_account(conn, api_key_row["user_id"], for_update=True)
        total_points = sum(_calculate_points_for_event(event.event_type, event.units) for event in payload.events)
        if int(account["balance_points"]) < total_points:
            raise HTTPException(status_code=402, detail="insufficient points")

        charges: list[dict[str, Any]] = []
        balance_after = int(account["balance_points"])
        for event in payload.events:
            charged_points = _calculate_points_for_event(event.event_type, event.units)
            balance_after -= charged_points
            updated_account = _run_pg_dict_query(
                conn,
                """
                UPDATE app.user_credit_account
                SET balance_points = %s,
                    lifetime_spent_points = lifetime_spent_points + %s,
                    updated_at = NOW()
                WHERE user_id = %s
                RETURNING user_id, balance_points, reserved_points, lifetime_granted_points,
                          lifetime_purchased_points, lifetime_spent_points, created_at, updated_at
                """,
                [balance_after, charged_points, api_key_row["user_id"]],
            )[0]
            usage_event = _record_usage_event(
                conn,
                user_id=api_key_row["user_id"],
                session_id=None,
                run_id=None,
                event_type=event.event_type,
                units=event.units,
                meta_json={
                    **event.meta,
                    "api_key_id": api_key_row["api_key_id"],
                    "points_price_version": POINTS_PRICE_VERSION,
                    "points_charged": charged_points,
                },
            )
            ledger_entry = _create_ledger_entry(
                conn=conn,
                user_id=api_key_row["user_id"],
                api_key_id=api_key_row["api_key_id"],
                entry_type="consume",
                event_type=event.event_type,
                units=event.units,
                points_delta=-charged_points,
                balance_after_points=balance_after,
                reference_id=event.reference_id,
                description=event.description,
                meta_json={
                    **event.meta,
                    "points_price_version": POINTS_PRICE_VERSION,
                    "points_charged": charged_points,
                },
            )
            charges.append(
                {
                    "event_type": event.event_type,
                    "units": event.units,
                    "points_charged": charged_points,
                    "usage_event": usage_event,
                    "ledger_entry": ledger_entry,
                    "points_account": updated_account,
                }
            )

        _touch_user_api_key(conn, api_key_row["api_key_id"])
        if _is_guest_daily_quota_user(user):
            _adjust_daily_credit_quota_consumed(conn, api_key_row["user_id"], total_points)

        response_json = _success_response(
            "/internal/billing/charge-points",
            {
                "user_id": api_key_row["user_id"],
                "api_key_id": api_key_row["api_key_id"],
                "pricing_version": POINTS_PRICE_VERSION,
                "charges": charges,
            },
            "points charged",
        )
        _complete_idempotent_request(conn, scope, idempotency_key, response_json)
    return response_json


@app.post("/internal/billing/refund-points")
def refund_points(request: Request, payload: RefundPointsRequest) -> dict[str, Any]:
    scope = request.url.path
    _require_internal_service(request, scope)
    idempotency_key = _require_idempotency_key(request)
    with _postgres_conn() as conn:
        cached_response = _begin_idempotent_request(conn, scope, idempotency_key, _build_request_hash(payload))
        if cached_response is not None:
            return cached_response
        api_key_row = _resolve_user_api_key(conn, payload.api_key)
        if api_key_row is None:
            raise HTTPException(status_code=401, detail="invalid user api key")

        user = _fetch_user(conn, api_key_row["user_id"])
        account = _get_credit_account(conn, api_key_row["user_id"], for_update=True)
        balance_after = int(account["balance_points"]) + payload.points
        updated_account = _run_pg_dict_query(
            conn,
            """
            UPDATE app.user_credit_account
            SET balance_points = %s,
                lifetime_spent_points = GREATEST(0, lifetime_spent_points - %s),
                updated_at = NOW()
            WHERE user_id = %s
            RETURNING user_id, balance_points, reserved_points, lifetime_granted_points,
                      lifetime_purchased_points, lifetime_spent_points, created_at, updated_at
            """,
            [balance_after, payload.points, api_key_row["user_id"]],
        )[0]
        ledger_entry = _create_ledger_entry(
            conn=conn,
            user_id=api_key_row["user_id"],
            api_key_id=api_key_row["api_key_id"],
            entry_type="refund",
            event_type=payload.event_type,
            units=payload.units,
            points_delta=payload.points,
            balance_after_points=balance_after,
            reference_id=payload.reference_id,
            description=payload.description,
            meta_json={
                **payload.meta,
                "points_price_version": POINTS_PRICE_VERSION,
                "points_refunded": payload.points,
            },
        )
        _touch_user_api_key(conn, api_key_row["api_key_id"])

        response_json = _success_response(
            "/internal/billing/refund-points",
            {
                "user_id": api_key_row["user_id"],
                "api_key_id": api_key_row["api_key_id"],
                "pricing_version": POINTS_PRICE_VERSION,
                "points_account": updated_account,
                "ledger_entry": ledger_entry,
            },
            "points refunded",
        )
        if _is_guest_daily_quota_user(user):
            _adjust_daily_credit_quota_consumed(conn, api_key_row["user_id"], -payload.points)
        _complete_idempotent_request(conn, scope, idempotency_key, response_json)
    return response_json


@app.post("/internal/provider/dify-workflow/run")
def internal_run_dify_workflow(request: Request, payload: InternalWorkflowRunRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    provider_response = _proxy_dify_workflow_blocking(query=payload.query, user=payload.user)
    return _success_response(
        "/internal/provider/dify-workflow/run",
        provider_response,
        "dify workflow proxied",
    )


@app.post("/internal/provider/dify-workflow/run-stream")
def internal_run_dify_workflow_stream(request: Request, payload: InternalWorkflowRunRequest) -> StreamingResponse:
    _require_internal_service(request, request.url.path)
    upstream_response = _proxy_dify_workflow_stream(query=payload.query, user=payload.user)

    def iterate_stream() -> Any:
        try:
            for chunk in upstream_response.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk
        finally:
            upstream_response.close()

    return StreamingResponse(
        iterate_stream(),
        media_type=upstream_response.headers.get("content-type") or "text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.post("/internal/provider/dify-dataset/retrieve")
def internal_retrieve_knowledge(request: Request, payload: InternalKnowledgeRetrieveRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    result = _proxy_knowledge_retrieve(query=payload.query, top_k=payload.top_k)
    return _success_response(
        "/internal/provider/dify-dataset/retrieve",
        {"result": result},
        "knowledge retrieval proxied",
    )


@app.post("/internal/provider/theme-api/{operation}")
def internal_call_theme_api(operation: str, request: Request, payload: InternalThemeAPICallRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    result = _proxy_theme_api(operation=operation, payload=payload.payload)
    return _success_response(
        f"/internal/provider/theme-api/{operation}",
        {"result": result},
        "theme api proxied",
    )


@app.post("/internal/provider/minimax/chat-completions")
def internal_minimax_chat_completion(request: Request, payload: InternalMinimaxRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    provider_response = _proxy_minimax_chat_completion(payload=payload.payload)
    return _success_response(
        "/internal/provider/minimax/chat-completions",
        provider_response,
        "minimax request proxied",
    )


@app.post("/internal/provider/minimax/chat-completions/stream")
def internal_minimax_chat_completion_stream(request: Request, payload: InternalMinimaxRequest) -> StreamingResponse:
    _require_internal_service(request, request.url.path)
    upstream_response = _proxy_minimax_chat_completion_stream(payload=payload.payload)

    def iterate_stream() -> Any:
        try:
            for chunk in upstream_response.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk
        finally:
            upstream_response.close()

    return StreamingResponse(
        iterate_stream(),
        media_type=upstream_response.headers.get("content-type") or "text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.post("/internal/payments/provider-callback/{provider}")
def internal_payment_provider_callback(provider: str, request: Request, payload: PaymentProviderCallbackRequest) -> dict[str, Any]:
    scope = request.url.path
    _require_internal_service(request, scope)
    idempotency_key = _require_idempotency_key(request)
    with _postgres_conn() as conn:
        cached_response = _begin_idempotent_request(conn, scope, idempotency_key, _build_request_hash(payload))
        if cached_response is not None:
            return cached_response

        order_row = _fetch_payment_order(conn, payload.order_id)
        if order_row["provider"] != provider:
            raise HTTPException(status_code=409, detail="payment provider does not match order provider")

        package = _fetch_billing_package(conn, order_row["package_code"])
        if payload.paid_amount_cents is not None and int(payload.paid_amount_cents) != int(order_row["amount_cents"]):
            raise HTTPException(status_code=400, detail="payment amount does not match order amount")

        if order_row["status"] == "paid":
            updated_account = _get_credit_account(conn, order_row["user_id"], for_update=False)
            subscription_row = None
            if order_row["product_type"] == "monthly_subscription":
                subscriptions = _run_pg_dict_query(
                    conn,
                    """
                    SELECT subscription_id, user_id, package_code, provider, provider_subscription_id,
                           status, monthly_points, current_period_start, current_period_end,
                           next_grant_at, last_grant_at, cancel_at_period_end, meta_json,
                           created_at, updated_at
                    FROM app.billing_subscription
                    WHERE user_id = %s AND package_code = %s
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT 1
                    """,
                    [order_row["user_id"], order_row["package_code"]],
                )
                subscription_row = subscriptions[0] if subscriptions else None
            response_json = _success_response(
                f"/internal/payments/provider-callback/{provider}",
                {
                    "order": order_row,
                    "package": package,
                    "points_account": updated_account,
                    "subscription": subscription_row,
                    "ledger_entry": None,
                    "subscription_grant": None,
                },
                "payment callback already applied",
            )
            _complete_idempotent_request(conn, scope, idempotency_key, response_json)
            return response_json

        updated_order = _run_pg_dict_query(
            conn,
            """
            UPDATE app.payment_order
            SET status = 'paid',
                provider_order_id = COALESCE(%s, provider_order_id),
                provider_trade_no = COALESCE(%s, provider_trade_no),
                callback_payload_json = %s,
                paid_at = COALESCE(paid_at, NOW()),
                updated_at = NOW()
            WHERE order_id = %s
            RETURNING order_id, user_id, package_code, product_type, provider, amount_cents,
                      points_amount, status, provider_order_id, provider_trade_no,
                      callback_payload_json, paid_at, created_at, updated_at
            """,
            [
                payload.provider_order_id,
                payload.provider_trade_no,
                psycopg2.extras.Json(payload.meta),
                payload.order_id,
            ],
        )[0]

        subscription_row = None
        subscription_grant_row = None
        if package["product_type"] == "credit_pack":
            updated_account, ledger_entry = _grant_points_with_ledger(
                conn=conn,
                user_id=updated_order["user_id"],
                points=int(package["points_amount"]),
                entry_type="recharge",
                event_type="recharge",
                reference_id=updated_order["order_id"],
                description="credit pack purchase",
                meta_json={
                    "provider": provider,
                    "package_code": package["package_code"],
                    "payment_order_id": updated_order["order_id"],
                    "provider_trade_no": payload.provider_trade_no,
                },
                purchased_points=int(package["points_amount"]),
            )
        else:
            period_start, period_end = _normalize_period_window(
                payload.period_start,
                payload.period_end,
                int(package["period_days"]),
            )
            existing_subscription = None
            if payload.provider_subscription_id:
                existing_subscription = _fetch_optional_one(
                    conn,
                    """
                    SELECT subscription_id, user_id, package_code, provider, provider_subscription_id,
                           status, monthly_points, current_period_start, current_period_end,
                           next_grant_at, last_grant_at, cancel_at_period_end, meta_json,
                           created_at, updated_at
                    FROM app.billing_subscription
                    WHERE provider = %s AND provider_subscription_id = %s
                    LIMIT 1
                    """,
                    [provider, payload.provider_subscription_id],
                )
            if existing_subscription is None:
                existing_subscription = _run_pg_dict_query(
                    conn,
                    """
                    INSERT INTO app.billing_subscription (
                        subscription_id, user_id, package_code, provider, provider_subscription_id,
                        status, monthly_points, current_period_start, current_period_end,
                        next_grant_at, last_grant_at, cancel_at_period_end, meta_json,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, 'active', %s, %s, %s, %s, NULL, FALSE, %s, NOW(), NOW())
                    RETURNING subscription_id, user_id, package_code, provider, provider_subscription_id,
                              status, monthly_points, current_period_start, current_period_end,
                              next_grant_at, last_grant_at, cancel_at_period_end, meta_json,
                              created_at, updated_at
                    """,
                    [
                        _generate_id("sub"),
                        updated_order["user_id"],
                        package["package_code"],
                        provider,
                        payload.provider_subscription_id,
                        int(package["points_amount"]),
                        period_start,
                        period_end,
                        period_end,
                        psycopg2.extras.Json(
                            {
                                "payment_order_id": updated_order["order_id"],
                                "provider_trade_no": payload.provider_trade_no,
                            }
                        ),
                    ],
                )[0]
            subscription_row, updated_account, subscription_grant_row, ledger_entry = _grant_subscription_period(
                conn=conn,
                subscription_row=existing_subscription,
                period_start=period_start,
                period_end=period_end,
                reference_id=payload.provider_trade_no or f"{existing_subscription['subscription_id']}:{period_start.isoformat()}:{period_end.isoformat()}",
                order_id=updated_order["order_id"],
                meta_json={
                    "provider": provider,
                    "package_code": package["package_code"],
                    "payment_order_id": updated_order["order_id"],
                    "provider_subscription_id": payload.provider_subscription_id,
                },
            )

        response_json = _success_response(
            f"/internal/payments/provider-callback/{provider}",
            {
                "order": updated_order,
                "package": package,
                "points_account": updated_account,
                "subscription": subscription_row,
                "ledger_entry": ledger_entry,
                "subscription_grant": subscription_grant_row,
            },
            "payment callback applied",
        )
        _complete_idempotent_request(conn, scope, idempotency_key, response_json)
    return response_json


@app.post("/internal/subscriptions/{subscription_id}/grant")
def internal_grant_subscription_points(
    subscription_id: str,
    request: Request,
    payload: GrantSubscriptionRequest,
) -> dict[str, Any]:
    scope = request.url.path
    _require_internal_service(request, scope)
    idempotency_key = _require_idempotency_key(request)
    with _postgres_conn() as conn:
        cached_response = _begin_idempotent_request(conn, scope, idempotency_key, _build_request_hash(payload))
        if cached_response is not None:
            return cached_response

        subscription_row = _fetch_subscription(conn, subscription_id)
        period_start, period_end = _normalize_period_window(
            payload.period_start,
            payload.period_end,
            max(1, int(subscription_row["monthly_points"])),
        )
        reference_id = payload.provider_trade_no or f"{subscription_id}:{period_start.isoformat()}:{period_end.isoformat()}"
        updated_subscription, updated_account, grant_row, ledger_entry = _grant_subscription_period(
            conn=conn,
            subscription_row=subscription_row,
            period_start=period_start,
            period_end=period_end,
            reference_id=reference_id,
            order_id=payload.order_id,
            meta_json={
                **payload.meta,
                "provider_trade_no": payload.provider_trade_no,
            },
        )
        response_json = _success_response(
            f"/internal/subscriptions/{subscription_id}/grant",
            {
                "subscription": updated_subscription,
                "points_account": updated_account,
                "subscription_grant": grant_row,
                "ledger_entry": ledger_entry,
            },
            "subscription points granted",
        )
        _complete_idempotent_request(conn, scope, idempotency_key, response_json)
    return response_json