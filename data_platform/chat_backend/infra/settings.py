"""Global settings, constants, and pure utility functions.

This module has NO dependency on any domain or infra sibling.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import smtplib
import string
from datetime import date, datetime, timezone
from email.utils import format_datetime, make_msgid
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from data_platform.llm_client import ROOT_ENV_FILE, load_env_file_if_present

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
INIT_APP_TABLES_SQL = PROJECT_ROOT / "postgres" / "init_app_tables.sql"

# Load .env before reading any env-backed settings constants.
load_env_file_if_present(ROOT_ENV_FILE)

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
TRUSTED_ADMIN_SESSION_HEADER_NAME = "X-OpenWebUI-Admin-Verified"

# ---------------------------------------------------------------------------
# Defaults from env
# ---------------------------------------------------------------------------
DEFAULT_USER_ID = os.environ.get("CHAT_BACKEND_DEFAULT_USER_ID", "demo-user")
DEFAULT_USER_EMAIL = os.environ.get("CHAT_BACKEND_DEFAULT_USER_EMAIL", "demo-user@local")
DEFAULT_USER_NAME = os.environ.get("CHAT_BACKEND_DEFAULT_USER_NAME", "Demo User")
DEFAULT_PLAN_TIER = os.environ.get("CHAT_BACKEND_DEFAULT_PLAN_TIER", "free")
SIGNUP_GIFT_POINTS = max(0, int(os.environ.get("CHAT_BACKEND_SIGNUP_GIFT_POINTS", "500")))
REFERRAL_INVITED_REWARD_POINTS = max(0, int(os.environ.get("CHAT_BACKEND_REFERRAL_INVITED_REWARD_POINTS", "500")))
USER_API_KEY_PREFIX = os.environ.get("CHAT_BACKEND_USER_API_KEY_PREFIX", "xia_user_")
USER_API_KEY_LENGTH = max(24, int(os.environ.get("CHAT_BACKEND_USER_API_KEY_LENGTH", "40")))
DEFAULT_PAYMENT_PROVIDER = os.environ.get("CHAT_BACKEND_PAYMENT_PROVIDER", "manual").strip() or "manual"
INTERNAL_SERVICE_SECRET = os.environ.get("CHAT_BACKEND_SERVICE_SECRET", "").strip()
ADMIN_BACKOFFICE_TOKEN = os.environ.get("CHAT_BACKEND_ADMIN_TOKEN", "").strip()
TRUSTED_ADMIN_SERVICE_NAME = os.environ.get("CHAT_BACKEND_TRUSTED_ADMIN_SERVICE_NAME", "openwebui-bridge-admin").strip() or "openwebui-bridge-admin"
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
SMTP_HOST = os.environ.get("CHAT_BACKEND_SMTP_HOST", "").strip()
SMTP_PORT = max(1, int(os.environ.get("CHAT_BACKEND_SMTP_PORT", "465")))
SMTP_USERNAME = os.environ.get("CHAT_BACKEND_SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.environ.get("CHAT_BACKEND_SMTP_PASSWORD", "").strip()
SMTP_FROM_EMAIL = os.environ.get("CHAT_BACKEND_SMTP_FROM_EMAIL", SMTP_USERNAME).strip()
SMTP_FROM_NAME = os.environ.get("CHAT_BACKEND_SMTP_FROM_NAME", "虾密小助手").strip() or "虾密小助手"
SMTP_USE_SSL = os.environ.get("CHAT_BACKEND_SMTP_USE_SSL", "true").strip().lower() not in {"0", "false", "no", "off"}
EMAIL_VERIFICATION_CODE_TTL_SECONDS = max(60, int(os.environ.get("CHAT_BACKEND_EMAIL_VERIFICATION_CODE_TTL", "600")))
EMAIL_VERIFICATION_RESEND_INTERVAL_SECONDS = max(30, int(os.environ.get("CHAT_BACKEND_EMAIL_VERIFICATION_RESEND_INTERVAL", "60")))
REFERRAL_INVITER_REWARD_POINTS = max(0, int(os.environ.get("CHAT_BACKEND_REFERRAL_INVITER_REWARD_POINTS", "500")))
PORTAL_REQUIRE_EMAIL_VERIFICATION = os.environ.get("CHAT_BACKEND_PORTAL_REQUIRE_EMAIL_VERIFICATION", "false").strip().lower() in {"1", "true", "yes", "on"}
PASSWORD_RESET_MIN_LENGTH = max(1, int(os.environ.get("CHAT_BACKEND_PASSWORD_RESET_MIN_LENGTH", "8")))
DEVICE_SESSION_COOKIE_NAME = os.environ.get("CHAT_BACKEND_DEVICE_SESSION_COOKIE_NAME", "xm_device_session").strip() or "xm_device_session"
DEVICE_SESSION_TTL_SECONDS = max(3600, int(os.environ.get("CHAT_BACKEND_DEVICE_SESSION_TTL_SECONDS", "2592000")))
DEVICE_SESSION_ELEVATION_TTL_SECONDS = max(300, int(os.environ.get("CHAT_BACKEND_DEVICE_SESSION_ELEVATION_TTL_SECONDS", "900")))

_default_openwebui_db_path = PROJECT_ROOT.parent / "xiamimate-openwebui-bridge" / "data" / "open-webui" / "webui.db"
OPENWEBUI_DB_PATH = os.environ.get("CHAT_BACKEND_OPENWEBUI_DB_PATH", "").strip() or (
    str(_default_openwebui_db_path) if _default_openwebui_db_path.exists() else ""
)

# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------
POINTS_PRICE_VERSION = "v5_report_routing_pricing"

ALLOWED_REPORT_PROFILES = {"quick", "standard", "deep", "research"}

REPORT_PROFILE_TO_BINDING: dict[str, str] = {
    "quick": "selection_report_quick",
    "standard": "selection_report_standard",
    "deep": "selection_report_deep",
    "research": "selection_report_research",
}

REPORT_PROFILE_TO_EVENT_TYPE: dict[str, str] = {
    "quick": "report_quick_run",
    "standard": "report_standard_run",
    "deep": "report_deep_run",
    "research": "report_research_run",
}

REPORT_PROFILE_TO_API_KEY_ENV_VAR: dict[str, str] = {
    "quick": "DIFY_REPORT_QUICK_APP_API_KEY",
    "standard": "DIFY_REPORT_STANDARD_APP_API_KEY",
    "deep": "DIFY_REPORT_DEEP_APP_API_KEY",
    "research": "DIFY_REPORT_RESEARCH_APP_API_KEY",
}

DEFAULT_EVENT_PRICING: list[dict[str, Any]] = [
    {"event_type": "llm_request",      "display_name": "LLM请求",      "points_per_unit": 1, "display_order": 10},
    {"event_type": "workflow_run",     "display_name": "历史Workflow请求", "points_per_unit": 8, "display_order": 20},
    {"event_type": "report_quick_run",    "display_name": "快速报告", "points_per_unit": 8,  "display_order": 21},
    {"event_type": "report_standard_run", "display_name": "标准报告", "points_per_unit": 16, "display_order": 22},
    {"event_type": "report_deep_run",     "display_name": "深度报告", "points_per_unit": 24, "display_order": 23},
    {"event_type": "report_research_run", "display_name": "研究报告", "points_per_unit": 32, "display_order": 24},
    {"event_type": "kb_retrieve",      "display_name": "知识库检索",    "points_per_unit": 2, "display_order": 30},
    {"event_type": "product_api_call", "display_name": "商品API检索",  "points_per_unit": 2, "display_order": 40},
    {"event_type": "web_search",       "display_name": "网络搜索",      "points_per_unit": 2, "display_order": 50},
]

# ---------------------------------------------------------------------------
# Portal tokens
# ---------------------------------------------------------------------------
PORTAL_TOKEN_TTL_SECONDS = int(os.environ.get("CHAT_BACKEND_PORTAL_TOKEN_TTL", "1800"))
LEGACY_PORTAL_BASE_URL = os.environ.get("CHAT_BACKEND_PORTAL_BASE_URL", "").strip()
PORTAL_PUBLIC_BASE_URL = (
    os.environ.get("CHAT_BACKEND_PUBLIC_PORTAL_BASE_URL", "").strip()
    or LEGACY_PORTAL_BASE_URL
)
PORTAL_INTERNAL_BASE_URL = (
    os.environ.get("CHAT_BACKEND_INTERNAL_PORTAL_BASE_URL", "").strip()
    or LEGACY_PORTAL_BASE_URL
)
PORTAL_USER_ID_HEADER_NAME = "X-Portal-User-Id"
PORTAL_USER_EMAIL_HEADER_NAME = "X-Portal-User-Email"
PORTAL_USER_NAME_HEADER_NAME = "X-Portal-User-Name"
_portal_mock_payment_env = os.environ.get("CHAT_BACKEND_PORTAL_MOCK_PAYMENT_ENABLED", "").strip().lower()
if _portal_mock_payment_env in {"1", "true", "yes", "on"}:
    PORTAL_MOCK_PAYMENT_ENABLED = True
elif _portal_mock_payment_env in {"0", "false", "no", "off"}:
    PORTAL_MOCK_PAYMENT_ENABLED = False
else:
    _portal_public_base_url_lower = PORTAL_PUBLIC_BASE_URL.lower()
    PORTAL_MOCK_PAYMENT_ENABLED = "127.0.0.1" in _portal_public_base_url_lower or "localhost" in _portal_public_base_url_lower


def _normalize_promotion_rule_status(value: Any, default: str = "active") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"active", "inactive"}:
        return normalized
    return default


def _parse_promotion_rule_status_overrides(raw_value: str) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for chunk in raw_value.split(","):
        item = chunk.strip()
        if not item:
            continue
        separator = "=" if "=" in item else (":" if ":" in item else "")
        if not separator:
            continue
        rule_code, status = item.split(separator, 1)
        normalized_rule_code = rule_code.strip()
        if not normalized_rule_code:
            continue
        overrides[normalized_rule_code] = _normalize_promotion_rule_status(status)
    return overrides


PROMOTION_RULE_STATUS_OVERRIDES = _parse_promotion_rule_status_overrides(
    os.environ.get("CHAT_BACKEND_PROMOTION_RULE_STATUS_OVERRIDES", "")
)


def _resolve_promotion_rule_seed_status(rule: dict[str, Any]) -> str:
    rule_code = str(rule.get("rule_code") or "").strip()
    override_status = PROMOTION_RULE_STATUS_OVERRIDES.get(rule_code)
    if override_status:
        return override_status
    return _normalize_promotion_rule_status(rule.get("status"), default="active")

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
    "category_resolve": "/api/product-theme/category-resolve",
    "expand_candidates": "/api/product-theme/expand-candidates",
    "candidate_expansion_status": "/api/product-theme/candidate-expansion-status",
    "opportunity_discovery": "/api/product-theme/opportunity-discovery",
    "opportunity_discovery_job": "/api/product-theme/opportunity-discovery-job",
    "candidate_pool_stats": "/api/product-theme/candidate-pool-stats",
    "candidate_pool_trends": "/api/product-theme/candidate-pool-trends",
    "candidate_pool_weak_forecast": "/api/product-theme/candidate-pool-weak-forecast",
    "product_forecast_explain": "/api/product-theme/product-forecast-explain",
    "launch_budget_calculator": "/api/product-theme/launch-budget-calculator",
    "top_asin_drilldown": "/api/product-theme/top-asin-drilldown",
    "asin_history_timeseries": "/api/product-theme/asin-history-timeseries",
    "category_benchmark": "/api/product-theme/category-benchmark",
    "keepa_asin_lookup": "/api/product-theme/keepa-asin-lookup",
}

DEFAULT_BILLING_PACKAGES: list[dict[str, Any]] = [
    {
        "package_code": "monthly_standard",
        "package_name": "Standard 标准版",
        "product_type": "monthly_subscription",
        "price_cents": 3900,
        "points_amount": 5000,
        "period_days": 30,
        "display_order": 10,
        "meta_json": {
            "zone_code": "monthly_zone",
            "tier_key": "standard",
            "display_price": "39 RMB / month",
            "display_points": "5000 points / month",
            "display_name": "Standard 标准版",
            "display_tagline": "适合轻量稳定使用",
            "renewal_price_cents": 3900,
            "renewal_price_label": "39元/月",
            "seed_catalog": "2026-04-launch",
        },
    },
    {
        "package_code": "monthly_pro",
        "package_name": "Pro 专业版",
        "product_type": "monthly_subscription",
        "price_cents": 9900,
        "points_amount": 16000,
        "period_days": 30,
        "display_order": 20,
        "meta_json": {
            "zone_code": "monthly_zone",
            "tier_key": "pro",
            "display_price": "99 RMB / month",
            "display_points": "16000 points / month",
            "display_name": "Pro 专业版",
            "display_tagline": "适合高频日常使用",
            "renewal_price_cents": 9900,
            "renewal_price_label": "99元/月",
            "seed_catalog": "2026-04-launch",
        },
    },
    {
        "package_code": "monthly_ultra",
        "package_name": "Ultra 旗舰版",
        "product_type": "monthly_subscription",
        "price_cents": 29900,
        "points_amount": 60000,
        "period_days": 30,
        "display_order": 30,
        "meta_json": {
            "zone_code": "monthly_zone",
            "tier_key": "ultra",
            "display_price": "299 RMB / month",
            "display_points": "60000 points / month",
            "display_name": "Ultra 旗舰版",
            "display_tagline": "适合团队与重度使用",
            "renewal_price_cents": 29900,
            "renewal_price_label": "299元/月",
            "seed_catalog": "2026-04-launch",
        },
    },
    {
        "package_code": "recharge_1000",
        "package_name": "充值包 1000",
        "product_type": "credit_pack",
        "price_cents": 1000,
        "points_amount": 1000,
        "period_days": 0,
        "display_order": 110,
        "meta_json": {
            "zone_code": "recharge_zone",
            "display_price": "10 RMB",
            "display_points": "1000 points",
            "display_name": "充值包 1000",
            "display_tagline": "100 积分 = 1 元",
            "seed_catalog": "2026-04-launch",
        },
    },
    {
        "package_code": "recharge_3000",
        "package_name": "充值包 3000",
        "product_type": "credit_pack",
        "price_cents": 3000,
        "points_amount": 3000,
        "period_days": 0,
        "display_order": 120,
        "meta_json": {
            "zone_code": "recharge_zone",
            "display_price": "30 RMB",
            "display_points": "3000 points",
            "display_name": "充值包 3000",
            "display_tagline": "100 积分 = 1 元",
            "seed_catalog": "2026-04-launch",
        },
    },
    {
        "package_code": "recharge_10000",
        "package_name": "充值包 10000",
        "product_type": "credit_pack",
        "price_cents": 10000,
        "points_amount": 10000,
        "period_days": 0,
        "display_order": 130,
        "meta_json": {
            "zone_code": "recharge_zone",
            "display_price": "100 RMB",
            "display_points": "10000 points",
            "display_name": "充值包 10000",
            "display_tagline": "100 积分 = 1 元",
            "seed_catalog": "2026-04-launch",
        },
    },
    {
        "package_code": "recharge_50000",
        "package_name": "充值包 50000",
        "product_type": "credit_pack",
        "price_cents": 50000,
        "points_amount": 50000,
        "period_days": 0,
        "display_order": 140,
        "meta_json": {
            "zone_code": "recharge_zone",
            "display_price": "500 RMB",
            "display_points": "50000 points",
            "display_name": "充值包 50000",
            "display_tagline": "100 积分 = 1 元",
            "seed_catalog": "2026-04-launch",
        },
    },
]

DEFAULT_PROMOTION_RULES: list[dict[str, Any]] = [
    {
        "rule_code": "signup_bonus_500",
        "rule_name": "新用户邮箱验证成功赠送 500 积分",
        "rule_type": "signup_reward",
        "target_product_type": None,
        "target_package_codes": [],
        "benefit_type": "points_bonus",
        "benefit_value": 500,
        "criteria_json": {"claim_once_per_user": True},
        "meta_json": {
            "zone_code": "newcomer_zone",
            "display_text": "邮箱验证成功后赠送 500 积分",
            "seed_catalog": "2026-04-launch",
        },
        "display_order": 10,
    },
    {
        "rule_code": "referral_invited_bind_bonus_500",
        "rule_name": "新用户绑定邀请码额外赠送 500 积分",
        "rule_type": "referral_invited_reward",
        "target_product_type": None,
        "target_package_codes": [],
        "benefit_type": "points_bonus",
        "benefit_value": REFERRAL_INVITED_REWARD_POINTS,
        "criteria_json": {"claim_once_per_user": True},
        "meta_json": {
            "zone_code": "newcomer_zone",
            "display_text": "新用户绑定邀请码，新老用户均额外赠送500积分",
            "seed_catalog": "2026-04-launch",
        },
        "display_order": 12,
    },
    {
        "rule_code": "referral_inviter_bonus_500",
        "rule_name": "邀请新用户注册成功赠送 500 积分",
        "rule_type": "referral_inviter_reward",
        "target_product_type": None,
        "target_package_codes": [],
        "benefit_type": "points_bonus",
        "benefit_value": REFERRAL_INVITER_REWARD_POINTS,
        "criteria_json": {"claim_once_per_invited_user": True},
        "meta_json": {
            "zone_code": "newcomer_zone",
            "display_text": "被邀请新用户完成邮箱验证后，邀请人赠送 500 积分",
            "seed_catalog": "2026-04-launch",
        },
        "display_order": 15,
    },
    {
        "rule_code": "first_subscription_monthly_90_off",
        "rule_name": "首次订阅月包首月 1 折",
        "status": "inactive",
        "rule_type": "first_subscription_discount",
        "target_product_type": "monthly_subscription",
        "target_package_codes": ["monthly_standard", "monthly_pro", "monthly_ultra"],
        "benefit_type": "discount_basis_points",
        "benefit_value": 9000,
        "criteria_json": {"claim_once_per_user": True},
        "meta_json": {
            "zone_code": "newcomer_zone",
            "display_text": "首次订阅月包，首月享 1 折优惠",
            "seed_catalog": "2026-04-launch",
        },
        "display_order": 20,
    },
    {
        "rule_code": "recharge_single_bonus_1000",
        "rule_name": "充值包 1000 单笔赠送",
        "rule_type": "recharge_bonus_single",
        "target_product_type": "credit_pack",
        "target_package_codes": ["recharge_1000"],
        "benefit_type": "points_bonus",
        "benefit_value": 100,
        "criteria_json": {},
        "meta_json": {
            "zone_code": "recharge_zone",
            "display_text": "充 10 元送 100 积分",
            "seed_catalog": "2026-04-launch",
        },
        "display_order": 110,
    },
    {
        "rule_code": "recharge_single_bonus_3000",
        "rule_name": "充值包 3000 单笔赠送",
        "rule_type": "recharge_bonus_single",
        "target_product_type": "credit_pack",
        "target_package_codes": ["recharge_3000"],
        "benefit_type": "points_bonus",
        "benefit_value": 600,
        "criteria_json": {},
        "meta_json": {
            "zone_code": "recharge_zone",
            "display_text": "充 30 元送 600 积分",
            "seed_catalog": "2026-04-launch",
        },
        "display_order": 120,
    },
    {
        "rule_code": "recharge_single_bonus_10000",
        "rule_name": "充值包 10000 单笔赠送",
        "rule_type": "recharge_bonus_single",
        "target_product_type": "credit_pack",
        "target_package_codes": ["recharge_10000"],
        "benefit_type": "points_bonus",
        "benefit_value": 3000,
        "criteria_json": {},
        "meta_json": {
            "zone_code": "recharge_zone",
            "display_text": "充 100 元送 3000 积分",
            "seed_catalog": "2026-04-launch",
        },
        "display_order": 130,
    },
    {
        "rule_code": "recharge_single_bonus_50000",
        "rule_name": "充值包 50000 单笔赠送",
        "rule_type": "recharge_bonus_single",
        "target_product_type": "credit_pack",
        "target_package_codes": ["recharge_50000"],
        "benefit_type": "points_bonus",
        "benefit_value": 20000,
        "criteria_json": {},
        "meta_json": {
            "zone_code": "recharge_zone",
            "display_text": "充 500 元送 20000 积分",
            "seed_catalog": "2026-04-launch",
        },
        "display_order": 140,
    },
    {
        "rule_code": "recharge_cumulative_bonus_100",
        "rule_name": "累计充值满 100 元赠送",
        "rule_type": "recharge_bonus_cumulative",
        "target_product_type": "credit_pack",
        "target_package_codes": [],
        "benefit_type": "points_bonus",
        "benefit_value": 1000,
        "criteria_json": {"threshold_paid_amount_cents": 10000},
        "meta_json": {
            "zone_code": "recharge_zone",
            "display_text": "累计充值满 100 元，额外送 1000 积分",
            "seed_catalog": "2026-04-launch",
        },
        "display_order": 210,
    },
    {
        "rule_code": "recharge_cumulative_bonus_500",
        "rule_name": "累计充值满 500 元赠送",
        "rule_type": "recharge_bonus_cumulative",
        "target_product_type": "credit_pack",
        "target_package_codes": [],
        "benefit_type": "points_bonus",
        "benefit_value": 8000,
        "criteria_json": {"threshold_paid_amount_cents": 50000},
        "meta_json": {
            "zone_code": "recharge_zone",
            "display_text": "累计充值满 500 元，额外送 8000 积分",
            "seed_catalog": "2026-04-launch",
        },
        "display_order": 220,
    },
    {
        "rule_code": "recharge_cumulative_bonus_1000",
        "rule_name": "累计充值满 1000 元赠送",
        "rule_type": "recharge_bonus_cumulative",
        "target_product_type": "credit_pack",
        "target_package_codes": [],
        "benefit_type": "points_bonus",
        "benefit_value": 20000,
        "criteria_json": {"threshold_paid_amount_cents": 100000},
        "meta_json": {
            "zone_code": "recharge_zone",
            "display_text": "累计充值满 1000 元，额外送 20000 积分",
            "seed_catalog": "2026-04-launch",
        },
        "display_order": 230,
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
    "ultra": {"daily_theme_runs": 5000, "history_retention_days": 3650},
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
# Pure utility functions
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def _generate_invite_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(max(6, length)))


def _generate_numeric_code(length: int = 6) -> str:
    alphabet = string.digits
    return "".join(secrets.choice(alphabet) for _ in range(max(4, length)))


def _build_api_key(prefix: str = USER_API_KEY_PREFIX, length: int = USER_API_KEY_LENGTH) -> str:
    alphabet = string.ascii_letters + string.digits
    token = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{prefix}{token}"


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_FROM_EMAIL)


def _portal_email_verification_gate_enabled() -> bool:
    return PORTAL_REQUIRE_EMAIL_VERIFICATION and _smtp_configured()


def _send_email_message(to_email: str, subject: str, text_body: str) -> None:
    if not _smtp_configured():
        raise RuntimeError("CHAT_BACKEND_SMTP_HOST / CHAT_BACKEND_SMTP_FROM_EMAIL 未配置，无法发送邮箱验证码")

    from_email = SMTP_FROM_EMAIL.strip()
    message_id_domain = ""
    if "@" in from_email:
        message_id_domain = from_email.rsplit("@", 1)[-1].strip()

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{SMTP_FROM_NAME} <{from_email}>"
    message["To"] = to_email
    message["Date"] = format_datetime(datetime.now(timezone.utc))
    message["Message-ID"] = make_msgid(domain=message_id_domain or None)
    message.set_content(text_body)

    if SMTP_USE_SSL:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            if SMTP_USERNAME:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(message)
        return

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
        smtp.starttls()
        if SMTP_USERNAME:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        smtp.send_message(message)


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
