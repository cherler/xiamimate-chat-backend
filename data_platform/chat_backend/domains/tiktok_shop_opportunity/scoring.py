"""Score normalized TikTok Shop realtime signals."""
from __future__ import annotations

from collections import Counter
from typing import Any


def _bounded(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return round(max(lower, min(upper, value)), 2)


def _brand_concentration(products: list[dict[str, Any]]) -> tuple[str, float]:
    names = [str(item.get("shop_name") or "").strip().lower() for item in products if item.get("shop_name")]
    if not names:
        return "unknown", 0.0
    top_count = Counter(names).most_common(1)[0][1]
    share = round(top_count / len(names), 4)
    if share >= 0.45:
        return "high", share
    if share >= 0.25:
        return "medium", share
    return "low", share


def _keyword_overlap(query_terms: list[str], trend_keywords: list[str]) -> float:
    normalized_query_terms = {term.strip().lower() for term in query_terms if term.strip()}
    normalized_trends = {term.strip().lower() for term in trend_keywords if term.strip()}
    if not normalized_query_terms or not normalized_trends:
        return 0.0
    return round(len(normalized_query_terms & normalized_trends) / len(normalized_query_terms), 4)


def score_opportunity(
    *,
    query_terms: list[str],
    expanded_keywords: list[str],
    trend_keywords: list[str],
    hot_products: list[dict[str, Any]],
    search_products: list[dict[str, Any]],
    product_details: list[dict[str, Any]],
    trending_posts: list[dict[str, Any]],
    ads_keyword_insights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    product_pool = search_products or hot_products
    brand_hint, brand_share = _brand_concentration(product_pool)
    trend_overlap = _keyword_overlap(query_terms + expanded_keywords[:5], trend_keywords)
    content_heat_score = _bounded(len(trending_posts) * 8 + trend_overlap * 40)
    product_momentum_score = _bounded(len(hot_products) * 4 + len(search_products) * 2 + len(product_details) * 3)
    keyword_heat_score = _bounded(len(expanded_keywords) * 6 + trend_overlap * 35)
    concentration_penalty = {"high": 18, "medium": 8, "low": 0, "unknown": 5}.get(brand_hint, 5)
    raw_score = keyword_heat_score * 0.30 + product_momentum_score * 0.35 + content_heat_score * 0.25 - concentration_penalty
    opportunity_score = _bounded(raw_score)

    if opportunity_score >= 68:
        level = "high"
    elif opportunity_score >= 42:
        level = "medium"
    elif opportunity_score > 0:
        level = "low"
    else:
        level = "unknown"

    evidence_groups = sum(
        1
        for value in (expanded_keywords, trend_keywords, hot_products, search_products, product_details, trending_posts)
        if value
    )
    confidence = round(min(0.95, 0.18 + evidence_groups * 0.12 + opportunity_score / 250), 2)
    competition_level = str((ads_keyword_insights or {}).get("competition_level") or "unknown")

    signals = {
        "hot_keyword_count": len(expanded_keywords),
        "trend_keyword_count": len(trend_keywords),
        "trend_keyword_overlap_ratio": trend_overlap,
        "hot_product_count": len(hot_products),
        "product_candidate_count": len(search_products),
        "product_detail_count": len(product_details),
        "content_heat_score": content_heat_score,
        "product_momentum_score": product_momentum_score,
        "keyword_heat_score": keyword_heat_score,
        "brand_concentration_hint": brand_hint,
        "brand_top_share": brand_share,
        "competition_level": competition_level,
    }

    summary = {
        "opportunity_level": level,
        "confidence": confidence,
        "opportunity_score": opportunity_score,
    }
    return {"summary": summary, "signals": signals}


def build_result_text(query: str, target_market: str, scored: dict[str, Any], degradation: dict[str, Any]) -> str:
    summary = scored.get("summary") or {}
    signals = scored.get("signals") or {}
    level = summary.get("opportunity_level") or "unknown"
    confidence = summary.get("confidence")
    status = degradation.get("status") or "unknown"
    parts = [
        f"TikTok Shop 实时增强：{query} / {target_market} 当前机会等级为 {level}，置信度 {confidence}。",
        f"热点词 {signals.get('hot_keyword_count', 0)} 个，热卖商品 {signals.get('hot_product_count', 0)} 个，搜索候选商品 {signals.get('product_candidate_count', 0)} 个。",
        f"内容热度分 {signals.get('content_heat_score', 0)}，品牌集中度 {signals.get('brand_concentration_hint', 'unknown')}。",
    ]
    if status != "ok":
        parts.append(f"降级状态：{status}；原因：{degradation.get('reason') or 'partial evidence'}。")
    return "\n".join(parts)
