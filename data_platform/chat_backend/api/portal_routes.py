"""Portal API routes — /portal/*."""
from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from typing import Any

import requests as http_requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

try:
    import psycopg2.extras
except ImportError:
    pass

from data_platform.chat_backend.infra.postgres import (
    _fetch_optional_one,
    _postgres_conn,
    _run_pg_dict_query,
)
from data_platform.chat_backend.infra.http import _success_response
from data_platform.chat_backend.infra.settings import (
    DEVICE_SESSION_ELEVATION_TTL_SECONDS,
    IDEMPOTENCY_KEY_HEADER_NAME,
    INTERNAL_SERVICE_NAME_HEADER_NAME,
    INTERNAL_SERVICE_SECRET,
    INTERNAL_SERVICE_SECRET_HEADER_NAME,
    PORTAL_MOCK_PAYMENT_ENABLED,
    WECHAT_NATIVE_QR_TTL_SECONDS,
    _portal_email_verification_gate_enabled,
    _generate_id,
    _utc_now,
)
from data_platform.chat_backend.domains.portal.service import (
    _backend_base_url,
    _portal_internal_base_url,
    _portal_public_base_url,
    _require_portal_user,
)
from data_platform.chat_backend.domains.admin.service import _build_user_account_overview
from data_platform.chat_backend.domains.tools.service import (
    ToolInputError,
    check_compliance,
    clean_and_expand_keywords,
    compute_acos_breakeven,
    compute_dimensional_weight,
    compute_landed_price,
    compute_pricing_reverse,
    compute_profit_calculator,
    diagnose_title,
    extract_competitor_gaps,
    generate_aplus_outline,
    generate_description,
    generate_service_reply,
    mine_reviews,
    score_listing_health,
)
from data_platform.chat_backend.domains.billing.service import (
    _build_billing_catalog,
    _build_payment_order_snapshot,
    _ensure_user_credit_account_state,
    _fetch_billing_package,
    _fetch_subscriptions_for_user,
    _grant_referral_invited_reward_if_needed,
    _redeem_code,
    _resolve_referral_invited_reward_points,
    _resolve_signup_gift_points,
)
from data_platform.chat_backend.domains.identity.service import (
    _auto_request_email_verification_if_needed,
    _bind_user_referral,
    _confirm_email_verification,
    _confirm_email_verification_link as _confirm_email_verification_link_token,
    _confirm_password_reset,
    _confirm_security_verification,
    _ensure_user_record,
    _fetch_user_by_invite_code,
    _fetch_user,
    _request_password_reset,
    _request_email_verification,
    _request_security_verification,
)
from data_platform.chat_backend.domains.device_sessions.service import (
    _bootstrap_device_session,
    _clear_device_session_cookie,
    _current_device_session_or_raise,
    _evaluate_device_session_request,
    _elevate_device_session,
    _require_elevated_device_session,
    _revoke_device_session,
    _revoke_other_device_sessions,
    _serialize_device_session,
    _set_device_session_cookie,
)
from data_platform.chat_backend.domains.notifications.service import (
    _list_notifications_for_user,
    _set_notification_read_state,
)
from data_platform.chat_backend.domains.payments.service import _fetch_payment_order_for_user
from data_platform.chat_backend.domains.payments.service import (
    _create_payment_session,
    _fetch_latest_payment_session,
    _fetch_payment_session,
    _update_payment_session_status,
)
from data_platform.chat_backend.domains.payments.wechat_pay import (
    close_wechat_order_by_out_trade_no,
    create_wechat_native_prepay,
    extract_wechat_trade_payload,
    query_wechat_order_by_out_trade_no,
    wechat_trade_state_to_session_status,
)
from data_platform.chat_backend.domains.provider_proxy.service import _proxy_report_blocking, _proxy_theme_api
from data_platform.chat_backend.domains.site_config import (
    _get_contact_config,
    _get_email_verification_security_config,
)

from data_platform.chat_backend.api.models import (
    AdminCreateRedeemCodeBatchRequest,
    BindReferralCodeRequest,
    ConfirmPasswordResetRequest,
    ConfirmEmailVerificationRequest,
    ConfirmSecurityVerificationRequest,
    CreatePaymentOrderRequest,
    CreatePaymentSessionRequest,
    RedeemCodeRedeemRequest,
    RequestPasswordResetRequest,
    UpdateNotificationReadStateRequest,
)
from data_platform.api.chat_backend_portal_html import render_portal_html
from data_platform.api.chat_backend_portal_public_html import (
    render_llms_txt,
    render_portal_checkout_html,
    render_portal_product_html,
    render_portal_guide_html,
    render_portal_tools_html,
    render_portal_email_verification_result_html,
    render_portal_invite_html,
    render_portal_password_reset_html,
    render_portal_products_html,
    render_robots_txt,
    render_sitemap_xml,
)

router = APIRouter()
_WECHAT_QR_IMAGE_PATH = Path(__file__).resolve().parents[3] / "微信二维码.jpg"
_WECHAT_PAY_LOGO_PATH = Path(__file__).resolve().parents[3] / "data_platform" / "api" / "assets" / "wechat-pay-logo.svg"


_PORTAL_PROVIDER_LABELS = {
    "alipay": "支付宝",
    "wechat": "微信支付",
    "manual": "线下/手工",
}

_PORTAL_LEDGER_SOURCE_LABELS = {
    "subscription": "月包积分",
    "recharge": "充值包积分",
    "other": "其他赠送积分",
}

_PORTAL_LEDGER_FILTER_CLAUSES = {
    "consume": " AND entry_type = 'consume'",
    "refund": " AND entry_type = 'refund'",
    "credit": " AND points_delta > 0 AND entry_type NOT IN ('refund', 'daily_quota_reset')",
    "daily_reset": " AND entry_type = 'daily_quota_reset'",
}

_EMAIL_VERIFICATION_IP_GUARD_LOCK = threading.Lock()
_EMAIL_VERIFICATION_IP_GUARD_BUCKETS: dict[str, deque[float]] = defaultdict(deque)

_PUBLIC_QUICK_TRIAL_COOKIE_NAME = "xm_quick_trial_device"
_PUBLIC_QUICK_TRIAL_LIMIT = 10
_PUBLIC_QUICK_TRIAL_IP_ABUSE_LIMIT = 200
_PUBLIC_QUICK_TRIAL_LOCK = threading.Lock()
_PUBLIC_QUICK_TRIAL_USED_COUNTS: dict[str, int] = defaultdict(int)
_PUBLIC_QUICK_TRIAL_IN_FLIGHT_COUNTS: dict[str, int] = defaultdict(int)


def _public_page_is_indexable(request: Request) -> bool:
    return len(request.query_params) == 0


def _public_page_cache_headers(request: Request) -> dict[str, str]:
    if _public_page_is_indexable(request):
        return {"Cache-Control": "public, max-age=300"}
    return {"Cache-Control": "no-store"}


def _mask_email_for_display(email: str) -> str:
    normalized = str(email or "").strip()
    if "@" not in normalized:
        return normalized or "-"
    local, domain = normalized.split("@", 1)
    if len(local) <= 2:
        masked_local = local[:1] + "*"
    else:
        masked_local = local[:2] + "***"
    return f"{masked_local}@{domain}"


def _normalize_portal_ledger_source(source: Any) -> str:
    normalized = str(source or "").strip().lower()
    if normalized in _PORTAL_LEDGER_SOURCE_LABELS:
        return normalized
    return "other"


def _summarize_portal_ledger_sources(row: dict[str, Any]) -> list[dict[str, Any]]:
    meta_json = dict(row.get("meta_json") or {})
    entry_type = str(row.get("entry_type") or "").strip().lower()
    allocations = list(meta_json.get("balance_source_allocations") or [])
    if entry_type == "refund" and not allocations:
        allocations = list(meta_json.get("refund_allocations") or [])
    totals: dict[str, int] = {}
    for allocation in allocations:
        source = _normalize_portal_ledger_source((allocation or {}).get("source"))
        points = max(0, int((allocation or {}).get("points") or 0))
        if points <= 0:
            continue
        totals[source] = totals.get(source, 0) + points

    if not totals and entry_type == "subscription_expire":
        expired_points = max(0, int(meta_json.get("expired_points") or abs(int(row.get("points_delta") or 0))))
        if expired_points > 0:
            totals["subscription"] = expired_points

    ordered_sources = ("subscription", "recharge", "other")
    return [
        {
            "source": source,
            "label": _PORTAL_LEDGER_SOURCE_LABELS[source],
            "points": totals[source],
        }
        for source in ordered_sources
        if totals.get(source, 0) > 0
    ]


def _build_portal_ledger_row(row: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(row)
    source_summary = _summarize_portal_ledger_sources(enriched)
    enriched["source_summary"] = source_summary
    enriched["source_summary_text"] = "；".join(
        f"{item['label']} {int(item.get('points') or 0)} 积分"
        for item in source_summary
    )
    return enriched


def _extract_openwebui_access_token(request: Request) -> str:
    auth_header = (request.headers.get("authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return str(request.cookies.get("token") or "").strip()


def _resolve_openwebui_session_user(request: Request) -> tuple[str, str, str] | None:
    token_value = _extract_openwebui_access_token(request)
    if not token_value:
        return None

    owui_base = _portal_internal_base_url()
    try:
        resp = http_requests.get(
            "%s/api/v1/auths/" % owui_base,
            headers={"Authorization": "Bearer %s" % token_value},
            timeout=5,
        )
    except Exception:
        return None

    if resp.status_code != 200:
        return None

    try:
        user_data = resp.json()
    except Exception:
        return None

    user_id = str(user_data.get("id") or "").strip()
    if not user_id:
        return None
    email = str(user_data.get("email") or "").strip()
    name = str(user_data.get("name") or "").strip()
    return user_id, email, name


def _apply_security_verification_summary(overview: dict[str, Any]) -> dict[str, Any]:
        current_session = overview.get("current_device_session") or {}
        overview["security_verification"] = {
        "required_actions": ["redeem_code", "revoke_device_session"],
                "current_device_verified": bool(current_session.get("is_elevated")),
                "current_device_verified_until": current_session.get("elevated_until"),
                "current_device_last_verified_at": current_session.get("last_verified_at"),
                "verification_ttl_seconds": DEVICE_SESSION_ELEVATION_TTL_SECONDS,
        }
        return overview


def _find_active_monthly_subscription(subscriptions: list[dict[str, Any]]) -> dict[str, Any] | None:
    now = _utc_now()
    active_rows: list[dict[str, Any]] = []
    for row in subscriptions or []:
        if str(row.get("status") or "").strip().lower() != "active":
            continue
        period_end = row.get("current_period_end")
        if period_end is not None and period_end <= now:
            continue
        active_rows.append(row)
    if not active_rows:
        return None
    active_rows.sort(
        key=lambda row: (
            row.get("current_period_end") is None,
            row.get("current_period_end") or row.get("updated_at") or row.get("created_at"),
        ),
        reverse=True,
    )
    return active_rows[0]


def _build_monthly_package_purchase_guard(conn, user_id: str, package: dict[str, Any]) -> dict[str, Any] | None:
    if str(package.get("product_type") or "").strip().lower() != "monthly_subscription":
        return None
    active_subscription = _find_active_monthly_subscription(_fetch_subscriptions_for_user(conn, user_id))
    if not active_subscription:
        return None
    active_package_code = str(active_subscription.get("package_code") or "").strip()
    target_package_code = str(package.get("package_code") or "").strip()
    is_current_package = active_package_code == target_package_code
    return {
        "blocked": True,
        "active_subscription": active_subscription,
        "button_label": "当前订阅" if is_current_package else "到期后可更换",
        "message": (
            "当前套餐已生效；本阶段不支持重复购买同一月包。"
            if is_current_package
            else "当前已有生效月包；本阶段不支持升降级切换，到期后可重新选择。积分不够时可购买充值包补量。"
        ),
        "reason_code": "current_subscription_active" if is_current_package else "subscription_switch_not_supported",
        "is_current_package": is_current_package,
    }


def _render_portal_session_expired_html() -> str:
        home_url = _portal_public_base_url()
        return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>会话已失效</title>
    <style>
        body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: linear-gradient(135deg, #f4efe6, #dfe8ec); color: #16323a; }}
        .shell {{ min-height: 100vh; display: grid; place-items: center; padding: 24px; }}
        .card {{ width: min(560px, 100%); background: rgba(255,255,255,0.92); border-radius: 24px; padding: 32px; box-shadow: 0 24px 60px rgba(22, 50, 58, 0.12); }}
        h1 {{ margin: 0 0 12px; font-size: 2rem; }}
        p {{ margin: 0 0 14px; line-height: 1.7; }}
        .actions {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px; }}
        a {{ text-decoration: none; }}
        .primary {{ background: #114b5f; color: #fff; padding: 12px 18px; border-radius: 999px; }}
        .secondary {{ background: #fff; color: #114b5f; padding: 12px 18px; border-radius: 999px; border: 1px solid rgba(17, 75, 95, 0.18); }}
    </style>
</head>
<body>
    <div class="shell">
        <div class="card">
            <h1>当前浏览器会话已失效</h1>
            <p>这通常发生在密码刚被重置，或者你主动在另一台设备上执行了安全操作。为了保护账户安全，当前浏览器需要重新登录。</p>
            <p>页面加载时会自动清理本地登录态；如果仍然看到旧状态，直接点下面按钮重新回到首页登录即可。</p>
            <div class="actions">
                <a class="primary" href="{home_url}/">回到首页重新登录</a>
                <a class="secondary" href="{home_url}/portal/guide">查看使用指南</a>
            </div>
        </div>
    </div>
    <script>
        try {{ localStorage.removeItem('token'); }} catch (error) {{}}
        ['token', 'oui-session', 'oauth_id_token', 'xm_device_session'].forEach(function(name) {{
            document.cookie = name + '=; Max-Age=0; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Lax';
        }});
        fetch('/api/v1/auths/signout', {{ method: 'GET', credentials: 'same-origin', cache: 'no-store' }}).catch(function() {{ return null; }});
    </script>
</body>
</html>
"""


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


async def _read_tool_payload(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体需要是合法 JSON")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="请求体需要是 JSON 对象")
    return payload


def _build_portal_guard_response(user_id: str, email: str, name: str) -> Response:
    return Response(
        status_code=200,
        headers={
            "X-Portal-User-Id": user_id,
            "X-Portal-User-Email": email,
            "X-Portal-User-Name": name,
        },
    )


def _build_portal_guard_rate_limited_response(retry_after_seconds: int) -> Response:
    return Response(
        status_code=403,
        headers={
            "X-Portal-Guard-Result": "rate_limited",
            "X-Portal-Guard-Retry-After": str(max(1, int(retry_after_seconds))),
        },
    )


def _public_quick_trial_device_id(request: Request, response: Response) -> str:
    existing = str(request.cookies.get(_PUBLIC_QUICK_TRIAL_COOKIE_NAME) or "").strip()
    if existing:
        return existing[:120]
    created = _generate_id("trial_device")
    response.set_cookie(
        _PUBLIC_QUICK_TRIAL_COOKIE_NAME,
        created,
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        samesite="lax",
    )
    return created


def _public_quick_trial_keys(request: Request, response: Response) -> tuple[str, str]:
    client_ip = _request_client_ip(request)
    device_id = _public_quick_trial_device_id(request, response)
    return f"ip:{client_ip}", f"device:{device_id}"


def _public_quick_trial_remaining(ip_key: str, device_key: str) -> int:
    return max(0, _PUBLIC_QUICK_TRIAL_LIMIT - int(_PUBLIC_QUICK_TRIAL_USED_COUNTS.get(device_key, 0) or 0))


def _reserve_public_quick_trial(ip_key: str, device_key: str) -> None:
    with _PUBLIC_QUICK_TRIAL_LOCK:
        device_total = int(_PUBLIC_QUICK_TRIAL_USED_COUNTS.get(device_key, 0) or 0) + int(_PUBLIC_QUICK_TRIAL_IN_FLIGHT_COUNTS.get(device_key, 0) or 0)
        if device_total >= _PUBLIC_QUICK_TRIAL_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=f"免费排雷体验每台设备限 {_PUBLIC_QUICK_TRIAL_LIMIT} 次；注册后可以保存报告、继续追问并生成完整版。",
            )
        ip_total = int(_PUBLIC_QUICK_TRIAL_USED_COUNTS.get(ip_key, 0) or 0) + int(_PUBLIC_QUICK_TRIAL_IN_FLIGHT_COUNTS.get(ip_key, 0) or 0)
        if ip_total >= _PUBLIC_QUICK_TRIAL_IP_ABUSE_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="当前网络下免费排雷请求过多，请稍后再试或注册后继续使用。",
            )
        keys = {ip_key, device_key}
        for key in keys:
            _PUBLIC_QUICK_TRIAL_IN_FLIGHT_COUNTS[key] += 1


def _finish_public_quick_trial(ip_key: str, device_key: str, *, consumed: bool) -> None:
    with _PUBLIC_QUICK_TRIAL_LOCK:
        keys = {ip_key, device_key}
        for key in keys:
            current = int(_PUBLIC_QUICK_TRIAL_IN_FLIGHT_COUNTS.get(key, 0) or 0)
            if current <= 1:
                _PUBLIC_QUICK_TRIAL_IN_FLIGHT_COUNTS.pop(key, None)
            else:
                _PUBLIC_QUICK_TRIAL_IN_FLIGHT_COUNTS[key] = current - 1
            if consumed:
                _PUBLIC_QUICK_TRIAL_USED_COUNTS[key] += 1


def _normalize_public_quick_input(payload: dict[str, Any]) -> dict[str, str]:
    raw_query = str(payload.get("query") or payload.get("product_query") or "").strip()
    asin = str(payload.get("asin") or "").strip().upper()
    marketplace_raw = str(payload.get("marketplace") or "US").strip() or "US"
    marketplace_upper = marketplace_raw.upper()
    marketplace_code = "US" if marketplace_raw in {"Amazon 美国站", "美国站", "美国", "US", "USA"} or marketplace_upper in {"US", "USA"} else marketplace_raw
    marketplace_label = "Amazon 美国站" if str(marketplace_code).upper() == "US" else marketplace_raw
    if not asin and len(raw_query) == 10 and raw_query.replace(" ", "").isalnum():
        asin = raw_query.upper()
        raw_query = ""
    if asin:
        if len(asin) != 10 or not asin.isalnum():
            raise HTTPException(status_code=400, detail="请输入 10 位 Amazon ASIN")
        return {"input_type": "asin", "asin": asin, "marketplace": marketplace_code, "marketplace_label": marketplace_label, "query": asin}
    if not raw_query:
        raise HTTPException(status_code=400, detail="请输入商品词或 ASIN")
    if len(raw_query) > 120:
        raise HTTPException(status_code=400, detail="商品词过长，请控制在 120 个字符以内")
    query = f"请排雷 {raw_query} 在 {marketplace_label} 是否适合新手卖家。直接给出继续看、谨慎看或暂时放弃的结论，并根据市场需求、竞争强度、价格带、评论壁垒、趋势和主要风险列出关键证据，最后告诉我下一步最值得验证什么。"
    return {"input_type": "query", "product_query": raw_query, "marketplace": marketplace_code, "marketplace_label": marketplace_label, "query": query}


def _decode_public_theme_tool_result(raw_result: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_result)
    except Exception:
        return {"raw_result": str(raw_result or "")[:2000]}
    return parsed if isinstance(parsed, dict) else {"raw_result": parsed}


def _find_public_value(payload: Any, keys: set[str]) -> Any:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key) in keys and value not in (None, "", [], {}):
                return value
        for value in payload.values():
            found = _find_public_value(value, keys)
            if found not in (None, "", [], {}):
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _find_public_value(item, keys)
            if found not in (None, "", [], {}):
                return found
    return None


def _public_theme_tool_status(payload: dict[str, Any]) -> str:
    status = str(_find_public_value(payload, {"status", "degradation_status"}) or "").strip().lower()
    if status in {"provider_required", "skipped", "error", "failed"}:
        return status
    if _find_public_value(payload, {"missing_capability", "required_provider"}):
        return "provider_required"
    return "ok"


def _compact_public_asin_tool_summary(operation: str, payload: dict[str, Any]) -> str:
    if payload.get("error"):
        return f"暂缺：{str(payload.get('error'))[:180]}"
    status = _public_theme_tool_status(payload)
    if status == "provider_required":
        missing = _find_public_value(payload, {"missing_capability", "required_provider"}) or "provider"
        return f"暂缺：需要 {missing} 数据源"
    if status in {"skipped", "error", "failed"}:
        reason = _find_public_value(payload, {"reason", "message", "detail"}) or status
        return f"暂缺：{str(reason)[:180]}"

    key_groups: list[tuple[str, set[str]]] = [
        ("标题", {"product_title", "title"}),
        ("品牌", {"brand", "brand_name"}),
        ("类目", {"leaf_category_name", "l3_category_name", "category_path"}),
        ("价格", {"effective_price", "price", "current_price"}),
        ("BSR", {"bsr", "current_bsr"}),
        ("评论", {"review_count", "reviews", "rating"}),
        ("销量", {"estimated_daily_sales", "sales_daily_avg", "sales_window_sum"}),
        ("趋势", {"window_summary", "review_growth_window", "trend_summary"}),
        ("预测", {"driver_summary_text", "primary_driver_label", "forecast_summary"}),
        ("风险", {"risk_summary", "risk_flags", "diagnostics"}),
    ]
    parts: list[str] = []
    for label, keys in key_groups:
        value = _find_public_value(payload, keys)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (dict, list)):
            value_text = json.dumps(value, ensure_ascii=False)[:220]
        else:
            value_text = str(value)[:220]
        parts.append(f"{label}：{value_text}")
        if len(parts) >= 4:
            break
    if parts:
        return "；".join(parts)
    return "已返回结构化证据，需结合完整数据继续判断。"


def _public_metric_text(payload: dict[str, Any], keys: set[str], default: str = "暂缺") -> str:
    value = _find_public_value(payload, keys)
    if value in (None, "", [], {}):
        return default
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)[:260]
    return str(value)[:260]


def _public_metric_pair(payload: dict[str, Any], label: str, keys: set[str]) -> str:
    return f"**{label}**：{_public_metric_text(payload, keys)}"


def _public_analysis_light(unavailable_count: int, risk_text: str, volatility_text: str) -> str:
    risk_blob = f"{risk_text} {volatility_text}".lower()
    high_risk_markers = ["high", "red", "下降", "下滑", "异常", "风险", "暂缺", "provider_required", "insufficient"]
    if unavailable_count >= 3 or sum(1 for marker in high_risk_markers if marker in risk_blob) >= 3:
        return "红灯：暂时放弃"
    if unavailable_count >= 1 or any(marker in risk_blob for marker in ["异常", "风险", "暂缺", "下降", "下滑"]):
        return "黄灯：谨慎验证"
    return "绿灯：值得继续研究"


def _public_asin_payload_has_evidence(payload: dict[str, Any]) -> bool:
    evidence_keys = {
        "product_title",
        "title",
        "brand",
        "brand_name",
        "leaf_category_name",
        "l3_category_name",
        "category_path",
        "effective_price",
        "price",
        "current_price",
        "bsr",
        "current_bsr",
        "best_sellers_rank",
        "rating",
        "review_rating",
        "average_rating",
        "review_count",
        "reviews",
        "estimated_daily_sales",
        "sales_daily_avg",
        "sales_window_sum",
        "window_summary",
        "review_growth_window",
        "change_30d",
        "change_90d",
        "series",
        "latest_snapshot",
        "keepa_snapshot",
    }
    return _find_public_value(payload, evidence_keys) not in (None, "", [], {})


def _public_asin_payload_has_history_evidence(payload: dict[str, Any]) -> bool:
    series = _find_public_value(payload, {"series"})
    if isinstance(series, list) and len(series) >= 2:
        return True
    window_summary = _find_public_value(payload, {"window_summary"})
    if isinstance(window_summary, dict) and window_summary:
        return True
    return _find_public_value(payload, {"change_30d", "change_90d", "review_growth_window", "sales_window_sum"}) not in (None, "", [], {})


def _public_asin_series(payload: dict[str, Any]) -> list[dict[str, Any]]:
    series = _find_public_value(payload, {"series"})
    if not isinstance(series, list):
        return []
    return [item for item in series if isinstance(item, dict)]


def _public_number_value(payload: dict[str, Any], keys: set[str]) -> float | None:
    value = _find_public_value(payload, keys)
    if isinstance(value, bool) or value in (None, "", [], {}):
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def _public_format_number(value: Any, *, suffix: str = "") -> str:
    if value in (None, "", [], {}):
        return "暂缺"
    try:
        number = float(str(value).replace(",", ""))
        if number.is_integer():
            text = str(int(number))
        else:
            text = f"{number:.2f}".rstrip("0").rstrip(".")
        return f"{text}{suffix}"
    except Exception:
        return str(value)


def _public_series_delta_text(payload: dict[str, Any], days: int) -> str:
    series = _public_asin_series(payload)
    if len(series) < 2:
        return "暂缺"
    window = series[-days:] if len(series) > days else series
    first = window[0]
    last = window[-1]
    parts: list[str] = []
    review_first = _public_number_value(first, {"review_count", "reviews"})
    review_last = _public_number_value(last, {"review_count", "reviews"})
    if review_first is not None and review_last is not None:
        parts.append(f"评论 +{_public_format_number(review_last - review_first)}")
    sales_first = _public_number_value(first, {"estimated_daily_sales", "sales_daily_avg"})
    sales_last = _public_number_value(last, {"estimated_daily_sales", "sales_daily_avg"})
    if sales_first is not None and sales_last is not None:
        parts.append(f"日销 {_public_format_number(sales_first)} -> {_public_format_number(sales_last)}")
    price_values = [_public_number_value(item, {"effective_price", "price", "current_price"}) for item in window]
    price_values = [value for value in price_values if value is not None]
    if price_values:
        parts.append(f"价格 {_public_format_number(min(price_values))}-{_public_format_number(max(price_values))}")
    bsr_first = _public_number_value(first, {"bsr", "current_bsr", "best_sellers_rank"})
    bsr_last = _public_number_value(last, {"bsr", "current_bsr", "best_sellers_rank"})
    if bsr_first is not None and bsr_last is not None:
        parts.append(f"BSR {_public_format_number(bsr_first)} -> {_public_format_number(bsr_last)}")
    if not parts:
        return "暂缺"
    return "；".join(parts)


def _public_window_summary_text(payload: dict[str, Any]) -> str:
    summary = _find_public_value(payload, {"window_summary"})
    if not isinstance(summary, dict):
        summary = {}
    parts: list[str] = []
    if summary.get("sales_daily_avg") not in (None, "", [], {}):
        parts.append(f"90天日销均值 {_public_format_number(summary.get('sales_daily_avg'))}")
    if summary.get("sales_window_sum") not in (None, "", [], {}):
        parts.append(f"窗口销量 {_public_format_number(summary.get('sales_window_sum'))}")
    if summary.get("price_min_window") not in (None, "", [], {}) or summary.get("price_max_window") not in (None, "", [], {}):
        parts.append(f"价格区间 {_public_format_number(summary.get('price_min_window'))}-{_public_format_number(summary.get('price_max_window'))}")
    if summary.get("review_growth_window") not in (None, "", [], {}):
        parts.append(f"评论增长 +{_public_format_number(summary.get('review_growth_window'))}")
    if summary.get("bsr_avg_window") not in (None, "", [], {}):
        parts.append(f"BSR均值 {_public_format_number(summary.get('bsr_avg_window'))}")
    if summary.get("coverage_ratio") not in (None, "", [], {}):
        parts.append(f"覆盖率 {_public_format_number(float(summary.get('coverage_ratio')) * 100, suffix='%')}")
    row_count = summary.get("series_row_count") or len(_public_asin_series(payload))
    if row_count:
        parts.append(f"历史点 {row_count} 条")
    return "；".join(parts) if parts else "暂缺"


def _call_public_asin_tool(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        raw_result = _proxy_theme_api(operation=operation, payload=payload)
        decoded = _decode_public_theme_tool_result(raw_result)
        return {"operation": operation, "ok": True, "payload": decoded, "summary": _compact_public_asin_tool_summary(operation, decoded)}
    except HTTPException as exc:
        return {"operation": operation, "ok": False, "payload": {}, "summary": f"暂缺：{str(exc.detail)[:180]}", "error": str(exc.detail)}


def _run_public_asin_quick_analysis(asin: str, marketplace: str, marketplace_label: str) -> dict[str, Any]:
    history_result = _call_public_asin_tool(
        "asin_history_timeseries",
        {
            "asins": [asin],
            "marketplace": marketplace,
            "window_days": 90,
            "interval": "day",
            "metrics": ["estimated_daily_sales", "effective_price", "bsr", "review_count", "offer_count"],
        },
    )
    tool_results = [history_result]
    history_payload = dict(history_result.get("payload") or {})
    selected_result = history_result if history_result.get("ok") and _public_asin_payload_has_evidence(history_payload) else None
    if not (history_result.get("ok") and _public_asin_payload_has_history_evidence(history_payload)):
        keepa_result = _call_public_asin_tool(
            "keepa_asin_lookup",
            {
                "asins": [asin],
                "marketplace": marketplace,
                "include_history": True,
                "window_days": 90,
                "interval": "day",
                "metrics": ["estimated_daily_sales", "effective_price", "bsr", "review_count", "offer_count"],
            },
        )
        tool_results.append(keepa_result)
        keepa_payload = dict(keepa_result.get("payload") or {})
        if keepa_result.get("ok") and (_public_asin_payload_has_history_evidence(keepa_payload) or selected_result is None and _public_asin_payload_has_evidence(keepa_payload)):
            selected_result = keepa_result

    if selected_result is None:
        first_error = next((result.get("error") for result in tool_results if result.get("error")), "ASIN 历史/Keepa 查询暂未返回可用数据")
        raise HTTPException(status_code=502, detail=str(first_error)[:4000])

    selected_operation = str(selected_result.get("operation") or "")
    selected_payload = dict(selected_result.get("payload") or {})
    source_label = "本地 ASIN 历史时序" if selected_operation == "asin_history_timeseries" else "Keepa 历史补充（include_history=true）"

    current_snapshot = "；".join([
        _public_metric_pair(selected_payload, "标题", {"product_title", "title"}),
        _public_metric_pair(selected_payload, "品牌", {"brand", "brand_name"}),
        _public_metric_pair(selected_payload, "类目", {"category", "leaf_category_name", "l3_category_name", "category_path"}),
        _public_metric_pair(selected_payload, "当前价格", {"effective_price", "price", "current_price"}),
        _public_metric_pair(selected_payload, "预估日销", {"estimated_daily_sales", "sales_daily_avg"}),
        _public_metric_pair(selected_payload, "BSR", {"bsr", "current_bsr", "best_sellers_rank"}),
        _public_metric_pair(selected_payload, "评分", {"rating", "review_rating", "average_rating"}),
        _public_metric_pair(selected_payload, "评论数", {"review_count", "reviews"}),
    ])
    change_30_90 = "；".join([
        f"**近 30 天**：{_public_series_delta_text(selected_payload, 30)}",
        f"**近 90 天**：{_public_series_delta_text(selected_payload, 90)}",
        f"**窗口摘要**：{_public_window_summary_text(selected_payload)}",
    ])
    review_barrier = "；".join([
        _public_metric_pair(selected_payload, "当前评分", {"rating", "review_rating", "average_rating"}),
        _public_metric_pair(selected_payload, "评论总数", {"review_count", "reviews"}),
        _public_metric_pair(selected_payload, "90天评论增长", {"review_growth", "review_growth_window", "review_growth_90d", "review_count_change"}),
    ])
    volatility_text = "；".join([
        f"**价格/BSR/销量**：{_public_window_summary_text(selected_payload)}",
        f"**数据来源**：{source_label}",
    ])
    unavailable_count = 0 if selected_result.get("ok") else 1
    conclusion = _public_analysis_light(unavailable_count, review_barrier, volatility_text)

    if conclusion.startswith("绿灯"):
        research_action = "可以作为竞品、跟卖参考或选品样本继续研究，但仍要补利润、合规和供应链验证。"
    elif conclusion.startswith("黄灯"):
        research_action = "可以作为竞品观察样本，但不建议直接跟卖；先验证利润空间、评论壁垒和销量稳定性。"
    else:
        research_action = "暂时不建议作为跟卖参考或选品样本投入预算；除非后续补到更稳定的销量、评论和利润证据。"

    answer = "\n".join([
        f"# ASIN 快速排雷：{asin}",
        "",
        f"**最终结论：{conclusion}**",
        "",
        "## 当前盘面",
        current_snapshot,
        "",
        "## 近 30/90 天变化",
        change_30_90,
        "",
        "## 评论增长与壁垒",
        review_barrier,
        "",
        "## 价格 / BSR / 销量波动",
        volatility_text,
        "",
        "## 是否值得继续研究",
        research_action,
        "",
        "---",
        "注册后可以保存这份报告、继续追问竞品差异，或生成完整版商品体检。",
    ])
    return {
        "profile": "asin_quick_analysis",
        "input_type": "asin",
        "asin": asin,
        "marketplace": marketplace,
        "marketplace_label": marketplace_label,
        "answer": answer,
        "tool_chain": [result.get("operation") for result in tool_results],
        "selected_tool": selected_operation,
        "tool_results": tool_results,
    }


def _extract_public_report_answer(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("answer", "text", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for key in ("answer", "text", "content"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    outputs = data.get("outputs") if isinstance(data.get("outputs"), dict) else {}
    for key in ("answer", "text", "result", "output"):
        value = outputs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in outputs.values():
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _enforce_email_verification_ip_guard(conn, request: Request, action: str) -> Response | None:
    limits = _get_email_verification_security_config(conn)
    if action == "request":
        window_seconds = int(limits.get("request_ip_window_seconds") or 0)
        max_attempts = int(limits.get("request_ip_max_attempts") or 0)
    else:
        window_seconds = int(limits.get("confirm_ip_window_seconds") or 0)
        max_attempts = int(limits.get("confirm_ip_max_attempts") or 0)
    if window_seconds <= 0 or max_attempts <= 0:
        return None

    client_ip = _request_client_ip(request)
    bucket_key = f"{action}:{client_ip}"
    now = time.monotonic()
    with _EMAIL_VERIFICATION_IP_GUARD_LOCK:
        bucket = _EMAIL_VERIFICATION_IP_GUARD_BUCKETS[bucket_key]
        while bucket and bucket[0] <= now - window_seconds:
            bucket.popleft()
        if len(bucket) >= max_attempts:
            retry_after = int(max(1, window_seconds - (now - bucket[0]))) if bucket else window_seconds
            return _build_portal_guard_rate_limited_response(retry_after)
        bucket.append(now)
    return None


def _portal_email_verification_guard(request: Request, action: str) -> Response:
    resolved_user = _resolve_openwebui_session_user(request)
    if resolved_user is None:
        return Response(status_code=401)

    user_id, email, name = resolved_user
    try:
        with _postgres_conn() as conn:
            _ensure_user_record(conn, user_id=user_id, email=email, display_name=name)
            guard_response = _enforce_email_verification_ip_guard(conn, request, action)
            if guard_response is not None:
                return guard_response
    except Exception:
        return Response(status_code=500)
    return _build_portal_guard_response(user_id, email, name)


def _portal_user_requires_email_verification(conn, user_id: str) -> bool:
    if not _portal_email_verification_gate_enabled():
        return False
    user = _fetch_user(conn, user_id)
    return user.email_verified_at is None


def _enforce_verified_portal_user(conn, user_id: str) -> None:
    if _portal_user_requires_email_verification(conn, user_id):
        raise HTTPException(status_code=403, detail="email verification required before using portal features")


def _normalize_portal_provider(provider: str) -> str:
    normalized = str(provider or "").strip().lower() or "alipay"
    if normalized == "wxpay":
        normalized = "wechat"
    if normalized not in _PORTAL_PROVIDER_LABELS:
        raise HTTPException(status_code=400, detail=f"unsupported payment provider: {provider}")
    return normalized


def _build_portal_payment_response(conn, order_row: dict[str, Any]) -> dict[str, Any]:
    package = _fetch_billing_package(conn, order_row["package_code"])
    latest_session = _fetch_latest_payment_session(conn, order_row["order_id"])
    payment_log = _build_portal_payment_log(order_row, latest_session)
    return {
        "order": order_row,
        "package": package,
        "pricing_snapshot": order_row.get("promotion_snapshot_json") or {},
        "payment_session": latest_session,
        "payment_log": payment_log,
        "mock_payment_enabled": PORTAL_MOCK_PAYMENT_ENABLED,
    }


def _build_portal_payment_log(order_row: dict[str, Any], latest_session: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if order_row.get("created_at"):
        rows.append({"time": order_row.get("created_at"), "message": "订单已创建"})
    if latest_session:
        if latest_session.get("created_at"):
            rows.append({"time": latest_session.get("created_at"), "message": "微信支付二维码已生成"})
        session_meta = dict(latest_session.get("prepay_payload_json") or {})
        if session_meta.get("last_query_at"):
            message = "已向微信支付查询订单状态"
            if session_meta.get("last_query_error"):
                message = "微信支付查单暂未成功，页面会继续重试"
            rows.append({"time": session_meta.get("last_query_at"), "message": message})
        if str(latest_session.get("status") or "").lower() == "expired":
            rows.append({"time": latest_session.get("updated_at"), "message": "二维码已过期"})
        if str(latest_session.get("status") or "").lower() == "paid":
            rows.append({"time": latest_session.get("paid_at") or latest_session.get("updated_at"), "message": "微信支付已确认"})
    if str(order_row.get("status") or "").lower() == "paid":
        rows.append({"time": order_row.get("paid_at") or order_row.get("updated_at"), "message": "积分已到账"})
    if str(order_row.get("status") or "").lower() == "closed":
        rows.append({"time": order_row.get("updated_at"), "message": "支付订单已取消"})
    return [row for row in rows if row.get("time") or row.get("message")]


def _portal_payment_order_status_label(status: Any) -> str:
    normalized = str(status or "").strip().lower()
    return {
        "paid": "成功",
        "pending": "待支付",
        "closed": "已取消",
        "expired": "已过期",
        "failed": "失败",
        "refunded": "已退款",
    }.get(normalized, str(status or "未知"))


def _build_portal_payment_order_list_row(row: dict[str, Any]) -> dict[str, Any]:
    package_meta = dict(row.get("package_meta_json") or {})
    package_name = str(
        package_meta.get("display_name")
        or row.get("package_name")
        or row.get("package_code")
        or "充值订单"
    )
    provider = str(row.get("provider") or "").strip().lower()
    return {
        "order_id": row.get("order_id"),
        "package_code": row.get("package_code"),
        "package_name": package_name,
        "product_type": row.get("product_type"),
        "provider": provider,
        "provider_label": _PORTAL_PROVIDER_LABELS.get(provider) or provider or "-",
        "amount_cents": int(row.get("amount_cents") or 0),
        "points_amount": int(row.get("points_amount") or 0),
        "status": row.get("status"),
        "status_label": _portal_payment_order_status_label(row.get("status")),
        "paid_at": row.get("paid_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _close_pending_payment_order_locally(conn, order_row: dict[str, Any], *, reason: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    close_meta = {
        "closed_via": "portal_wechat_modal",
        "closed_reason": reason,
        "closed_at": now.isoformat(),
    }
    _run_pg_dict_query(
        conn,
        """
        UPDATE app.payment_session
        SET status = 'closed',
            prepay_payload_json = COALESCE(prepay_payload_json, '{}'::jsonb) || %s::jsonb,
            updated_at = NOW()
        WHERE order_id = %s
          AND status = 'pending'
        RETURNING session_id
        """,
        [psycopg2.extras.Json(close_meta), order_row["order_id"]],
    )
    rows = _run_pg_dict_query(
        conn,
        """
        UPDATE app.payment_order
        SET status = 'closed',
            callback_payload_json = COALESCE(callback_payload_json, '{}'::jsonb) || %s::jsonb,
            updated_at = NOW()
        WHERE order_id = %s
          AND user_id = %s
          AND status = 'pending'
        RETURNING order_id, user_id, package_code, product_type, provider, list_amount_cents,
                  discount_amount_cents, amount_cents, points_amount, status,
                  provider_order_id, provider_trade_no, promotion_snapshot_json,
                  callback_payload_json, paid_at, created_at, updated_at
        """,
        [psycopg2.extras.Json(close_meta), order_row["order_id"], order_row["user_id"]],
    )
    return rows[0] if rows else _fetch_payment_order_for_user(conn, order_row["order_id"], order_row["user_id"])


def _close_expired_pending_wechat_orders(conn, *, user_id: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = [WECHAT_NATIVE_QR_TTL_SECONDS]
    user_clause = ""
    if user_id:
        user_clause = " AND payment_order.user_id = %s"
        params.append(user_id)
    now = datetime.now(timezone.utc)
    close_meta = {
        "closed_via": "wechat_qr_ttl_guard",
        "closed_reason": "wechat_qr_expired",
        "closed_at": now.isoformat(),
        "ttl_seconds": WECHAT_NATIVE_QR_TTL_SECONDS,
    }
    params.append(psycopg2.extras.Json(close_meta))
    params.append(psycopg2.extras.Json(close_meta))
    return _run_pg_dict_query(
        conn,
        """
        WITH expired_orders AS (
            SELECT payment_order.order_id
            FROM app.payment_order AS payment_order
            WHERE payment_order.provider = 'wechat'
              AND payment_order.status = 'pending'
              AND payment_order.created_at <= NOW() - (%s * INTERVAL '1 second')
              {user_clause}
        ), closed_sessions AS (
            UPDATE app.payment_session AS payment_session
            SET status = 'closed',
                prepay_payload_json = COALESCE(payment_session.prepay_payload_json, '{{}}'::jsonb) || %s::jsonb,
                updated_at = NOW()
            FROM expired_orders
            WHERE payment_session.order_id = expired_orders.order_id
              AND payment_session.status = 'pending'
            RETURNING payment_session.session_id
        )
        UPDATE app.payment_order AS payment_order
        SET status = 'closed',
            callback_payload_json = COALESCE(payment_order.callback_payload_json, '{{}}'::jsonb) || %s::jsonb,
            updated_at = NOW()
        FROM expired_orders
        WHERE payment_order.order_id = expired_orders.order_id
          AND payment_order.status = 'pending'
        RETURNING payment_order.order_id, payment_order.user_id, payment_order.package_code,
                  payment_order.product_type, payment_order.provider, payment_order.list_amount_cents,
                  payment_order.discount_amount_cents, payment_order.amount_cents,
                  payment_order.points_amount, payment_order.status, payment_order.provider_order_id,
                  payment_order.provider_trade_no, payment_order.promotion_snapshot_json,
                  payment_order.callback_payload_json, payment_order.paid_at,
                  payment_order.created_at, payment_order.updated_at
        """.format(user_clause=user_clause),
        params,
    )


def _parse_optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _call_internal_payment_callback(provider: str, payload: dict[str, Any], *, idempotency_key: str, service_name: str) -> dict[str, Any]:
    if not INTERNAL_SERVICE_SECRET:
        raise HTTPException(status_code=503, detail="internal service secret is not configured")
    callback_url = _backend_base_url() + f"/internal/payments/provider-callback/{provider}"
    headers = {
        INTERNAL_SERVICE_SECRET_HEADER_NAME: INTERNAL_SERVICE_SECRET,
        INTERNAL_SERVICE_NAME_HEADER_NAME: service_name,
        IDEMPOTENCY_KEY_HEADER_NAME: idempotency_key,
    }
    try:
        response = http_requests.post(callback_url, headers=headers, json=payload, timeout=12)
    except Exception as exc:  # pragma: no cover - network failure only
        raise HTTPException(status_code=502, detail=f"payment callback failed: {exc}") from exc
    try:
        response_json = response.json()
    except Exception:
        response_json = {"message": response.text.strip() or response.reason}
    if response.status_code != 200 or response_json.get("success") is not True:
        raise HTTPException(
            status_code=502,
            detail=response_json.get("detail") or response_json.get("message") or "payment callback failed",
        )
    return response_json


def _maybe_refresh_wechat_order_from_provider(order_row: dict[str, Any], latest_session: dict[str, Any] | None) -> None:
    if str(order_row.get("provider") or "").strip().lower() != "wechat":
        return
    if str(order_row.get("status") or "").strip().lower() != "pending":
        return
    if not latest_session:
        return
    session_meta = dict(latest_session.get("prepay_payload_json") or {})
    last_query_at = _parse_optional_datetime(session_meta.get("last_query_at"))
    now = datetime.now(timezone.utc)
    expires_at = _parse_optional_datetime(latest_session.get("expires_at"))
    if expires_at is not None and expires_at <= now:
        with _postgres_conn() as conn:
            _update_payment_session_status(
                conn,
                session_id=str(latest_session["session_id"]),
                status="expired",
                prepay_payload_json={
                    **session_meta,
                    "expired_by": "portal_order_polling",
                    "expired_at": now.isoformat(),
                },
            )
        return
    if last_query_at is not None and (now - last_query_at).total_seconds() < 8:
        return

    try:
        trade_response = query_wechat_order_by_out_trade_no(str(order_row["order_id"]))
    except HTTPException as exc:
        with _postgres_conn() as conn:
            updated_meta = {
                **session_meta,
                "last_query_at": now.isoformat(),
                "last_query_error": str(exc.detail),
            }
            _update_payment_session_status(
                conn,
                session_id=str(latest_session["session_id"]),
                status=str(latest_session.get("status") or "pending"),
                prepay_payload_json=updated_meta,
            )
        return

    trade = extract_wechat_trade_payload(trade_response)
    session_status = wechat_trade_state_to_session_status(str(trade.get("trade_state") or ""))
    updated_meta = {
        **session_meta,
        "last_query_at": now.isoformat(),
        "last_query_response": trade_response,
    }

    if session_status == "paid":
        callback_payload = {
            "order_id": order_row["order_id"],
            "provider_order_id": trade.get("provider_order_id") or order_row["order_id"],
            "provider_trade_no": trade.get("provider_trade_no"),
            "paid_amount_cents": trade.get("paid_amount_cents"),
            "meta": {
                "source": "wechat_order_query",
                "trade_state": trade.get("trade_state"),
                "wechat_payload": trade.get("raw") or trade_response,
            },
        }
        _call_internal_payment_callback(
            "wechat",
            callback_payload,
            idempotency_key=f"wechat-query:{trade.get('provider_trade_no') or order_row['order_id']}",
            service_name="wechat-order-query",
        )
        with _postgres_conn() as conn:
            _update_payment_session_status(
                conn,
                session_id=str(latest_session["session_id"]),
                status="paid",
                provider_trade_no=trade.get("provider_trade_no"),
                prepay_payload_json=updated_meta,
                paid_at=now,
            )
        return

    with _postgres_conn() as conn:
        _update_payment_session_status(
            conn,
            session_id=str(latest_session["session_id"]),
            status=session_status,
            provider_trade_no=trade.get("provider_trade_no"),
            prepay_payload_json=updated_meta,
        )
        if session_status in {"closed", "failed"}:
            _run_pg_dict_query(
                conn,
                "UPDATE app.payment_order SET status = %s, updated_at = NOW() WHERE order_id = %s AND status = 'pending' RETURNING order_id",
                [session_status, order_row["order_id"]],
            )


# ---------------------------------------------------------------------------
# Session validation (called by nginx auth_request)
# ---------------------------------------------------------------------------

@router.get("/_internal/portal/validate-session")
def portal_validate_session(request: Request) -> Response:
    """Nginx auth_request subrequest: validate OpenWebUI cookie and return user identity headers."""
    resolved_user = _resolve_openwebui_session_user(request)
    if resolved_user is None:
        return Response(status_code=401)
    user_id, email, name = resolved_user
    try:
        with _postgres_conn() as conn:
            user = _ensure_user_record(conn, user_id=user_id, email=email, display_name=name)
            _auto_request_email_verification_if_needed(conn, user.user_id)
            device_session_state = _evaluate_device_session_request(conn, user_id, request, touch=True)
            if device_session_state["status"] == "invalid":
                return Response(status_code=409)
    except Exception:
        pass

    return Response(
        status_code=200,
        headers={
            "X-Portal-User-Id": user_id,
            "X-Portal-User-Email": email,
            "X-Portal-User-Name": name,
        },
    )


@router.get("/_internal/portal/email-verification/request-guard")
def portal_email_verification_request_guard(request: Request) -> Response:
    return _portal_email_verification_guard(request, "request")


@router.get("/_internal/portal/email-verification/confirm-guard")
def portal_email_verification_confirm_guard(request: Request) -> Response:
    return _portal_email_verification_guard(request, "confirm")


@router.get("/_internal/openwebui/verified-user-check")
def openwebui_verified_user_check(request: Request) -> Response:
    """Nginx auth_request for Open WebUI root traffic.

    - anonymous user: 401, let nginx pass through to Open WebUI login page
    - logged-in but unverified user: 403, let nginx redirect to /portal/account
    - logged-in and verified user: 200
    """
    resolved_user = _resolve_openwebui_session_user(request)
    if resolved_user is None:
        return Response(status_code=401)

    user_id, email, name = resolved_user
    try:
        with _postgres_conn() as conn:
            user = _ensure_user_record(conn, user_id=user_id, email=email, display_name=name)
            _auto_request_email_verification_if_needed(conn, user.user_id)
            device_session_state = _evaluate_device_session_request(conn, user_id, request, touch=True)
            if device_session_state["status"] == "invalid":
                return Response(status_code=409)
            if _portal_user_requires_email_verification(conn, user_id):
                return Response(status_code=403)
    except Exception:
        return Response(status_code=401)
    return Response(status_code=200)


@router.get("/portal")
def portal_page() -> HTMLResponse:
    return HTMLResponse(render_portal_html(), headers={"Cache-Control": "no-store"})


@router.get("/portal/account")
def portal_account_page() -> HTMLResponse:
    return HTMLResponse(render_portal_html(), headers={"Cache-Control": "no-store"})


@router.get("/portal/product")
def portal_product_page(request: Request) -> HTMLResponse:
    return HTMLResponse(
        render_portal_product_html(indexable=_public_page_is_indexable(request)),
        headers=_public_page_cache_headers(request),
    )


@router.get("/portal/products")
def portal_products_page(request: Request) -> HTMLResponse:
    return HTMLResponse(
        render_portal_products_html(indexable=_public_page_is_indexable(request)),
        headers=_public_page_cache_headers(request),
    )


@router.get("/portal/guide")
def portal_guide_page(request: Request) -> HTMLResponse:
    return HTMLResponse(
        render_portal_guide_html(indexable=_public_page_is_indexable(request)),
        headers=_public_page_cache_headers(request),
    )


@router.get("/portal/tools")
def portal_tools_page(request: Request) -> HTMLResponse:
    return HTMLResponse(
        render_portal_tools_html(indexable=_public_page_is_indexable(request)),
        headers=_public_page_cache_headers(request),
    )


@router.post("/portal/api/public/report/quick")
async def portal_public_quick_report(request: Request, response: Response) -> dict[str, Any]:
    payload = await _read_tool_payload(request)
    trial_input = _normalize_public_quick_input(payload)
    ip_key, device_key = _public_quick_trial_keys(request, response)
    _reserve_public_quick_trial(ip_key, device_key)
    consumed = False
    try:
        if trial_input["input_type"] == "asin":
            result_data = _run_public_asin_quick_analysis(
                asin=trial_input["asin"],
                marketplace=trial_input["marketplace"],
                marketplace_label=trial_input["marketplace_label"],
            )
            answer = str(result_data.get("answer") or "").strip()
            message = "ASIN quick analysis generated"
        else:
            provider_response = _proxy_report_blocking(
                query=trial_input["query"],
                user=device_key.replace(":", "_"),
                profile="quick",
            )
            answer = _extract_public_report_answer(provider_response)
            if not answer:
                raise HTTPException(status_code=502, detail="quick 排雷上游暂未返回报告内容，请稍后重试")
            result_data = {
                "profile": "quick",
                "input_type": "query",
                "product_query": trial_input["product_query"],
                "marketplace": trial_input["marketplace"],
                "marketplace_label": trial_input["marketplace_label"],
                "query": trial_input["query"],
                "answer": answer,
            }
            message = "quick report generated"
        consumed = True
        remaining = _public_quick_trial_remaining(ip_key, device_key) - 1
        result_data.update({
            "answer": answer,
            "trial_limit": _PUBLIC_QUICK_TRIAL_LIMIT,
            "trial_remaining": max(0, remaining),
            "requires_registration_for": ["save_report", "follow_up", "standard_report", "full_report"],
            "next_action": "注册后可保存本次报告、继续追问，或升级生成完整版商品体检报告。",
        })
        return _success_response(
            "/portal/api/public/report/quick",
            result_data,
            message,
        )
    finally:
        _finish_public_quick_trial(ip_key, device_key, consumed=consumed)


@router.post("/portal/api/public/tools/profit-calculator")
async def portal_tools_profit_calculator(request: Request) -> dict[str, Any]:
    payload = await _read_tool_payload(request)
    try:
        result = compute_profit_calculator(payload)
    except ToolInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _success_response("/portal/api/public/tools/profit-calculator", result, "profit calculated")


@router.post("/portal/api/public/tools/pricing-reverse")
async def portal_tools_pricing_reverse(request: Request) -> dict[str, Any]:
    payload = await _read_tool_payload(request)
    try:
        result = compute_pricing_reverse(payload)
    except ToolInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _success_response("/portal/api/public/tools/pricing-reverse", result, "pricing computed")


@router.post("/portal/api/public/tools/title-diagnose")
async def portal_tools_title_diagnose(request: Request) -> dict[str, Any]:
    payload = await _read_tool_payload(request)
    try:
        result = diagnose_title(payload, client_ip=_request_client_ip(request))
    except ToolInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _success_response("/portal/api/public/tools/title-diagnose", result, "title diagnosed")


@router.post("/portal/api/public/tools/keyword-clean")
async def portal_tools_keyword_clean(request: Request) -> dict[str, Any]:
    payload = await _read_tool_payload(request)
    try:
        result = clean_and_expand_keywords(payload, client_ip=_request_client_ip(request))
    except ToolInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _success_response("/portal/api/public/tools/keyword-clean", result, "keywords cleaned")


@router.post("/portal/api/public/tools/description-generator")
async def portal_tools_description_generator(request: Request) -> dict[str, Any]:
    payload = await _read_tool_payload(request)
    try:
        result = generate_description(payload, client_ip=_request_client_ip(request))
    except ToolInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _success_response("/portal/api/public/tools/description-generator", result, "description generated")


@router.post("/portal/api/public/tools/compliance-check")
async def portal_tools_compliance_check(request: Request) -> dict[str, Any]:
    payload = await _read_tool_payload(request)
    try:
        result = check_compliance(payload, client_ip=_request_client_ip(request))
    except ToolInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _success_response("/portal/api/public/tools/compliance-check", result, "compliance checked")


@router.post("/portal/api/public/tools/acos-breakeven")
async def portal_tools_acos_breakeven(request: Request) -> dict[str, Any]:
    payload = await _read_tool_payload(request)
    try:
        result = compute_acos_breakeven(payload)
    except ToolInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _success_response("/portal/api/public/tools/acos-breakeven", result, "acos computed")


@router.post("/portal/api/public/tools/dimensional-weight")
async def portal_tools_dimensional_weight(request: Request) -> dict[str, Any]:
    payload = await _read_tool_payload(request)
    try:
        result = compute_dimensional_weight(payload)
    except ToolInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _success_response("/portal/api/public/tools/dimensional-weight", result, "weight computed")


@router.post("/portal/api/public/tools/landed-price")
async def portal_tools_landed_price(request: Request) -> dict[str, Any]:
    payload = await _read_tool_payload(request)
    try:
        result = compute_landed_price(payload)
    except ToolInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _success_response("/portal/api/public/tools/landed-price", result, "landed price computed")


@router.post("/portal/api/public/tools/listing-health")
async def portal_tools_listing_health(request: Request) -> dict[str, Any]:
    payload = await _read_tool_payload(request)
    try:
        result = score_listing_health(payload)
    except ToolInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _success_response("/portal/api/public/tools/listing-health", result, "listing scored")


@router.post("/portal/api/public/tools/competitor-gaps")
async def portal_tools_competitor_gaps(request: Request) -> dict[str, Any]:
    payload = await _read_tool_payload(request)
    try:
        result = extract_competitor_gaps(payload, client_ip=_request_client_ip(request))
    except ToolInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _success_response("/portal/api/public/tools/competitor-gaps", result, "competitor analyzed")


@router.post("/portal/api/public/tools/aplus-outline")
async def portal_tools_aplus_outline(request: Request) -> dict[str, Any]:
    payload = await _read_tool_payload(request)
    try:
        result = generate_aplus_outline(payload, client_ip=_request_client_ip(request))
    except ToolInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _success_response("/portal/api/public/tools/aplus-outline", result, "outline generated")


@router.post("/portal/api/public/tools/review-mining")
async def portal_tools_review_mining(request: Request) -> dict[str, Any]:
    payload = await _read_tool_payload(request)
    try:
        result = mine_reviews(payload, client_ip=_request_client_ip(request))
    except ToolInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _success_response("/portal/api/public/tools/review-mining", result, "reviews mined")


@router.post("/portal/api/public/tools/service-reply")
async def portal_tools_service_reply(request: Request) -> dict[str, Any]:
    payload = await _read_tool_payload(request)
    try:
        result = generate_service_reply(payload, client_ip=_request_client_ip(request))
    except ToolInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _success_response("/portal/api/public/tools/service-reply", result, "reply generated")


@router.get("/portal/invite")
def portal_invite_page(request: Request) -> HTMLResponse:
    return HTMLResponse(
        render_portal_invite_html(indexable=_public_page_is_indexable(request)),
        headers=_public_page_cache_headers(request),
    )


@router.get("/robots.txt", include_in_schema=False)
def robots_txt() -> Response:
    return Response(
        render_robots_txt(),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml() -> Response:
    return Response(
        render_sitemap_xml(),
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/llms.txt", include_in_schema=False)
def llms_txt() -> Response:
    return Response(
        render_llms_txt(),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/portal/recover-password", response_model=None)
def portal_password_reset_page(request: Request) -> Response:
    if _resolve_openwebui_session_user(request) is not None:
        redirect_target = "/portal/account"
        portal_token = (request.query_params.get("t") or "").strip()
        if portal_token:
            redirect_target += f"?t={portal_token}"
        return RedirectResponse(redirect_target, status_code=303, headers={"Cache-Control": "no-store"})
    return HTMLResponse(render_portal_password_reset_html(), headers={"Cache-Control": "no-store"})


@router.get("/portal/session-expired")
def portal_session_expired_page() -> HTMLResponse:
    return HTMLResponse(_render_portal_session_expired_html(), headers={"Cache-Control": "no-store"})


@router.post("/_xm/session/bootstrap")
def bootstrap_openwebui_device_session(request: Request, response: Response) -> dict[str, Any]:
    resolved_user = _resolve_openwebui_session_user(request)
    if resolved_user is None:
        raise HTTPException(status_code=401, detail="not authenticated")

    user_id, email, display_name = resolved_user
    with _postgres_conn() as conn:
        user = _ensure_user_record(conn, user_id=user_id, email=email, display_name=display_name)
        _auto_request_email_verification_if_needed(conn, user.user_id)
        session_row, raw_token, created = _bootstrap_device_session(conn, user_id, request)
        if session_row is None or raw_token is None:
            raise HTTPException(status_code=409, detail="current device session expired")
        _set_device_session_cookie(response, raw_token)
    return _success_response(
        "/_xm/session/bootstrap",
        {
            "created": created,
            "session": _serialize_device_session(session_row, current_session_id=session_row.get("session_id")),
        },
        "device session ready",
    )


@router.get("/portal/api/public/site-contact-config")
def portal_public_site_contact_config() -> dict[str, Any]:
    with _postgres_conn() as conn:
        contact = _get_contact_config(conn)
    return _success_response(
        "/portal/api/public/site-contact-config",
        {"contact": contact},
        "portal site contact config loaded",
    )


@router.get("/portal/api/public/referral/preview")
def portal_public_referral_preview(invite_code: str = "") -> dict[str, Any]:
    normalized_invite_code = (invite_code or "").strip().upper()
    if not normalized_invite_code:
        raise HTTPException(status_code=400, detail="missing invite code")

    with _postgres_conn() as conn:
        inviter = _fetch_user_by_invite_code(conn, normalized_invite_code)
        signup_reward_points, _ = _resolve_signup_gift_points(conn)
        bind_reward_points, _ = _resolve_referral_invited_reward_points(conn)

    if inviter is None:
        raise HTTPException(status_code=404, detail="invite code not found")

    return _success_response(
        "/portal/api/public/referral/preview",
        {
            "invite_code": inviter.invite_code,
            "inviter_user_id": inviter.user_id,
            "inviter_display_name": inviter.display_name,
            "inviter_email_masked": _mask_email_for_display(inviter.email),
            "signup_reward_points": signup_reward_points,
            "bind_reward_points": bind_reward_points,
        },
        "invite code preview loaded",
    )


@router.post("/portal/api/public/password-reset/request")
def portal_request_password_reset(request: Request, payload: RequestPasswordResetRequest) -> dict[str, Any]:
    with _postgres_conn() as conn:
        rate_limited = _enforce_email_verification_ip_guard(conn, request, "request")
        if rate_limited is not None:
            retry_after = int(rate_limited.headers.get("X-Portal-Guard-Retry-After") or 1)
            raise HTTPException(status_code=429, detail=f"请求过于频繁，请在 {retry_after} 秒后重试")
        result = _request_password_reset(conn, payload.email)
    return _success_response(
        "/portal/api/public/password-reset/request",
        result,
        "password reset request accepted",
    )


@router.post("/portal/api/public/password-reset/confirm")
def portal_confirm_password_reset(
    request: Request,
    payload: ConfirmPasswordResetRequest,
) -> dict[str, Any]:
    with _postgres_conn() as conn:
        rate_limited = _enforce_email_verification_ip_guard(conn, request, "confirm")
        if rate_limited is not None:
            retry_after = int(rate_limited.headers.get("X-Portal-Guard-Retry-After") or 1)
            raise HTTPException(status_code=429, detail=f"请求过于频繁，请在 {retry_after} 秒后重试")
        result = _confirm_password_reset(conn, payload.email, payload.code, payload.new_password)
    return _success_response(
        "/portal/api/public/password-reset/confirm",
        result,
        "password reset completed",
    )


@router.get("/portal/contact/wechat-qr")
def portal_wechat_qr_image() -> FileResponse:
    if not _WECHAT_QR_IMAGE_PATH.exists():
        raise HTTPException(status_code=404, detail="wechat qr image not found")
    return FileResponse(
        path=str(_WECHAT_QR_IMAGE_PATH),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/portal/assets/wechat-pay-logo.svg")
def portal_wechat_pay_logo() -> FileResponse:
    if not _WECHAT_PAY_LOGO_PATH.exists():
        raise HTTPException(status_code=404, detail="wechat pay logo not found")
    return FileResponse(
        path=str(_WECHAT_PAY_LOGO_PATH),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/portal/checkout")
def portal_checkout_page(request: Request) -> HTMLResponse:
    user_id = _require_portal_user(request)
    subscription_purchase_guard: dict[str, Any] | None = None
    with _postgres_conn() as conn:
        if _portal_user_requires_email_verification(conn, user_id):
            redirect_target = "/portal/account"
            portal_token = (request.query_params.get("t") or "").strip()
            if portal_token:
                redirect_target += f"?t={portal_token}"
            return RedirectResponse(url=redirect_target, status_code=302)
    package_code = (request.query_params.get("package_code") or "").strip()
    selected_package: dict[str, Any] | None = None
    pricing_preview: dict[str, Any] | None = None
    if package_code:
        with _postgres_conn() as conn:
            selected_package = _fetch_billing_package(conn, package_code)
            subscription_purchase_guard = _build_monthly_package_purchase_guard(conn, user_id, selected_package)
            pricing_preview = _build_payment_order_snapshot(
                conn,
                user_id=user_id,
                package=selected_package,
                order_id=f"preview:{package_code}",
            )
    return HTMLResponse(
        render_portal_checkout_html(
            selected_package=selected_package,
            pricing_preview=pricing_preview,
            mock_payment_enabled=PORTAL_MOCK_PAYMENT_ENABLED,
            subscription_purchase_guard=subscription_purchase_guard,
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/portal/api/account")
def portal_get_account(request: Request, response: Response) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        session_row, raw_token, _created = _bootstrap_device_session(conn, user_id, request)
        if session_row is None or raw_token is None:
            raise HTTPException(status_code=409, detail="current device session expired")
        _set_device_session_cookie(response, raw_token)
        overview = _build_user_account_overview(
            conn,
            user_id,
            current_device_session_id=str(session_row.get("session_id") or "") or None,
            ledger_limit=50,
            usage_limit=50,
        )
        overview = _apply_security_verification_summary(overview)
    return _success_response("/portal/api/account", overview, "account loaded")


@router.post("/portal/api/account/security-verification/request")
def portal_request_security_verification(request: Request, response: Response) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        session_row, raw_token, _created = _bootstrap_device_session(conn, user_id, request)
        if session_row is None or raw_token is None:
            raise HTTPException(status_code=409, detail="current device session expired")
        _set_device_session_cookie(response, raw_token)
        result = _request_security_verification(conn, user_id)
    return _success_response(
        "/portal/api/account/security-verification/request",
        result,
        "security verification code sent",
    )


@router.post("/portal/api/account/security-verification/confirm")
def portal_confirm_security_verification(
    request: Request,
    response: Response,
    payload: ConfirmSecurityVerificationRequest,
) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        session_row = _current_device_session_or_raise(conn, user_id, request)
        _confirm_security_verification(conn, user_id, payload.code)
        elevated_session = _elevate_device_session(conn, str(session_row["session_id"]))
        session_check = _evaluate_device_session_request(conn, user_id, request, touch=False)
        raw_token = session_check.get("raw_token")
        if raw_token:
            _set_device_session_cookie(response, raw_token)
        overview = _build_user_account_overview(
            conn,
            user_id,
            current_device_session_id=str(elevated_session.get("session_id") or "") or None,
            ledger_limit=50,
            usage_limit=50,
        )
        overview = _apply_security_verification_summary(overview)
    return _success_response(
        "/portal/api/account/security-verification/confirm",
        overview,
        "security verification confirmed",
    )


@router.post("/portal/api/account/email-verification/request")
def portal_request_email_verification(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        result = _request_email_verification(conn, user_id)
    return _success_response(
        "/portal/api/account/email-verification/request",
        result,
        "email verification code sent",
    )


@router.post("/portal/api/account/email-verification/confirm")
def portal_confirm_email_verification(request: Request, payload: ConfirmEmailVerificationRequest) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        current_session = _current_device_session_or_raise(conn, user_id, request)
        verified_user = _confirm_email_verification(conn, user_id, payload.code)
        _ensure_user_credit_account_state(conn, verified_user)
        overview = _build_user_account_overview(
            conn,
            user_id,
            current_device_session_id=str(current_session.get("session_id") or "") or None,
            ledger_limit=50,
            usage_limit=50,
        )
        overview = _apply_security_verification_summary(overview)
    return _success_response(
        "/portal/api/account/email-verification/confirm",
        overview,
        "email verified",
    )


@router.get("/portal/email-verification/confirm", response_model=None)
def portal_confirm_email_verification_link(challenge_id: str = "", token: str = "") -> HTMLResponse:
    try:
        with _postgres_conn() as conn:
            verified_user = _confirm_email_verification_link_token(conn, challenge_id, token)
            _ensure_user_credit_account_state(conn, verified_user)
        html = render_portal_email_verification_result_html(
            success=True,
            title="邮箱验证成功",
            message="你的注册邮箱已完成验证，新用户权益会按账户规则自动结算。",
            email=verified_user.email,
        )
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})
    except HTTPException as exc:
        html = render_portal_email_verification_result_html(
            success=False,
            title="邮箱验证未完成",
            message=str(exc.detail),
        )
        status_code = exc.status_code if 400 <= exc.status_code < 500 else 400
        return HTMLResponse(html, status_code=status_code, headers={"Cache-Control": "no-store"})


@router.post("/portal/api/account/referral/bind")
def portal_bind_referral_code(request: Request, payload: BindReferralCodeRequest) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        current_session = _current_device_session_or_raise(conn, user_id, request)
        _bind_user_referral(conn, user_id, payload.invite_code)
        _grant_referral_invited_reward_if_needed(conn, user_id)
        verified_user = _fetch_user(conn, user_id)
        _ensure_user_credit_account_state(conn, verified_user)
        overview = _build_user_account_overview(
            conn,
            user_id,
            current_device_session_id=str(current_session.get("session_id") or "") or None,
            ledger_limit=50,
            usage_limit=50,
        )
        overview = _apply_security_verification_summary(overview)
    return _success_response(
        "/portal/api/account/referral/bind",
        overview,
        "invite code bound",
    )


@router.post("/portal/api/account/sessions/revoke-others")
def portal_revoke_other_sessions(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        current_session = _require_elevated_device_session(conn, user_id, request)
        revoked_count = _revoke_other_device_sessions(
            conn,
            user_id,
            str(current_session["session_id"]),
            "self_service_revoke_others",
        )
        overview = _build_user_account_overview(
            conn,
            user_id,
            current_device_session_id=str(current_session.get("session_id") or "") or None,
            ledger_limit=50,
            usage_limit=50,
        )
        overview["session_action"] = {"revoked_other_device_count": revoked_count}
        overview = _apply_security_verification_summary(overview)
    return _success_response(
        "/portal/api/account/sessions/revoke-others",
        overview,
        "other device sessions revoked",
    )


@router.post("/portal/api/account/sessions/{session_id}/revoke")
def portal_revoke_device_session(session_id: str, request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        raise HTTPException(status_code=400, detail="device session id is required")
    with _postgres_conn() as conn:
        current_session = _require_elevated_device_session(conn, user_id, request)
        current_session_id = str(current_session.get("session_id") or "")
        if normalized_session_id == current_session_id:
            raise HTTPException(status_code=400, detail="current device cannot be revoked from this action")
        revoked_session = _revoke_device_session(
            conn,
            user_id,
            normalized_session_id,
            "self_service_revoke_device",
            current_session_id=current_session_id or None,
        )
        if revoked_session is None:
            raise HTTPException(status_code=404, detail="device session not found or already revoked")
        overview = _build_user_account_overview(
            conn,
            user_id,
            current_device_session_id=current_session_id or None,
            ledger_limit=50,
            usage_limit=50,
        )
        overview["session_action"] = {
            "action": "revoke_device_session",
            "revoked_session_id": normalized_session_id,
            "revoked_device_label": revoked_session.get("device_label") or "设备",
            "revoked_session_count": int(revoked_session.get("revoked_session_count") or 1),
        }
        overview = _apply_security_verification_summary(overview)
    return _success_response(
        f"/portal/api/account/sessions/{normalized_session_id}/revoke",
        overview,
        "device session revoked",
    )


@router.post("/portal/api/redeem-codes/redeem")
def portal_redeem_code(request: Request, payload: RedeemCodeRedeemRequest) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        current_session = _require_elevated_device_session(conn, user_id, request)
        redeem_result = _redeem_code(conn, user_id=user_id, redeem_code=payload.code)
        overview = _build_user_account_overview(
            conn,
            user_id,
            current_device_session_id=str(current_session.get("session_id") or "") or None,
            ledger_limit=50,
            usage_limit=50,
        )
        overview["redeem_result"] = redeem_result
        overview = _apply_security_verification_summary(overview)
    return _success_response(
        "/portal/api/redeem-codes/redeem",
        overview,
        "redeem code applied",
    )


@router.post("/portal/api/notifications/read-state")
def portal_update_notification_read_state(
    request: Request,
    payload: UpdateNotificationReadStateRequest,
) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        updated_rows = _set_notification_read_state(
            conn,
            user_id,
            read=payload.read,
            notification_ids=payload.notification_ids,
            category=payload.category,
        )
        notifications = _list_notifications_for_user(conn, user_id, limit=100)
    return _success_response(
        "/portal/api/notifications/read-state",
        {"updated_count": len(updated_rows), "notifications": notifications},
        "notification read state updated",
    )


@router.get("/portal/api/billing/catalog")
def portal_get_billing_catalog(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        catalog = _build_billing_catalog(conn, user_id)
    return _success_response(
        "/portal/api/billing/catalog",
        {"user_id": user_id, "catalog": catalog},
        "billing catalog loaded",
    )


@router.get("/portal/api/ledger")
def portal_get_ledger(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    page = max(1, int(request.query_params.get("page", "1")))
    page_size = min(100, max(1, int(request.query_params.get("page_size", "30"))))
    offset = (page - 1) * page_size
    ledger_filter = (request.query_params.get("filter") or "").strip().lower()

    filter_clause = ""
    if ledger_filter == "topup":
        filter_clause = _PORTAL_LEDGER_FILTER_CLAUSES["credit"]
    elif ledger_filter == "spend":
        filter_clause = " AND points_delta < 0"
    elif ledger_filter in _PORTAL_LEDGER_FILTER_CLAUSES:
        filter_clause = _PORTAL_LEDGER_FILTER_CLAUSES[ledger_filter]
    elif ledger_filter == "other":
        filter_clause = (
            " AND NOT ("
            "entry_type = 'consume'"
            " OR entry_type = 'refund'"
            " OR entry_type = 'daily_quota_reset'"
            " OR (points_delta > 0 AND entry_type NOT IN ('refund', 'daily_quota_reset'))"
            ")"
        )

    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        base_query = (
            "SELECT entry_id, entry_type, event_type, units, points_delta, balance_after_points,"
            " reference_id, description, meta_json, created_at"
            " FROM app.credit_ledger_entry"
            " WHERE user_id = %s" + filter_clause +
            " ORDER BY created_at DESC, entry_id DESC"
            " LIMIT %s OFFSET %s"
        )
        rows = [
            _build_portal_ledger_row(row)
            for row in _run_pg_dict_query(conn, base_query, [user_id, page_size, offset])
        ]
        count_query = "SELECT COUNT(*) AS cnt FROM app.credit_ledger_entry WHERE user_id = %s" + filter_clause
        total_row = _fetch_optional_one(conn, count_query, [user_id])
    total = int((total_row or {}).get("cnt", 0))
    return _success_response(
        "/portal/api/ledger",
        {"rows": rows, "page": page, "page_size": page_size, "total": total},
        "ledger loaded",
    )


@router.get("/portal/api/payments/orders")
def portal_list_payment_orders(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    page = max(1, int(request.query_params.get("page", "1")))
    page_size = min(100, max(1, int(request.query_params.get("page_size", "20"))))
    offset = (page - 1) * page_size
    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        _close_expired_pending_wechat_orders(conn, user_id=user_id)
        rows = _run_pg_dict_query(
            conn,
            """
            SELECT payment_order.order_id, payment_order.user_id, payment_order.package_code,
                   payment_order.product_type, payment_order.provider, payment_order.amount_cents,
                   payment_order.points_amount, payment_order.status, payment_order.paid_at,
                   payment_order.created_at, payment_order.updated_at,
                   billing_package.package_name, billing_package.meta_json AS package_meta_json
            FROM app.payment_order AS payment_order
            LEFT JOIN app.billing_package AS billing_package
              ON billing_package.package_code = payment_order.package_code
            WHERE payment_order.user_id = %s
            ORDER BY payment_order.created_at DESC, payment_order.order_id DESC
            LIMIT %s OFFSET %s
            """,
            [user_id, page_size, offset],
        )
        total_row = _fetch_optional_one(
            conn,
            "SELECT COUNT(*) AS cnt FROM app.payment_order WHERE user_id = %s",
            [user_id],
        )
    total = int((total_row or {}).get("cnt", 0))
    return _success_response(
        "/portal/api/payments/orders",
        {
            "rows": [_build_portal_payment_order_list_row(row) for row in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
        },
        "payment orders loaded",
    )


@router.get("/portal/api/usage-daily")
def portal_get_usage_daily(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    days = min(90, max(1, int(request.query_params.get("days", "30"))))
    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
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


@router.post("/portal/api/payments/orders")
def portal_create_payment_order(request: Request, payload: CreatePaymentOrderRequest) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    provider = _normalize_portal_provider(payload.provider)
    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        package = _fetch_billing_package(conn, payload.package_code)
        purchase_guard = _build_monthly_package_purchase_guard(conn, user_id, package)
        if purchase_guard:
            raise HTTPException(status_code=409, detail=str(purchase_guard.get("message") or "current subscription blocks monthly purchase"))
        order_id = _generate_id("order")
        pricing_snapshot = _build_payment_order_snapshot(
            conn,
            user_id=user_id,
            package=package,
            order_id=order_id,
        )
        pricing = pricing_snapshot["pricing"]
        order_row = _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.payment_order (
                order_id, user_id, package_code, product_type, provider, list_amount_cents,
                discount_amount_cents, amount_cents, points_amount, status,
                promotion_snapshot_json, callback_payload_json, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s, NOW(), NOW())
            RETURNING order_id, user_id, package_code, product_type, provider, list_amount_cents,
                      discount_amount_cents, amount_cents, points_amount, status,
                      provider_order_id, provider_trade_no, promotion_snapshot_json,
                      callback_payload_json, paid_at, created_at, updated_at
            """,
            [
                order_id,
                user_id,
                package["package_code"],
                package["product_type"],
                provider,
                pricing["list_amount_cents"],
                pricing["discount_amount_cents"],
                pricing["payable_amount_cents"],
                package["points_amount"],
                psycopg2.extras.Json(pricing_snapshot),
                psycopg2.extras.Json(
                    {
                        "package_name": package["package_name"],
                        "package_meta": package.get("meta_json") or {},
                        "pricing_snapshot": pricing_snapshot,
                        "provider_label": _PORTAL_PROVIDER_LABELS.get(provider) or provider,
                        "created_via": "/portal/api/payments/orders",
                    }
                ),
            ],
        )[0]
    return _success_response(
        "/portal/api/payments/orders",
        {
            "order": order_row,
            "package": package,
            "pricing_snapshot": pricing_snapshot,
            "mock_payment_enabled": PORTAL_MOCK_PAYMENT_ENABLED,
        },
        "portal payment order created",
    )


@router.post("/portal/api/payments/orders/{order_id}/cancel")
def portal_cancel_payment_order(order_id: str, request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    reason = str(request.query_params.get("reason") or "user_close_modal").strip()[:80] or "user_close_modal"
    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        order_row = _fetch_payment_order_for_user(conn, order_id, user_id)
        latest_session = _fetch_latest_payment_session(conn, order_id)

    if str(order_row.get("status") or "").strip().lower() != "pending":
        with _postgres_conn() as conn:
            payload = _build_portal_payment_response(conn, order_row)
        return _success_response(
            f"/portal/api/payments/orders/{order_id}/cancel",
            payload,
            "payment order is already terminal",
        )

    if str(order_row.get("provider") or "").strip().lower() == "wechat" and latest_session:
        _maybe_refresh_wechat_order_from_provider(order_row, latest_session)
        with _postgres_conn() as conn:
            _enforce_verified_portal_user(conn, user_id)
            order_row = _fetch_payment_order_for_user(conn, order_id, user_id)
            latest_session = _fetch_latest_payment_session(conn, order_id)
        if str(order_row.get("status") or "").strip().lower() == "paid":
            with _postgres_conn() as conn:
                payload = _build_portal_payment_response(conn, order_row)
            return _success_response(
                f"/portal/api/payments/orders/{order_id}/cancel",
                payload,
                "payment order paid before cancel",
            )
        try:
            close_wechat_order_by_out_trade_no(order_id)
        except HTTPException as exc:
            detail = str(exc.detail or "").upper()
            if "ORDERPAID" in detail or "PAID" in detail or "已支付" in detail:
                _maybe_refresh_wechat_order_from_provider(order_row, latest_session)
                with _postgres_conn() as conn:
                    _enforce_verified_portal_user(conn, user_id)
                    order_row = _fetch_payment_order_for_user(conn, order_id, user_id)
                    payload = _build_portal_payment_response(conn, order_row)
                return _success_response(
                    f"/portal/api/payments/orders/{order_id}/cancel",
                    payload,
                    "payment order paid before cancel",
                )
            if not ("CLOSED" in detail or "已关闭" in detail or "NOTEXIST" in detail or "不存在" in detail):
                raise

    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        current_order = _fetch_payment_order_for_user(conn, order_id, user_id)
        if str(current_order.get("status") or "").strip().lower() == "pending":
            current_order = _close_pending_payment_order_locally(conn, current_order, reason=reason)
        payload = _build_portal_payment_response(conn, current_order)
    return _success_response(
        f"/portal/api/payments/orders/{order_id}/cancel",
        payload,
        "payment order cancelled",
    )


@router.get("/portal/api/payments/orders/{order_id}")
def portal_get_payment_order(order_id: str, request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        _close_expired_pending_wechat_orders(conn, user_id=user_id)
        order_row = _fetch_payment_order_for_user(conn, order_id, user_id)
        latest_session = _fetch_latest_payment_session(conn, order_id)
    _maybe_refresh_wechat_order_from_provider(order_row, latest_session)
    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        order_row = _fetch_payment_order_for_user(conn, order_id, user_id)
        payload = _build_portal_payment_response(conn, order_row)
    return _success_response(
        f"/portal/api/payments/orders/{order_id}",
        payload,
        "portal payment order loaded",
    )


@router.post("/portal/api/payments/orders/{order_id}/session")
def portal_create_payment_session(order_id: str, request: Request, payload: CreatePaymentSessionRequest) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    provider = _normalize_portal_provider(payload.provider)
    channel = str(payload.channel or "native").strip().lower() or "native"
    if provider != "wechat" or channel != "native":
        raise HTTPException(status_code=400, detail="only wechat native payment session is supported")

    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        _close_expired_pending_wechat_orders(conn, user_id=user_id)
        order_row = _fetch_payment_order_for_user(conn, order_id, user_id)
        if str(order_row.get("provider") or "").strip().lower() != "wechat":
            raise HTTPException(status_code=409, detail="payment order provider is not wechat")
        if str(order_row.get("status") or "").strip().lower() != "pending":
            raise HTTPException(status_code=409, detail="payment order is not pending")
        package = _fetch_billing_package(conn, order_row["package_code"])
        latest_session = _fetch_latest_payment_session(conn, order_id)
        if latest_session and not payload.force_refresh:
            expires_at = _parse_optional_datetime(latest_session.get("expires_at"))
            if (
                str(latest_session.get("status") or "").strip().lower() == "pending"
                and latest_session.get("qr_code_url")
                and (expires_at is None or expires_at > datetime.now(timezone.utc))
            ):
                response_payload = _build_portal_payment_response(conn, order_row)
                response_payload["payment_session"] = latest_session
                return _success_response(
                    f"/portal/api/payments/orders/{order_id}/session",
                    response_payload,
                    "existing payment session reused",
                )

    prepay = create_wechat_native_prepay(order_row, package)
    session_meta = {
        "request_payload": prepay.get("request_payload") or {},
        "response_payload": prepay.get("response_payload") or {},
        "code_url_expires_in_seconds": WECHAT_NATIVE_QR_TTL_SECONDS,
    }
    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        current_order = _fetch_payment_order_for_user(conn, order_id, user_id)
        if str(current_order.get("status") or "").strip().lower() != "pending":
            raise HTTPException(status_code=409, detail="payment order is no longer pending")
        session_row = _create_payment_session(
            conn,
            order_row=current_order,
            provider="wechat",
            channel="native",
            status="pending",
            provider_order_id=str(prepay.get("provider_order_id") or order_id),
            qr_code_url=str(prepay["qr_code_url"]),
            prepay_payload_json=session_meta,
            expires_at=prepay.get("expires_at"),
        )
        response_payload = _build_portal_payment_response(conn, current_order)
        response_payload["payment_session"] = session_row
    return _success_response(
        f"/portal/api/payments/orders/{order_id}/session",
        response_payload,
        "wechat native payment session created",
    )


@router.get("/portal/api/payments/sessions/{session_id}/qr.svg")
def portal_get_payment_session_qr(session_id: str, request: Request) -> Response:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        session_row = _fetch_payment_session(conn, session_id)
    if session_row.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="payment session not found")
    code_url = str(session_row.get("qr_code_url") or "").strip()
    if not code_url:
        raise HTTPException(status_code=404, detail="payment session qr code not found")
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError as exc:  # pragma: no cover - depends on runtime env
        raise HTTPException(status_code=503, detail="qrcode package is required for payment QR rendering") from exc
    qr = qrcode.QRCode(image_factory=qrcode.image.svg.SvgImage, border=2)
    qr.add_data(code_url)
    qr.make(fit=True)
    image = qr.make_image()
    output = BytesIO()
    image.save(output)
    return Response(
        content=output.getvalue(),
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/portal/api/payments/orders/{order_id}/simulate-paid")
def portal_simulate_payment_paid(order_id: str, request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    if not PORTAL_MOCK_PAYMENT_ENABLED:
        raise HTTPException(status_code=403, detail="portal mock payment is disabled")
    if not INTERNAL_SERVICE_SECRET:
        raise HTTPException(status_code=503, detail="internal service secret is not configured")

    with _postgres_conn() as conn:
        _enforce_verified_portal_user(conn, user_id)
        order_row = _fetch_payment_order_for_user(conn, order_id, user_id)
        if str(order_row.get("status") or "").lower() == "paid":
            payload = _build_portal_payment_response(conn, order_row)
            return _success_response(
                f"/portal/api/payments/orders/{order_id}/simulate-paid",
                payload,
                "order already paid",
            )
        provider = _normalize_portal_provider(str(order_row.get("provider") or "alipay"))
        callback_url = _backend_base_url() + f"/internal/payments/provider-callback/{provider}"

    callback_payload = {
        "order_id": order_id,
        "provider_order_id": f"mock-order-{order_id}",
        "provider_trade_no": f"mock-trade-{uuid4().hex[:24]}",
        "paid_amount_cents": int(order_row.get("amount_cents") or 0),
        "meta": {
            "source": "portal_mock_payment",
            "triggered_via": f"/portal/api/payments/orders/{order_id}/simulate-paid",
        },
    }
    headers = {
        INTERNAL_SERVICE_SECRET_HEADER_NAME: INTERNAL_SERVICE_SECRET,
        INTERNAL_SERVICE_NAME_HEADER_NAME: "portal-mock-payment",
        IDEMPOTENCY_KEY_HEADER_NAME: f"portal-mock:{order_id}:{uuid4().hex}",
    }
    try:
        response = http_requests.post(callback_url, headers=headers, json=callback_payload, timeout=12)
    except Exception as exc:  # pragma: no cover - network failure only
        raise HTTPException(status_code=502, detail=f"mock payment callback failed: {exc}") from exc

    try:
        response_json = response.json()
    except Exception:
        response_json = {"message": response.text.strip() or response.reason}
    if response.status_code != 200 or response_json.get("success") is not True:
        raise HTTPException(
            status_code=502,
            detail=response_json.get("detail") or response_json.get("message") or "mock payment callback failed",
        )

    with _postgres_conn() as conn:
        updated_order = _fetch_payment_order_for_user(conn, order_id, user_id)
        payload = _build_portal_payment_response(conn, updated_order)
    return _success_response(
        f"/portal/api/payments/orders/{order_id}/simulate-paid",
        payload,
        "portal mock payment applied",
    )
