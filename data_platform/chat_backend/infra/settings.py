"""Global settings, constants, and pure utility functions.

This module has NO dependency on any domain or infra sibling.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import string
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from data_platform.llm_client import ROOT_ENV_FILE, load_env_file_if_present

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
INIT_APP_TABLES_SQL = PROJECT_ROOT / "postgres" / "init_app_tables.sql"

# ---------------------------------------------------------------------------
# API response schema
# ---------------------------------------------------------------------------
API_RESPONSE_SCHEMA = "xiamimate_chat_backend_v1"

# ---------------------------------------------------------------------------
# Header names
# ---------------------------------------------------------------------------
USER_ID_HEADER_NAME = "X-User-Id"
USER_EMAIL_HEADER_NAME = "X-User-Email"
USER_NAME_HEADER_NAME = "X-User-Name"
USER_API_KEY_HEADER_NAME = "X-Xia-User-Key"
INTERNAL_SERVICE_SECRET_HEADER_NAME = "X-Internal-Service-Secret"
INTERNAL_SERVICE_NAME_HEADER_NAME = "X-Internal-Service-Name"
IDEMPOTENCY_KEY_HEADER_NAME = "Idempotency-Key"
ADMIN_OPERATOR_HEADER_NAME = "X-Admin-Operator"

# ---------------------------------------------------------------------------
# Defaults from env
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------
POINTS_PRICE_VERSION = "v2_db_pricing"

DEFAULT_EVENT_PRICING: list[dict[str, Any]] = [
    {"event_type": "llm_request",      "display_name": "LLM请求",      "points_per_unit": 1, "display_order": 10},
    {"event_type": "workflow_run",     "display_name": "workflow请求", "points_per_unit": 8, "display_order": 20},
    {"event_type": "kb_retrieve",      "display_name": "知识库检索",    "points_per_unit": 1, "display_order": 30},
    {"event_type": "product_api_call", "display_name": "商品API检索",  "points_per_unit": 1, "display_order": 40},
    {"event_type": "web_search",       "display_name": "网络搜索",      "points_per_unit": 1, "display_order": 50},
]

# ---------------------------------------------------------------------------
# Portal tokens
# ---------------------------------------------------------------------------
PORTAL_TOKEN_TTL_SECONDS = int(os.environ.get("CHAT_BACKEND_PORTAL_TOKEN_TTL", "1800"))
PORTAL_BASE_URL = os.environ.get("CHAT_BACKEND_PORTAL_BASE_URL", "").strip()

# ---------------------------------------------------------------------------
# Billing bundles & packages
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Plan limits
# ---------------------------------------------------------------------------
PLAN_LIMITS: dict[str, dict[str, Any]] = {
    "free": {"daily_theme_runs": 10, "history_retention_days": 7},
    "guest": {"daily_theme_runs": 20, "history_retention_days": 7, "daily_points": GUEST_DAILY_POINTS},
    "standard": {"daily_theme_runs": 100, "history_retention_days": 30},
    "pro": {"daily_theme_runs": 1000, "history_retention_days": 365},
    "admin": {"daily_theme_runs": None, "history_retention_days": None},
}

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------
TERMINAL_RUN_STATUSES = {"completed", "failed", "canceled"}
ALLOWED_RUN_STATUSES = {"queued", "running", "completed", "failed", "canceled"}
ALLOWED_SESSION_STATUSES = {"active", "closed", "archived"}
ALLOWED_MESSAGE_ROLES = {"user", "assistant", "system"}

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------
load_env_file_if_present(ROOT_ENV_FILE)


# ---------------------------------------------------------------------------
# Pure utility functions
# ---------------------------------------------------------------------------

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


def _reset_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(DAILY_RESET_TIMEZONE)
    except Exception:
        return ZoneInfo("UTC")


def _current_quota_date() -> date:
    return datetime.now(_reset_timezone()).date()
