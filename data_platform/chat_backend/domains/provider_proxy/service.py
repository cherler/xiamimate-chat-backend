"""Provider proxy domain — upstream service forwarding.

Covers: Dify workflow, Dify knowledge-base, Theme API, MiniMax (OpenAI-compat).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import requests as http_requests
from fastapi import HTTPException

from data_platform.llm_client import build_chat_completions_url, build_llm_provider, build_openai_compatible_config
from data_platform.chat_backend.domains.site_config import (
    _get_site_config_int_value,
    _get_site_config_value,
)
from data_platform.chat_backend.infra.postgres import _postgres_conn
from data_platform.chat_backend.infra.settings import (
    AGENT_OPENAI_TIMEOUT,
    ALLOWED_REPORT_PROFILES,
    REPORT_PROFILE_TO_API_KEY_ENV_VAR,
    REPORT_PROFILE_TO_BINDING,
    THEME_API_OPERATION_PATHS,
)


# ---------------------------------------------------------------------------
# Provider config helpers
# ---------------------------------------------------------------------------

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


def _normalize_report_profile(profile: str) -> str:
    normalized = str(profile or "standard").strip().lower() or "standard"
    if normalized not in ALLOWED_REPORT_PROFILES:
        raise HTTPException(status_code=400, detail=f"unsupported report profile: {profile}")
    return normalized


def _resolve_report_binding(profile: str) -> str:
    normalized = _normalize_report_profile(profile)
    return REPORT_PROFILE_TO_BINDING[normalized]


def _dify_report_api_key(profile: str) -> str:
    normalized = _normalize_report_profile(profile)
    env_var_name = REPORT_PROFILE_TO_API_KEY_ENV_VAR[normalized]
    api_key = (os.environ.get(env_var_name) or "").strip()
    if api_key:
        return api_key
    if normalized == "research":
        raise HTTPException(
            status_code=503,
            detail="report research is not available yet: DIFY_REPORT_RESEARCH_APP_API_KEY is not configured",
        )
    return _dify_workflow_api_key()


def _dify_web_search_app_id() -> str:
    app_id = (os.environ.get("DIFY_WEB_SEARCH_APP_ID") or "").strip()
    if not app_id:
        raise HTTPException(status_code=500, detail="DIFY_WEB_SEARCH_APP_ID is not configured")
    return app_id


def _dify_web_search_api_key() -> str:
    api_key = (os.environ.get("DIFY_WEB_SEARCH_APP_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="DIFY_WEB_SEARCH_APP_API_KEY is not configured")
    return api_key


def _tavily_base_url() -> str:
    return (os.environ.get("TAVILY_API_BASE_URL") or "https://api.tavily.com").rstrip("/")


def _tavily_api_key() -> str:
    api_key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="TAVILY_API_KEY is not configured")
    return api_key


def _tavily_timeout() -> int:
    return max(1, int(os.environ.get("TAVILY_REQUEST_TIMEOUT", "30")))


def _tavily_default_exclude_domains() -> list[str]:
    raw_value = os.environ.get(
        "TAVILY_DEFAULT_EXCLUDE_DOMAINS",
        "who13.com,wgntv.com,aol.com,yahoo.com,msn.com,newsweek.com,people.com",
    )
    return [item.strip().lower() for item in raw_value.split(",") if item.strip()]


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


def _dify_customer_help_dataset_id() -> str:
    dataset_id = (os.environ.get("DIFY_CUSTOMER_HELP_DATASET_ID") or "").strip()
    if not dataset_id:
        raise HTTPException(status_code=500, detail="DIFY_CUSTOMER_HELP_DATASET_ID is not configured")
    return dataset_id


def _dify_customer_help_dataset_api_key() -> str:
    return (os.environ.get("DIFY_CUSTOMER_HELP_DATASET_API_KEY") or "").strip() or _dify_dataset_api_key()


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


def _agent_openai_provider():
    provider = build_llm_provider("AGENT_OPENAI", provider_default="openai_compatible", enabled_default=True)
    if provider.provider_name != "openai_compatible":
        raise HTTPException(status_code=500, detail=f"AGENT_OPENAI provider mismatch: {provider.provider_name}")
    return provider


def _agent_anthropic_provider():
    provider = build_llm_provider("AGENT_ANTHROPIC", provider_default="anthropic_compatible", enabled_default=False)
    if provider.provider_name != "anthropic_compatible":
        raise HTTPException(status_code=500, detail=f"AGENT_ANTHROPIC provider mismatch: {provider.provider_name}")
    return provider


def _ima_base_url() -> str:
    return (os.environ.get("IMA_OPENAPI_BASE_URL") or "https://ima.qq.com").rstrip("/")


def _ima_client_id() -> str:
    client_id = (
        os.environ.get("IMA_OPENAPI_CLIENTID")
        or os.environ.get("IMA_CLIENT_ID")
        or ""
    ).strip()
    if not client_id:
        raise HTTPException(status_code=500, detail="IMA_OPENAPI_CLIENTID is not configured")
    return client_id


def _ima_api_key() -> str:
    api_key = (
        os.environ.get("IMA_OPENAPI_APIKEY")
        or os.environ.get("IMA_API_KEY")
        or ""
    ).strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="IMA_OPENAPI_APIKEY is not configured")
    return api_key


def _ima_timeout() -> int:
    return max(1, int(os.environ.get("IMA_OPENAPI_TIMEOUT", "60")))


def _parse_bool_text(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if not normalized:
        return default
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _compact_unique_strings(values: list[Any], *, limit: int | None = None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if limit is not None and len(result) >= limit:
            break
    return result


def _normalize_tavily_query_text(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^/(?:report|workflow|wf|agent|tool|web)\b", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^(?:quick|standard|deep|research)\b", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^(?:请|帮我|请帮我|麻烦帮我|我想看|想看|帮忙)", "", text).strip()
    text = re.sub(r"^(?:调研一下|分析一下|分析|调研|看看|评估一下|评估|判断一下|判断)", "", text).strip()
    return text.strip("：:，,。.!?！？；; ")


def _is_tavily_news_request(*, query: str, intent: str | None = None, topic: str | None = None, search_mode: str | None = None) -> bool:
    mode_lookup = str(search_mode or "").strip().lower()
    if mode_lookup in {"news", "current_events", "current-events", "hot_news", "hot-news"}:
        return True
    topic_lookup = str(topic or "").strip().lower()
    if topic_lookup == "news":
        return True
    lookup = f"{query}\n{intent or ''}".lower()
    chinese_news_tokens = [
        "新闻",
        "热点",
        "今日",
        "今天",
        "本周",
        "最新",
        "快讯",
        "公告",
        "政策",
        "规则更新",
        "平台动态",
        "卖家影响",
    ]
    english_news_tokens = [
        "news",
        "today",
        "latest",
        "breaking",
        "headline",
        "policy update",
        "seller update",
        "platform update",
        "current events",
    ]
    return any(token in query for token in chinese_news_tokens) or any(token in lookup for token in english_news_tokens)


def _is_cross_border_ecommerce_query(query: str) -> bool:
    lookup = query.lower()
    return any(
        token in query or token in lookup
        for token in [
            "跨境电商",
            "跨境卖家",
            "出海",
            "amazon",
            "亚马逊",
            "tiktok shop",
            "temu",
            "shein",
            "shopify",
            "cross-border ecommerce",
            "cross border ecommerce",
            "e-commerce sellers",
            "ecommerce sellers",
        ]
    )


def _tavily_requested_result_limit(query: str, requested_limit: int) -> int:
    text = str(query or "")
    match = re.search(r"top\s*(\d{1,2})", text, flags=re.IGNORECASE)
    if not match:
        match = re.search(r"前\s*(\d{1,2})\s*(?:条|个|则)?", text)
    if match:
        requested_limit = max(requested_limit, int(match.group(1)))
    return max(1, min(10, requested_limit))


def _build_tavily_news_query_variants(query: str, *, limit: int = 4) -> list[str]:
    normalized = _normalize_tavily_query_text(query)
    current_date = datetime.now().strftime("%Y-%m-%d")
    variants: list[str] = []
    if normalized:
        variants.append(normalized)

    if _is_cross_border_ecommerce_query(query):
        variants.extend(
            [
                f"{current_date} 跨境电商 今日 热点新闻 平台 政策 卖家 影响 Amazon TikTok Shop Temu SHEIN",
                "跨境电商 最新新闻 平台政策 卖家影响 Amazon TikTok Shop Temu SHEIN Shopify",
                "cross-border ecommerce latest news Amazon TikTok Shop Temu SHEIN seller policy updates",
                "Amazon Seller Central TikTok Shop Temu SHEIN ecommerce seller policy update latest news",
            ]
        )
    else:
        variants.extend(
            [
                f"{current_date} {normalized} 最新新闻 政策 影响",
                f"{normalized} latest news policy update",
                f"{normalized} today headlines",
            ]
        )
    return _compact_unique_strings(variants, limit=limit)


def _guess_product_query_for_tavily(query: str, product_query: str | None = None) -> str:
    explicit = _normalize_tavily_query_text(product_query)
    if explicit:
        return explicit

    text = _normalize_tavily_query_text(query)
    if not text:
        return ""
    patterns = [
        r"(?P<product>.+?)\s+在\s+(?:Amazon|亚马逊|TikTok|Temu|美国|英国|德国|日本)",
        r"(?P<product>.+?)\s+(?:Amazon|亚马逊|TikTok|Temu)\s*(?:美国|US|UK|DE|JP)?\s*(?:市场|平台)",
        r"(?P<product>[A-Za-z0-9][A-Za-z0-9\s\-/&]+?)\s+(?:market|opportunity|trend|amazon|temu|tiktok)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = match.group("product").strip(" ：:，,。.!?！？；;")
            if candidate:
                return candidate
    text = re.split(r"并输出|输出|并给出|，|。|；|\n", text, maxsplit=1)[0]
    text = re.sub(r"(?:在)?(?:Amazon|亚马逊|TikTok Shop|TikTok|Temu)(?:美国|US|UK|DE|JP|英国|德国|日本)?(?:市场|平台)?", "", text, flags=re.IGNORECASE)
    return text.strip(" ：:，,。.!?！？；;")


def _build_tavily_search_query(
    *,
    query: str,
    product_query: str | None = None,
    target_platform: str | None = None,
    target_market: str | None = None,
    intent: str | None = None,
    topic: str | None = None,
    search_mode: str | None = None,
) -> dict[str, Any]:
    normalized_intent = str(intent or "market opportunity").strip() or "market opportunity"
    if _is_tavily_news_request(query=query, intent=normalized_intent, topic=topic, search_mode=search_mode):
        query_variants = _build_tavily_news_query_variants(query)
        search_query = query_variants[0] if query_variants else _normalize_tavily_query_text(query)
        return {
            "query": search_query,
            "query_variants": query_variants or [search_query],
            "product_query": "",
            "target_platform": str(target_platform or "").strip(),
            "target_market": str(target_market or "").strip(),
            "intent": normalized_intent,
            "search_mode": "news",
        }

    product = _guess_product_query_for_tavily(query, product_query)
    platform = str(target_platform or "").strip()
    market = str(target_market or "").strip()

    inferred_platform = platform
    lookup = query.lower()
    if not inferred_platform:
        if "amazon" in lookup or "亚马逊" in query:
            inferred_platform = "Amazon"
        elif "temu" in lookup:
            inferred_platform = "Temu"
        elif "tiktok" in lookup or "抖音" in query:
            inferred_platform = "TikTok Shop"

    inferred_market = market
    if not inferred_market:
        if "美国" in query or " us" in f" {lookup} " or "usa" in lookup:
            inferred_market = "US"
        elif "英国" in query or " uk" in f" {lookup} ":
            inferred_market = "UK"
        elif "德国" in query or " de" in f" {lookup} ":
            inferred_market = "DE"
        elif "日本" in query or " jp" in f" {lookup} ":
            inferred_market = "JP"

    search_parts = [product or _normalize_tavily_query_text(query)]
    if inferred_platform:
        search_parts.append(inferred_platform)
    if inferred_market:
        search_parts.append(inferred_market)
    search_parts.extend([normalized_intent, "reviews", "price", "competition"])
    search_query = " ".join(part for part in search_parts if part).strip()
    return {
        "query": search_query,
        "query_variants": [search_query],
        "product_query": product,
        "target_platform": inferred_platform,
        "target_market": inferred_market,
        "intent": normalized_intent,
        "search_mode": "commerce",
    }


def _domain_from_url(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _score_tavily_result(item: dict[str, Any], *, product_query: str, target_platform: str) -> tuple[float, list[str]]:
    title = str(item.get("title") or "")
    content = str(item.get("content") or "")
    url = str(item.get("url") or "")
    domain = _domain_from_url(url)
    haystack = f"{title}\n{content}\n{url}".lower()
    score = float(item.get("score") or 0.0)
    reasons: list[str] = []

    product_tokens = [token.lower() for token in re.findall(r"[A-Za-z0-9]+", product_query or "") if len(token) >= 3]
    matched_tokens = [token for token in product_tokens if token in haystack]
    if product_tokens:
        token_ratio = len(set(matched_tokens)) / max(1, len(set(product_tokens)))
        score += token_ratio * 0.45
        if token_ratio >= 0.5:
            reasons.append("product_match")

    platform_lookup = (target_platform or "").lower()
    if platform_lookup and platform_lookup in haystack:
        score += 0.15
        reasons.append("platform_match")
    if any(keyword in haystack for keyword in ["best seller", "bestseller", "most wished", "amazon", "review", "price"]):
        score += 0.08
        reasons.append("commerce_context")
    if any(domain.endswith(suffix) for suffix in ["amazon.com", "junglescout.com", "helium10.com", "keepa.com", "statista.com"]):
        score += 0.12
        reasons.append("commerce_domain")
    if any(noise in haystack for noise in ["tornado", "shooting", "celebrity", "weather", "mother's day"]):
        score -= 0.3
        reasons.append("news_noise")
    return score, reasons


def _score_tavily_news_result(item: dict[str, Any], *, query: str) -> tuple[float, list[str]]:
    title = str(item.get("title") or "")
    content = str(item.get("content") or "")
    url = str(item.get("url") or "")
    domain = _domain_from_url(url)
    haystack = f"{title}\n{content}\n{url}".lower()
    raw_text = f"{title}\n{content}\n{url}"
    score = float(item.get("score") or 0.0)
    reasons: list[str] = []

    ecommerce_terms = ["跨境", "跨境电商", "卖家", "电商", "出海", "amazon", "亚马逊", "tiktok", "temu", "shein", "shopify", "ecommerce", "e-commerce"]
    platform_terms = ["amazon", "亚马逊", "seller central", "tiktok shop", "temu", "shein", "shopify", "walmart", "etsy", "lazada", "shopee"]
    news_terms = ["新闻", "热点", "最新", "今日", "今天", "公告", "政策", "规则", "动态", "发布", "更新", "news", "latest", "announced", "policy", "update", "regulation"]
    seller_impact_terms = ["卖家", "商家", "店铺", "佣金", "物流", "关税", "合规", "广告", "流量", "seller", "merchant", "tariff", "fee", "logistics", "compliance"]

    if any(term in raw_text or term in haystack for term in ecommerce_terms):
        score += 0.35
        reasons.append("ecommerce_context")
    if any(term in raw_text or term in haystack for term in platform_terms):
        score += 0.2
        reasons.append("platform_context")
    if any(term in raw_text or term in haystack for term in news_terms):
        score += 0.15
        reasons.append("news_context")
    if any(term in raw_text or term in haystack for term in seller_impact_terms):
        score += 0.12
        reasons.append("seller_impact_context")
    if item.get("published_date"):
        score += 0.08
        reasons.append("dated_result")

    trusted_domain_suffixes = [
        "cifnews.com",
        "ebrun.com",
        "sellercentral.amazon.com",
        "sell.amazon.com",
        "aboutamazon.com",
        "newsroom.tiktok.com",
        "seller-us.tiktok.com",
        "marketplacepulse.com",
        "practicalecommerce.com",
        "digitalcommerce360.com",
        "retaildive.com",
        "pymnts.com",
        "ecommercebytes.com",
        "channelx.world",
        "reuters.com",
        "cnbc.com",
    ]
    if any(domain.endswith(suffix) for suffix in trusted_domain_suffixes):
        score += 0.18
        reasons.append("trusted_news_domain")

    technical_noise_terms = ["github", "githubdaily", "代码", "开源", "repository", "developer", "python", "javascript"]
    if _is_cross_border_ecommerce_query(query) and any(term in raw_text.lower() for term in technical_noise_terms):
        score -= 0.7
        reasons.append("technical_noise")
    if any(noise in haystack for noise in ["coupon code", "promo code", "招聘", "job opening", "weather", "celebrity"]):
        score -= 0.25
        reasons.append("general_noise")
    return score, reasons


def _format_tavily_result_text(query: str, results: list[dict[str, Any]], dropped_count: int, *, search_mode: str = "commerce") -> str:
    if not results:
        return f"Tavily 搜索未得到可用于报告的高相关结果。原始查询: {query}。已过滤低相关或噪声结果 {dropped_count} 条。"
    if search_mode == "news":
        lines = [f"Tavily 新闻/热点搜索可用结果 {len(results)} 条；已过滤低相关或噪声结果 {dropped_count} 条。"]
    else:
        lines = [f"Tavily 搜索可用结果 {len(results)} 条；已过滤低相关或噪声结果 {dropped_count} 条。"]
    for index, item in enumerate(results, 1):
        title = item.get("title") or "未命名结果"
        domain = item.get("domain") or _domain_from_url(str(item.get("url") or "")) or "unknown"
        content = str(item.get("content") or "").strip().replace("\n", " ")
        snippet = content[:280] + ("..." if len(content) > 280 else "")
        published_date = item.get("published_date") or "unknown-date"
        if search_mode == "news":
            lines.append(f"{index}. {title} ({domain}, {published_date})\n   相关性: {item.get('relevance_score')}；摘要: {snippet}\n   URL: {item.get('url')}")
        else:
            lines.append(f"{index}. {title} ({domain})\n   相关性: {item.get('relevance_score')}；摘要: {snippet}\n   URL: {item.get('url')}")
    return "\n".join(lines)


def _normalize_tavily_time_filters(payload: dict[str, Any]) -> dict[str, Any]:
    time_filters: dict[str, Any] = {}
    time_range_aliases = {
        "d": "day",
        "w": "week",
        "m": "month",
        "y": "year",
    }
    time_range = str(payload.get("time_range") or "").strip().lower()
    time_range = time_range_aliases.get(time_range, time_range)
    if time_range in {"day", "week", "month", "year"}:
        time_filters["time_range"] = time_range

    days = payload.get("days")
    if days not in (None, ""):
        try:
            normalized_days = max(1, min(3650, int(days)))
            time_filters["days"] = normalized_days
        except (TypeError, ValueError):
            pass

    for field_name in ("start_date", "end_date"):
        value = str(payload.get(field_name) or "").strip()
        if value:
            time_filters[field_name] = value
    return time_filters


def _parse_ima_knowledge_bases_config(raw_value: str) -> list[dict[str, str]]:
    text = str(raw_value or "").strip()
    if not text:
        return []

    parsed_items: list[dict[str, str]] = []
    try:
        payload = json.loads(text)
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    kb_id = str(item.get("id") or item.get("kb_id") or "").strip()
                    kb_name = str(item.get("name") or item.get("kb_name") or "").strip()
                    if kb_id:
                        parsed_items.append({"id": kb_id, "name": kb_name, "cover_url": ""})
                elif isinstance(item, str):
                    kb_id = item.strip()
                    if kb_id:
                        parsed_items.append({"id": kb_id, "name": "", "cover_url": ""})
            return parsed_items
    except Exception:
        pass

    for line in text.replace(",", "\n").splitlines():
        entry = line.strip()
        if not entry:
            continue
        if "|" in entry:
            kb_id, kb_name = entry.split("|", 1)
        else:
            kb_id, kb_name = entry, ""
        kb_id = kb_id.strip()
        kb_name = kb_name.strip()
        if kb_id:
            parsed_items.append({"id": kb_id, "name": kb_name, "cover_url": ""})
    return parsed_items


def _load_ima_site_settings() -> dict[str, Any]:
    settings = {
        "default_knowledge_bases": [],
        "default_knowledge_base_query": str(os.environ.get("IMA_DEFAULT_KNOWLEDGE_BASE_QUERY") or "跨境电商").strip() or "跨境电商",
        "query_rewrite_enabled": _parse_bool_text(os.environ.get("IMA_QUERY_REWRITE_ENABLED"), default=True),
        "query_rewrite_max_terms": max(1, min(5, int(os.environ.get("IMA_QUERY_REWRITE_MAX_TERMS", "3") or "3"))),
    }
    try:
        with _postgres_conn() as conn:
            settings["default_knowledge_bases"] = _parse_ima_knowledge_bases_config(
                _get_site_config_value(conn, "ima_default_knowledge_bases_json", "[]")
            )
            settings["default_knowledge_base_query"] = (
                _get_site_config_value(
                    conn,
                    "ima_default_knowledge_base_query",
                    settings["default_knowledge_base_query"],
                ).strip()
                or settings["default_knowledge_base_query"]
            )
            settings["query_rewrite_enabled"] = _parse_bool_text(
                _get_site_config_value(
                    conn,
                    "ima_query_rewrite_enabled",
                    "true" if settings["query_rewrite_enabled"] else "false",
                ),
                default=settings["query_rewrite_enabled"],
            )
            settings["query_rewrite_max_terms"] = _get_site_config_int_value(
                conn,
                "ima_query_rewrite_max_terms",
                settings["query_rewrite_max_terms"],
                minimum=1,
                maximum=5,
            )
    except Exception:
        return settings
    return settings


def _rewrite_ima_queries(
    query: str,
    *,
    knowledge_base_query: str,
    rewrite_enabled: bool,
    max_terms: int,
) -> dict[str, Any]:
    normalized_query = str(query or "").strip()
    normalized_kb_query = str(knowledge_base_query or "").strip()
    fallback = {
        "enabled": rewrite_enabled,
        "used": False,
        "knowledge_base_query": normalized_kb_query,
        "search_terms": [normalized_query] if normalized_query else [],
        "error": "",
        "provider": "",
    }
    if not normalized_query or not rewrite_enabled:
        return fallback

    try:
        provider = build_llm_provider("AGENT_OPENAI", enabled_default=True)
        payload = provider.json(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是跨境电商知识库检索词重写器。"
                        "请输出 JSON，对当前问题生成更适合知识库召回的短检索词。"
                        "要求：1. search_terms 返回 1 到 3 个短词组；"
                        "2. knowledge_base_query 返回 1 个更宽泛的知识库定位词；"
                        "3. 保留原问题语义，不要发散。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "query": normalized_query,
                            "knowledge_base_query": normalized_kb_query,
                            "max_terms": max_terms,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.2,
        )
        search_terms = _compact_unique_strings(
            list(payload.get("search_terms") or payload.get("queries") or []),
            limit=max_terms,
        )
        if normalized_query and normalized_query not in search_terms:
            search_terms.insert(0, normalized_query)
        search_terms = _compact_unique_strings(search_terms, limit=max_terms)
        rewritten_kb_query = str(payload.get("knowledge_base_query") or normalized_kb_query).strip()
        return {
            "enabled": True,
            "used": True,
            "knowledge_base_query": rewritten_kb_query or normalized_kb_query,
            "search_terms": search_terms or ([normalized_query] if normalized_query else []),
            "error": "",
            "provider": provider.provider_name,
        }
    except Exception as exc:
        fallback["error"] = str(exc)
        return fallback


# ---------------------------------------------------------------------------
# Error detail helper
# ---------------------------------------------------------------------------

def _request_error_detail(response: http_requests.Response | None, exc: Exception) -> str:
    if response is not None:
        try:
            payload = response.json()
            return str(payload.get("message") or payload)
        except ValueError:
            if response.text:
                return response.text
    return str(exc)


def _ima_response_error_detail(response: http_requests.Response | None, exc: Exception) -> str:
    if response is not None:
        try:
            payload = response.json()
            return str(payload.get("msg") or payload.get("message") or payload)
        except ValueError:
            if response.text:
                return response.text
    return str(exc)


def _proxy_ima_post(api_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = None
    try:
        response = http_requests.post(
            f"{_ima_base_url()}/{api_path.lstrip('/')}",
            json=payload,
            headers={
                "ima-openapi-clientid": _ima_client_id(),
                "ima-openapi-apikey": _ima_api_key(),
                "ima-openapi-ctx": "skill_version=chat-backend-provider-v1",
                "Content-Type": "application/json",
            },
            timeout=(10, _ima_timeout()),
        )
        response.raise_for_status()
        response_json = response.json()
    except http_requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=("IMA API 请求失败:\n" + _ima_response_error_detail(response, exc))[:4000])
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"IMA API 返回了无法解析的 JSON: {str(exc)}")

    if not isinstance(response_json, dict):
        raise HTTPException(status_code=502, detail="IMA API 返回结构不是对象")

    if int(response_json.get("code", 0) or 0) != 0:
        raise HTTPException(status_code=502, detail=("IMA API 业务错误:\n" + str(response_json.get("msg") or response_json))[:4000])

    data = response_json.get("data")
    return data if isinstance(data, dict) else {}


def _normalize_ima_knowledge_base_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or item.get("kb_id") or "").strip(),
        "name": str(item.get("name") or item.get("kb_name") or "").strip(),
        "cover_url": str(item.get("cover_url") or "").strip(),
    }


def _normalize_ima_knowledge_item(item: dict[str, Any], knowledge_base_id: str, knowledge_base_name: str) -> dict[str, Any]:
    return {
        "knowledge_base_id": knowledge_base_id,
        "knowledge_base_name": knowledge_base_name,
        "media_id": str(item.get("media_id") or "").strip(),
        "title": str(item.get("title") or "").strip(),
        "parent_folder_id": str(item.get("parent_folder_id") or "").strip(),
        "highlight_content": str(item.get("highlight_content") or "").strip(),
    }


def _proxy_ima_search_knowledge_bases(query: str, cursor: str = "", limit: int = 10) -> dict[str, Any]:
    data = _proxy_ima_post(
        "openapi/wiki/v1/search_knowledge_base",
        {
            "query": str(query or ""),
            "cursor": str(cursor or ""),
            "limit": int(limit),
        },
    )
    knowledge_bases = [
        _normalize_ima_knowledge_base_item(item)
        for item in (data.get("info_list") or [])
        if isinstance(item, dict)
    ]
    return {
        "query": str(query or ""),
        "cursor": str(cursor or ""),
        "limit": int(limit),
        "knowledge_bases": [item for item in knowledge_bases if item.get("id")],
        "next_cursor": str(data.get("next_cursor") or ""),
        "is_end": bool(data.get("is_end")),
    }


def _proxy_ima_search_knowledge(query: str, knowledge_base_id: str, cursor: str = "") -> dict[str, Any]:
    normalized_kb_id = str(knowledge_base_id or "").strip()
    if not normalized_kb_id:
        raise HTTPException(status_code=400, detail="knowledge_base_id is required")

    data = _proxy_ima_post(
        "openapi/wiki/v1/search_knowledge",
        {
            "query": str(query or ""),
            "cursor": str(cursor or ""),
            "knowledge_base_id": normalized_kb_id,
        },
    )
    return {
        "query": str(query or ""),
        "knowledge_base_id": normalized_kb_id,
        "matches": [item for item in (data.get("info_list") or []) if isinstance(item, dict)],
        "next_cursor": str(data.get("next_cursor") or ""),
        "is_end": bool(data.get("is_end")),
    }


def _proxy_ima_get_media_info(media_id: str) -> dict[str, Any]:
    normalized_media_id = str(media_id or "").strip()
    if not normalized_media_id:
        raise HTTPException(status_code=400, detail="media_id is required")
    data = _proxy_ima_post(
        "openapi/wiki/v1/get_media_info",
        {"media_id": normalized_media_id},
    )
    return {
        "media_id": normalized_media_id,
        "media_info": data,
    }


def _format_ima_retrieve_result(query: str, matches: list[dict[str, Any]], errors: list[str]) -> str:
    if not matches:
        result = f'未在 IMA 知识库中找到与 "{query}" 相关的资料。'
        if errors:
            result += "\n\n⚠️ 部分知识库检索失败: %s" % "; ".join(errors)
        return result

    snippets: list[str] = []
    for index, item in enumerate(matches, 1):
        knowledge_base_label = item.get("knowledge_base_name") or item.get("knowledge_base_id") or "未命名知识库"
        title = item.get("title") or f"资料 {index}"
        highlight = item.get("highlight_content") or "未返回摘要片段。"
        media_id = item.get("media_id") or ""
        snippets.append(
            "【%s】%s\n知识库: %s\nmedia_id: %s\n摘要: %s" % (
                index,
                title,
                knowledge_base_label,
                media_id or "-",
                highlight,
            )
        )

    result = "IMA 知识库检索到 %d 条相关资料:\n\n%s" % (len(matches), "\n\n---\n\n".join(snippets))
    if errors:
        result += "\n\n⚠️ 部分知识库检索失败: %s" % "; ".join(errors)
    return result


def _proxy_ima_retrieve(
    query: str,
    top_k: int,
    knowledge_base_ids: list[str] | None = None,
    knowledge_base_query: str | None = None,
    knowledge_base_limit: int = 3,
) -> dict[str, Any]:
    site_settings = _load_ima_site_settings()
    configured_knowledge_bases = site_settings.get("default_knowledge_bases") or []
    configured_names_by_id = {
        item.get("id") or "": item.get("name") or ""
        for item in configured_knowledge_bases
        if item.get("id")
    }
    normalized_ids = [str(value or "").strip() for value in (knowledge_base_ids or []) if str(value or "").strip()]
    selected_knowledge_bases: list[dict[str, Any]] = []
    resolved_knowledge_base_query = str(knowledge_base_query or "").strip()

    rewrite_result = _rewrite_ima_queries(
        query=query,
        knowledge_base_query=resolved_knowledge_base_query or str(site_settings.get("default_knowledge_base_query") or "").strip(),
        rewrite_enabled=bool(site_settings.get("query_rewrite_enabled")),
        max_terms=int(site_settings.get("query_rewrite_max_terms") or 3),
    )
    search_terms = _compact_unique_strings(rewrite_result.get("search_terms") or [query], limit=5)
    if not search_terms and str(query or "").strip():
        search_terms = [str(query).strip()]

    if normalized_ids:
        selected_knowledge_bases = [
            {"id": knowledge_base_id, "name": configured_names_by_id.get(knowledge_base_id, ""), "cover_url": ""}
            for knowledge_base_id in normalized_ids
        ]
    else:
        if resolved_knowledge_base_query:
            kb_lookup_query = resolved_knowledge_base_query
        elif configured_knowledge_bases:
            selected_knowledge_bases = configured_knowledge_bases
            normalized_ids = [item.get("id") or "" for item in selected_knowledge_bases if item.get("id")]
            kb_lookup_query = str(site_settings.get("default_knowledge_base_query") or "").strip()
        else:
            kb_lookup_query = str(
                rewrite_result.get("knowledge_base_query")
                or site_settings.get("default_knowledge_base_query")
                or os.environ.get("IMA_DEFAULT_KNOWLEDGE_BASE_QUERY")
                or query
                or ""
            ).strip()

        if not normalized_ids:
            kb_search_result = _proxy_ima_search_knowledge_bases(
                query=kb_lookup_query,
                cursor="",
                limit=knowledge_base_limit,
            )
            selected_knowledge_bases = kb_search_result.get("knowledge_bases") or []
            normalized_ids = [item.get("id") or "" for item in selected_knowledge_bases if item.get("id")]
        resolved_knowledge_base_query = kb_lookup_query

    if not normalized_ids:
        return {
            "query": query,
            "knowledge_base_query": resolved_knowledge_base_query,
            "knowledge_bases": [],
            "matches": [],
            "result": f'未找到可用于检索的 IMA 知识库。',
            "errors": [],
            "query_rewrite": rewrite_result,
        }

    knowledge_base_name_by_id = {
        item.get("id") or "": item.get("name") or ""
        for item in selected_knowledge_bases
        if item.get("id")
    }
    matched_items: list[dict[str, Any]] = []
    seen_match_keys: set[tuple[str, str, str]] = set()
    errors: list[str] = []

    for knowledge_base_id in normalized_ids:
        for search_query in search_terms:
            try:
                search_result = _proxy_ima_search_knowledge(query=search_query, knowledge_base_id=knowledge_base_id, cursor="")
                knowledge_base_name = knowledge_base_name_by_id.get(knowledge_base_id, "")
                for item in search_result.get("matches") or []:
                    if not isinstance(item, dict):
                        continue
                    normalized_item = _normalize_ima_knowledge_item(item, knowledge_base_id, knowledge_base_name)
                    normalized_item["matched_query"] = search_query
                    dedupe_key = (
                        normalized_item.get("knowledge_base_id") or "",
                        normalized_item.get("media_id") or normalized_item.get("title") or "",
                        normalized_item.get("highlight_content") or "",
                    )
                    if dedupe_key in seen_match_keys:
                        continue
                    seen_match_keys.add(dedupe_key)
                    matched_items.append(normalized_item)
            except HTTPException as exc:
                errors.append(f"{knowledge_base_id}/{search_query}: {str(exc.detail)}")

    top_matches = matched_items[:top_k]
    if not top_matches and errors:
        raise HTTPException(status_code=502, detail=("IMA 知识库检索失败:\n" + "\n".join(errors))[:4000])

    return {
        "query": query,
        "knowledge_base_query": resolved_knowledge_base_query,
        "knowledge_bases": selected_knowledge_bases,
        "matches": top_matches,
        "result": _format_ima_retrieve_result(query=query, matches=top_matches, errors=errors),
        "errors": errors,
        "query_rewrite": rewrite_result,
    }


# ---------------------------------------------------------------------------
# Dify proxies
# ---------------------------------------------------------------------------

def _proxy_dify_chat_blocking(query: str, user: str, api_key: str, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    response = None
    try:
        response = http_requests.post(
            f"{_dify_base_url()}/v1/chat-messages",
            json={
                "inputs": inputs or {},
                "query": query,
                "response_mode": "blocking",
                "user": user,
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Host": "localhost",
            },
            timeout=(10, _dify_timeout()),
        )
        response.raise_for_status()
        return response.json()
    except http_requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=_request_error_detail(response, exc)[:4000])
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"invalid Dify JSON response: {str(exc)}")


def _proxy_dify_chat_stream(query: str, user: str, api_key: str, inputs: dict[str, Any] | None = None) -> http_requests.Response:
    response = None
    try:
        response = http_requests.post(
            f"{_dify_base_url()}/v1/chat-messages",
            json={
                "inputs": inputs or {},
                "query": query,
                "response_mode": "streaming",
                "user": user,
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Host": "localhost",
            },
            timeout=(10, _dify_timeout()),
            stream=True,
        )
        response.raise_for_status()
        return response
    except http_requests.RequestException as exc:
        if response is not None:
            response.close()
        raise HTTPException(status_code=502, detail=_request_error_detail(response, exc)[:4000])


def _proxy_dify_workflow_blocking(query: str, user: str) -> dict[str, Any]:
    return _proxy_report_blocking(query=query, user=user, profile="standard")


def _proxy_dify_workflow_stream(query: str, user: str) -> http_requests.Response:
    return _proxy_report_stream(query=query, user=user, profile="standard")


def _proxy_report_blocking(query: str, user: str, profile: str) -> dict[str, Any]:
    normalized = _normalize_report_profile(profile)
    return _proxy_dify_chat_blocking(
        query=query,
        user=user,
        api_key=_dify_report_api_key(normalized),
        inputs={
            "report_profile": normalized,
            "report_binding": _resolve_report_binding(normalized),
        },
    )


def _proxy_report_stream(query: str, user: str, profile: str) -> http_requests.Response:
    normalized = _normalize_report_profile(profile)
    return _proxy_dify_chat_stream(
        query=query,
        user=user,
        api_key=_dify_report_api_key(normalized),
        inputs={
            "report_profile": normalized,
            "report_binding": _resolve_report_binding(normalized),
        },
    )


def _proxy_dify_web_search_blocking(query: str, user: str) -> dict[str, Any]:
    _dify_web_search_app_id()
    return _proxy_dify_chat_blocking(query=query, user=user, api_key=_dify_web_search_api_key())


def _proxy_dify_web_search_stream(query: str, user: str) -> http_requests.Response:
    _dify_web_search_app_id()
    return _proxy_dify_chat_stream(query=query, user=user, api_key=_dify_web_search_api_key())


def _proxy_tavily_search(payload: dict[str, Any]) -> dict[str, Any]:
    raw_query = str(payload.get("query") or "").strip()
    if not raw_query:
        raise HTTPException(status_code=400, detail="query is required")

    requested_topic = str(payload.get("topic") or "general").strip().lower()
    query_plan = _build_tavily_search_query(
        query=raw_query,
        product_query=payload.get("product_query"),
        target_platform=payload.get("target_platform"),
        target_market=payload.get("target_market"),
        intent=payload.get("intent"),
        topic=requested_topic,
        search_mode=payload.get("search_mode"),
    )
    search_mode = str(query_plan.get("search_mode") or "commerce")
    include_domains = _compact_unique_strings(list(payload.get("include_domains") or []), limit=20)
    requested_exclude_domains = _compact_unique_strings(list(payload.get("exclude_domains") or []), limit=50)
    exclude_domains = _compact_unique_strings(
        requested_exclude_domains + _tavily_default_exclude_domains(),
        limit=80,
    )
    max_results = _tavily_requested_result_limit(raw_query, max(1, min(10, int(payload.get("max_results") or 5))))
    raw_limit = max(max_results, min(20, max_results * 3))
    search_depth = str(payload.get("search_depth") or "basic").strip().lower()
    if search_depth not in {"basic", "advanced"}:
        search_depth = "basic"
    topic = requested_topic
    if topic not in {"general", "news", "finance"}:
        topic = "general"
    if search_mode == "news" and topic == "general":
        topic = "news"
    time_filters = _normalize_tavily_time_filters(payload)

    request_payload: dict[str, Any] = {
        "query": query_plan["query"],
        "search_depth": search_depth,
        "topic": topic,
        "max_results": raw_limit,
        "include_answer": bool(payload.get("include_answer", False)),
        "include_raw_content": bool(payload.get("include_raw_content", False)),
        "include_images": bool(payload.get("include_images", False)),
    }
    request_payload.update(time_filters)
    if include_domains:
        request_payload["include_domains"] = include_domains
    if exclude_domains:
        request_payload["exclude_domains"] = exclude_domains

    response_records: list[dict[str, Any]] = []
    request_errors: list[str] = []
    api_key = _tavily_api_key()
    query_variants = _compact_unique_strings(list(query_plan.get("query_variants") or [query_plan["query"]]), limit=4 if search_mode == "news" else 1)
    for search_query in query_variants:
        variant_payload = {**request_payload, "query": search_query}
        response = None
        try:
            response = http_requests.post(
                f"{_tavily_base_url()}/search",
                json={**variant_payload, "api_key": api_key},
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=(10, _tavily_timeout()),
            )
            response.raise_for_status()
            response_records.append({"query": search_query, "response_json": response.json()})
        except http_requests.RequestException as exc:
            request_errors.append(("Tavily API 请求失败:\n" + _request_error_detail(response, exc))[:1000])
        except ValueError as exc:
            request_errors.append(f"Tavily API 返回了无法解析的 JSON: {str(exc)}")

    if not response_records:
        detail = request_errors[0] if request_errors else "Tavily API 请求失败"
        raise HTTPException(status_code=502, detail=detail[:4000])

    raw_results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    answers: list[str] = []
    request_ids: list[Any] = []
    response_times: list[Any] = []
    for record in response_records:
        response_json = record["response_json"]
        if response_json.get("answer"):
            answers.append(str(response_json.get("answer")))
        if response_json.get("request_id"):
            request_ids.append(response_json.get("request_id"))
        if response_json.get("response_time") is not None:
            response_times.append(response_json.get("response_time"))
        for item in response_json.get("results") or []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            dedupe_key = url or f"{item.get('title')}::{item.get('content')}"
            if dedupe_key in seen_urls:
                continue
            seen_urls.add(dedupe_key)
            enriched_item = dict(item)
            enriched_item["source_query"] = record["query"]
            raw_results.append(enriched_item)
    normalized_results: list[dict[str, Any]] = []
    dropped_results: list[dict[str, Any]] = []
    minimum_relevance = float(payload.get("minimum_relevance") or (0.25 if search_mode == "news" else 0.35))

    for item in raw_results:
        url = str(item.get("url") or "").strip()
        domain = _domain_from_url(url)
        if search_mode == "news":
            relevance_score, reasons = _score_tavily_news_result(item, query=raw_query)
        else:
            relevance_score, reasons = _score_tavily_result(
                item,
                product_query=str(query_plan.get("product_query") or ""),
                target_platform=str(query_plan.get("target_platform") or ""),
            )
        normalized_item = {
            "title": str(item.get("title") or "").strip(),
            "url": url,
            "domain": domain,
            "content": str(item.get("content") or "").strip(),
            "published_date": item.get("published_date"),
            "source_query": item.get("source_query"),
            "tavily_score": item.get("score"),
            "relevance_score": round(relevance_score, 4),
            "relevance_reasons": reasons,
        }
        if relevance_score >= minimum_relevance:
            normalized_results.append(normalized_item)
        else:
            dropped_results.append(normalized_item)

    normalized_results.sort(key=lambda item: float(item.get("relevance_score") or 0.0), reverse=True)
    selected_results = normalized_results[:max_results]
    dropped_count = len(raw_results) - len(selected_results)

    return {
        "provider": "tavily",
        "capability": "web_search",
        "query": raw_query,
        "query_plan": query_plan,
        "request": {
            **request_payload,
            "query_variants": query_variants,
            "api_key": "***",
        },
        "answer": "\n\n".join(answers) if answers else None,
        "results": selected_results,
        "dropped_results": dropped_results[:10],
        "result_text": _format_tavily_result_text(query_plan["query"], selected_results, dropped_count, search_mode=search_mode),
        "source_meta": {
            "request_id": request_ids[0] if len(request_ids) == 1 else request_ids,
            "response_time": response_times[0] if len(response_times) == 1 else response_times,
            "raw_result_count": len(raw_results),
            "selected_result_count": len(selected_results),
            "dropped_result_count": dropped_count,
            "search_mode": search_mode,
            "query_variant_count": len(query_variants),
            "search_depth": search_depth,
            "topic": topic,
            "time_filters": time_filters,
            "partial_error_count": len(request_errors),
        },
        "degradation": {
            "status": "ok" if selected_results and not request_errors else ("partial" if selected_results else "no_relevant_results"),
            "reason": "" if selected_results and not request_errors else ("Some Tavily query variants failed." if selected_results else "Tavily returned results, but none passed local relevance filtering."),
        },
    }


def _proxy_knowledge_retrieve(query: str, top_k: int) -> str:
    all_records: list[dict[str, Any]] = []
    errors: list[str] = []
    for dataset_id in _dify_dataset_ids():
        response = None
        try:
            response = http_requests.post(
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
        except http_requests.RequestException as exc:
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


def _proxy_customer_help_retrieve(query: str, top_k: int) -> str:
    dataset_id = _dify_customer_help_dataset_id()
    response = None
    try:
        response = http_requests.post(
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
                "Authorization": f"Bearer {_dify_customer_help_dataset_api_key()}",
                "Content-Type": "application/json",
                "Host": "localhost",
            },
            timeout=_dify_timeout(),
        )
        response.raise_for_status()
        data = response.json()
    except http_requests.RequestException as exc:
        detail = _request_error_detail(response, exc)[:500]
        raise HTTPException(status_code=502, detail=f"客服知识库检索失败: {detail}")
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"客服知识库返回了无法解析的 JSON: {str(exc)[:500]}")

    records = data.get("records") or []
    if not records:
        return f'未找到与 "{query}" 相关的客服知识库内容。'

    records.sort(key=lambda item: item.get("score", 0), reverse=True)
    snippets: list[str] = []
    for index, record in enumerate(records[:top_k], 1):
        segment = record.get("segment") or record
        content = str(segment.get("content") or "").strip()
        if not content:
            continue
        doc = segment.get("document") or {}
        title = doc.get("name") or record.get("document_name") or "客服知识库"
        score = record.get("score", 0)
        snippets.append(f"【{index}】{title} (相关度: {score:.2f})\n{content}")

    if not snippets:
        return f'未找到与 "{query}" 相关的客服知识库内容。'

    return "找到 %d 条客服知识:\n\n%s" % (len(snippets), "\n\n---\n\n".join(snippets))


# ---------------------------------------------------------------------------
# OpenAI-compatible / Anthropic-compatible LLM proxy
# ---------------------------------------------------------------------------

def _proxy_openai_chat_completion(payload: dict[str, Any]) -> dict[str, Any]:
    provider = _agent_openai_provider()
    extra_body = {
        key: value
        for key, value in dict(payload or {}).items()
        if key not in {"messages", "temperature", "response_format", "model"}
    }
    try:
        return provider.chat(
            messages=list(payload.get("messages") or []),
            temperature=float(payload.get("temperature") or 0),
            response_format=payload.get("response_format") if isinstance(payload.get("response_format"), dict) else None,
            extra_body=extra_body or None,
        )
    except http_requests.RequestException as exc:
        response = getattr(exc, "response", None)
        raise HTTPException(status_code=502, detail=_request_error_detail(response, exc)[:4000])
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:4000])


def _proxy_openai_chat_completion_stream(payload: dict[str, Any]) -> http_requests.Response:
    config = build_openai_compatible_config("AGENT_OPENAI", enabled_default=True)
    if not config.enabled:
        raise HTTPException(status_code=500, detail="AGENT_OPENAI is not enabled")
    if not config.configured:
        raise HTTPException(status_code=500, detail="AGENT_OPENAI requires BASE_URL and MODEL")

    stream_payload = dict(payload or {})
    stream_payload["model"] = config.model
    stream_payload["stream"] = True

    response = None
    try:
        response = http_requests.post(
            build_chat_completions_url(config.base_url),
            json=stream_payload,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=(10, config.timeout_seconds),
            stream=True,
        )
        response.raise_for_status()
        return response
    except http_requests.RequestException as exc:
        if response is not None:
            response.close()
        raise HTTPException(status_code=502, detail=_request_error_detail(response, exc)[:4000])


def _proxy_anthropic_message(payload: dict[str, Any]) -> dict[str, Any]:
    provider = _agent_anthropic_provider()
    extra_body = {
        key: value
        for key, value in dict(payload or {}).items()
        if key not in {"messages", "temperature", "response_format", "model", "stream"}
    }
    try:
        return provider.chat(
            messages=list(payload.get("messages") or []),
            temperature=float(payload.get("temperature") or 0),
            response_format=payload.get("response_format") if isinstance(payload.get("response_format"), dict) else None,
            extra_body=extra_body or None,
        )
    except http_requests.RequestException as exc:
        response = getattr(exc, "response", None)
        raise HTTPException(status_code=502, detail=_request_error_detail(response, exc)[:4000])
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:4000])


# ---------------------------------------------------------------------------
# Theme API proxy
# ---------------------------------------------------------------------------

def _format_theme_api_tool_result(operation: str, payload: dict[str, Any]) -> str:
    if operation != "opportunity_discovery":
        return json.dumps(payload, ensure_ascii=False, indent=2)

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return json.dumps(payload, ensure_ascii=False, indent=2)

    llm_presentation = data.get("llm_presentation") if isinstance(data.get("llm_presentation"), dict) else {}
    compact = {
        "success": payload.get("success", True),
        "operation": operation,
        "instruction": "将 opportunity_cards_text 作为机会发现的工具证据块展示，保留表格、字段解释和工具返回数值；可自行组织摘要和解读，但不要改写成平铺列表。opportunities_for_llm 包含可继续分析的结构化机会入口。",
        "opportunity_count": data.get("opportunity_count"),
        "opportunity_cards_text": data.get("opportunity_cards_text") or llm_presentation.get("opportunity_cards_text"),
        "opportunities_for_llm": data.get("opportunities_for_llm") or llm_presentation.get("opportunities_for_llm"),
        "metric_definitions": data.get("metric_definitions"),
        "tool_contract": data.get("tool_contract"),
        "evidence_contract": data.get("evidence_contract"),
        "diagnostics": data.get("diagnostics"),
        "notes": data.get("notes"),
        "meta": payload.get("meta"),
    }
    return json.dumps(compact, ensure_ascii=False, indent=2)

def _proxy_theme_api(operation: str, payload: dict[str, Any]) -> str:
    path = THEME_API_OPERATION_PATHS.get(operation)
    if path is None:
        raise HTTPException(status_code=404, detail=f"unsupported theme_api operation: {operation}")
    response = None
    try:
        response = http_requests.post(
            f"{_theme_api_base_url()}{path}",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": _theme_api_key(),
            },
            timeout=_theme_api_timeout(),
        )
        response.raise_for_status()
        return _format_theme_api_tool_result(operation, response.json())
    except http_requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=("theme_api 请求失败:\n" + _request_error_detail(response, exc))[:4000])
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"theme_api 返回了无法解析的 JSON: {str(exc)}")


# ---------------------------------------------------------------------------
# Deprecated MiniMax OpenAI-compatible proxy.
# MiniMax-M2.7 should use _proxy_anthropic_message so native tool_use/tool_result
# conversion stays aligned with the Anthropic-compatible protocol.
# ---------------------------------------------------------------------------

def _proxy_minimax_chat_completion(payload: dict[str, Any]) -> dict[str, Any]:
    response = None
    try:
        response = http_requests.post(
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
    except http_requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=_request_error_detail(response, exc)[:4000])
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"invalid OpenAI-compatible JSON response: {str(exc)}")


def _proxy_minimax_chat_completion_stream(payload: dict[str, Any]) -> http_requests.Response:
    response = None
    try:
        response = http_requests.post(
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
    except http_requests.RequestException as exc:
        if response is not None:
            response.close()
        raise HTTPException(status_code=502, detail=_request_error_detail(response, exc)[:4000])
