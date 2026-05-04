"""TikTok Shop opportunity native-tool orchestration."""
from __future__ import annotations

import time
from typing import Any

from data_platform.chat_backend.domains.tiktok_shop_opportunity.normalizer import (
    normalize_hot_products,
    normalize_keywords,
    normalize_product_detail,
    normalize_search_products,
    normalize_trending_posts,
)
from data_platform.chat_backend.domains.tiktok_shop_opportunity.repository import record_tiktok_realtime_query
from data_platform.chat_backend.domains.tiktok_shop_opportunity.scoring import build_result_text, score_opportunity
from data_platform.chat_backend.domains.tiktok_shop_opportunity.tikhub_client import TikHubCallResult, TikHubClient, load_tikhub_config
from data_platform.chat_backend.infra.postgres import _postgres_conn


P0_HOT_PRODUCTS = "/api/v1/tiktok/shop/web/fetch_hot_selling_products_list"
P0_SEARCH_SUGGESTIONS = "/api/v1/tiktok/shop/web/fetch_search_word_suggestion_v2"
P0_SEARCH_PRODUCTS = "/api/v1/tiktok/shop/web/fetch_search_products_list_v3"
P0_PRODUCT_DETAIL = "/api/v1/tiktok/shop/web/fetch_product_detail"
P1_TRENDING_POST = "/api/v1/tiktok/web/fetch_trending_post"
P1_TRENDING_SEARCHWORDS = "/api/v1/tiktok/web/fetch_trending_searchwords"
P2_KEYWORD_INSIGHTS = "/api/v1/tiktok/ads/get_keyword_insights"
P2_TOP_PRODUCTS = "/api/v1/tiktok/ads/get_top_products"


def _call_to_dict(result: TikHubCallResult) -> dict[str, Any]:
    return {
        "endpoint": result.endpoint,
        "params": result.params,
        "ok": result.ok,
        "status_code": result.status_code,
        "latency_ms": result.latency_ms,
        "error": result.error,
    }


def _result_payload(result: TikHubCallResult) -> dict[str, Any]:
    return result.data if result.ok and isinstance(result.data, dict) else {}


def _safe_status(results: list[TikHubCallResult]) -> str:
    if not results:
        return "failed"
    ok_count = sum(1 for result in results if result.ok)
    if ok_count == len(results):
        return "ok"
    if ok_count > 0:
        if any("timed out" in str(result.error).lower() or "timeout" in str(result.error).lower() for result in results if result.error):
            return "timeout"
        return "partial"
    if any("timed out" in str(result.error).lower() or "timeout" in str(result.error).lower() for result in results if result.error):
        return "timeout"
    return "failed"


def _top_product_ids(products: list[dict[str, Any]], limit: int) -> list[str]:
    ids: list[str] = []
    for product in products:
        product_id = str(product.get("product_id") or "").strip()
        if product_id and product_id not in ids:
            ids.append(product_id)
        if len(ids) >= limit:
            break
    return ids


def run_tiktok_opportunity(payload: dict[str, Any]) -> dict[str, Any]:
    started_at = time.monotonic()
    config = load_tikhub_config()
    query = str(payload.get("query") or "").strip()
    target_market = str(payload.get("target_market") or config.target_region).strip().upper() or config.target_region
    keywords = [str(item).strip() for item in payload.get("keywords") or [] if str(item).strip()]
    query_terms = [query] + [keyword for keyword in keywords if keyword != query]
    limit = min(int(payload.get("limit") or config.topn), config.topn)
    request_payload = {"query": query, "target_market": target_market, "keywords": keywords, "limit": limit}

    if not config.enabled:
        degradation = {"status": "disabled", "reason": "TikTok opportunity provider is disabled"}
        scored = score_opportunity(
            query_terms=query_terms,
            expanded_keywords=[],
            trend_keywords=[],
            hot_products=[],
            search_products=[],
            product_details=[],
            trending_posts=[],
        )
        result_text = build_result_text(query, target_market, scored, degradation)
        return _build_response(config.provider, request_payload, [], {}, scored, result_text, degradation, started_at, None)

    if config.provider != "tikhub":
        degradation = {"status": "failed", "reason": f"unsupported TikTok provider: {config.provider}"}
        scored = score_opportunity(
            query_terms=query_terms,
            expanded_keywords=[],
            trend_keywords=[],
            hot_products=[],
            search_products=[],
            product_details=[],
            trending_posts=[],
        )
        result_text = build_result_text(query, target_market, scored, degradation)
        return _build_response(config.provider, request_payload, [], {}, scored, result_text, degradation, started_at, None)

    if not config.api_key:
        degradation = {"status": "missing_credentials", "reason": "TIKTOK_API_KEY is not configured"}
        scored = score_opportunity(
            query_terms=query_terms,
            expanded_keywords=[],
            trend_keywords=[],
            hot_products=[],
            search_products=[],
            product_details=[],
            trending_posts=[],
        )
        result_text = build_result_text(query, target_market, scored, degradation)
        return _build_response(config.provider, request_payload, [], {}, scored, result_text, degradation, started_at, None)

    client = TikHubClient(config=config)
    results: list[TikHubCallResult] = []
    results.append(client.get(P0_HOT_PRODUCTS, {"region": target_market, "country": target_market, "limit": limit}))
    results.append(client.get(P0_SEARCH_SUGGESTIONS, {"keyword": query, "query": query, "region": target_market, "country": target_market, "limit": limit}))
    if config.enable_p1_content_heat:
        results.append(client.get(P1_TRENDING_SEARCHWORDS, {"region": target_market, "country": target_market, "limit": limit}))

    hot_products = normalize_hot_products(_result_payload(results[0]))
    expanded_keywords = normalize_keywords(_result_payload(results[1]))
    trend_keywords = normalize_keywords(_result_payload(results[2])) if config.enable_p1_content_heat and len(results) > 2 else []
    search_keyword = (expanded_keywords[0] if expanded_keywords else query) or query
    search_result = client.get(P0_SEARCH_PRODUCTS, {"keyword": search_keyword, "query": search_keyword, "region": target_market, "country": target_market, "limit": limit})
    results.append(search_result)
    search_products = normalize_search_products(_result_payload(search_result))

    product_details: list[dict[str, Any]] = []
    for product_id in _top_product_ids(search_products or hot_products, config.detail_topk):
        detail_result = client.get(P0_PRODUCT_DETAIL, {"product_id": product_id, "item_id": product_id, "region": target_market, "country": target_market})
        results.append(detail_result)
        if detail_result.ok:
            product_details.append(normalize_product_detail(_result_payload(detail_result)))

    trending_posts: list[dict[str, Any]] = []
    if config.enable_p1_content_heat:
        post_result = client.get(P1_TRENDING_POST, {"region": target_market, "country": target_market, "limit": min(limit, 20)})
        results.append(post_result)
        trending_posts = normalize_trending_posts(_result_payload(post_result))

    ads_keyword_insights: dict[str, Any] | None = None
    if config.enable_p2_ads:
        ads_keyword_result = client.get(P2_KEYWORD_INSIGHTS, {"keyword": query, "region": target_market, "country": target_market})
        ads_top_result = client.get(P2_TOP_PRODUCTS, {"region": target_market, "country": target_market, "limit": min(limit, 20)})
        results.extend([ads_keyword_result, ads_top_result])
        ads_keyword_insights = _result_payload(ads_keyword_result)

    status = _safe_status(results)
    failed_reasons = [result.error for result in results if result.error]
    degradation = {
        "status": status,
        "reason": "; ".join(str(reason) for reason in failed_reasons[:3]) if status != "ok" else "",
    }
    scored = score_opportunity(
        query_terms=query_terms,
        expanded_keywords=expanded_keywords,
        trend_keywords=trend_keywords,
        hot_products=hot_products,
        search_products=search_products,
        product_details=product_details,
        trending_posts=trending_posts,
        ads_keyword_insights=ads_keyword_insights,
    )
    result_text = build_result_text(query, target_market, scored, degradation)
    vendor_response_raw = {result.endpoint: _result_payload(result) for result in results if result.ok}
    snapshot_id = _persist_if_requested(
        payload=payload,
        provider=config.provider,
        request_payload=request_payload,
        vendor_endpoints=[_call_to_dict(result) for result in results],
        vendor_response_raw=vendor_response_raw,
        normalized_summary=scored,
        result_text=result_text,
        status=status,
        latency_ms=int((time.monotonic() - started_at) * 1000),
    )
    return _build_response(
        config.provider,
        request_payload,
        [_call_to_dict(result) for result in results],
        vendor_response_raw,
        scored,
        result_text,
        degradation,
        started_at,
        snapshot_id,
    )


def _persist_if_requested(
    *,
    payload: dict[str, Any],
    provider: str,
    request_payload: dict[str, Any],
    vendor_endpoints: list[dict[str, Any]],
    vendor_response_raw: dict[str, Any],
    normalized_summary: dict[str, Any],
    result_text: str,
    status: str,
    latency_ms: int,
) -> str | None:
    report_run_id = str(payload.get("report_run_id") or "").strip()
    if not report_run_id:
        return None
    with _postgres_conn() as conn:
        return record_tiktok_realtime_query(
            conn,
            report_run_id=report_run_id,
            query=request_payload["query"],
            target_market=request_payload["target_market"],
            provider=provider,
            request_payload=request_payload,
            vendor_endpoints=vendor_endpoints,
            vendor_response_raw=vendor_response_raw,
            normalized_summary=normalized_summary,
            result_text=result_text,
            status=status,
            latency_ms=latency_ms,
        )


def _build_response(
    provider: str,
    request_payload: dict[str, Any],
    vendor_endpoints: list[dict[str, Any]],
    vendor_response_raw: dict[str, Any],
    scored: dict[str, Any],
    result_text: str,
    degradation: dict[str, Any],
    started_at: float,
    snapshot_id: str | None,
) -> dict[str, Any]:
    latency_ms = int((time.monotonic() - started_at) * 1000)
    source_meta = {
        "latency_ms": latency_ms,
        "data_freshness": "realtime",
        "snapshot_id": snapshot_id,
        "endpoint_count": len(vendor_endpoints),
    }
    return {
        "provider": provider,
        "capability": "tiktok_opportunity",
        "query": request_payload["query"],
        "target_market": request_payload["target_market"],
        "summary": scored.get("summary") or {},
        "signals": scored.get("signals") or {},
        "top_products": [],
        "vendor_endpoints": vendor_endpoints,
        "vendor_response_keys": sorted(vendor_response_raw.keys()),
        "result_text": result_text,
        "source_meta": source_meta,
        "degradation": degradation,
    }
