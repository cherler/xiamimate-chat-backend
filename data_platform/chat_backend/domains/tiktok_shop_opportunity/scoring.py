"""Score normalized TikTok Shop realtime signals."""
from __future__ import annotations

from collections import Counter
from typing import Any


IP_SENSITIVE_TERMS = {
    "disney",
    "marvel",
    "pokemon",
    "labubu",
    "sanrio",
    "hello kitty",
    "star wars",
    "nike",
    "adidas",
    "louis vuitton",
}
COMPLIANCE_RISK_TERMS = {
    "baby",
    "kids",
    "child",
    "children",
    "medical",
    "medicine",
    "supplement",
    "laser",
    "battery",
    "charger",
    "cosmetic",
    "skincare",
}
LOGISTICS_RISK_TERMS = {
    "furniture",
    "sofa",
    "mattress",
    "desk",
    "chair",
    "glass",
    "ceramic",
    "fragile",
    "oversized",
    "heavy",
}


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


def _contains_any(text: str, terms: set[str]) -> bool:
    normalized = text.lower()
    return any(term in normalized for term in terms)


def _combined_text(query_terms: list[str], products: list[dict[str, Any]]) -> str:
    parts = [str(term) for term in query_terms]
    parts.extend(str(product.get("title") or "") for product in products)
    parts.extend(str(product.get("shop_name") or "") for product in products)
    return " ".join(part for part in parts if part).lower()


def _infer_seller_fit(
    *,
    query_terms: list[str],
    hot_products: list[dict[str, Any]],
    search_products: list[dict[str, Any]],
    product_details: list[dict[str, Any]],
    trending_posts: list[dict[str, Any]],
    brand_hint: str,
    competition_level: str,
    opportunity_score: float,
) -> dict[str, Any]:
    product_pool = search_products or product_details or hot_products
    text = _combined_text(query_terms, product_pool)
    risk_flags: list[str] = []

    if not search_products and not product_details:
        risk_flags.append("shop_evidence_missing")
    if brand_hint == "high":
        risk_flags.append("brand_dominated")
    if competition_level == "high":
        risk_flags.append("ad_cost_risk")
    if _contains_any(text, IP_SENSITIVE_TERMS):
        risk_flags.append("ip_sensitive")
    if _contains_any(text, LOGISTICS_RISK_TERMS):
        risk_flags.append("logistics_risk")
    if _contains_any(text, COMPLIANCE_RISK_TERMS):
        risk_flags.append("compliance_risk")

    base_score = 48 + opportunity_score * 0.35
    if search_products:
        base_score += 16
    if product_details:
        base_score += 10
    if hot_products:
        base_score += 8
    if trending_posts:
        base_score += 4

    penalties = {
        "shop_evidence_missing": 18,
        "brand_dominated": 25,
        "ad_cost_risk": 18,
        "ip_sensitive": 30,
        "logistics_risk": 16,
        "compliance_risk": 20,
    }
    fit_score = _bounded(base_score - sum(penalties[flag] for flag in risk_flags), upper=100.0)

    if not (hot_products or search_products or product_details or trending_posts):
        fit_level = "unknown"
        recommended_action = "insufficient_evidence"
    elif fit_score >= 70 and not {"brand_dominated", "ip_sensitive", "compliance_risk"} & set(risk_flags):
        fit_level = "good"
        recommended_action = "small_batch_test"
    elif fit_score >= 42:
        fit_level = "caution"
        recommended_action = "content_validate_before_inventory"
    else:
        fit_level = "poor"
        recommended_action = "avoid_or_research"

    if "shop_evidence_missing" in risk_flags and fit_level == "good":
        fit_level = "caution"
        recommended_action = "content_validate_before_inventory"

    return {
        "fit_level": fit_level,
        "fit_score": fit_score,
        "risk_flags": risk_flags,
        "recommended_action": recommended_action,
    }


def _infer_evidence_profile(
    *,
    evidence_sources: dict[str, bool] | None,
    expanded_keywords: list[str],
    trend_keywords: list[str],
    hot_products: list[dict[str, Any]],
    search_products: list[dict[str, Any]],
    product_details: list[dict[str, Any]],
    trending_posts: list[dict[str, Any]],
) -> dict[str, Any]:
    sources = evidence_sources or {
        "shop_search_products": bool(search_products),
        "shop_product_details": bool(product_details),
        "product_signals": bool(hot_products),
        "expanded_keywords": bool(expanded_keywords),
        "tiktok_web_trending_searchwords": bool(trend_keywords),
        "tiktok_web_trending_posts": bool(trending_posts),
    }
    active_sources = [name for name, enabled in sources.items() if enabled]
    strong_sources = ["shop_search_products", "shop_product_details"]
    medium_sources = ["shop_hot_products", "tiktok_ads_top_products", "product_signals"]
    weak_sources = ["expanded_keywords", "tiktok_web_trending_searchwords", "tiktok_web_trending_posts", "tiktok_ads_keyword_insights"]

    if any(sources.get(name) for name in strong_sources):
        level = "strong"
        reason = "TikTok Shop 商品搜索或详情证据可用"
    elif any(sources.get(name) for name in medium_sources):
        level = "medium"
        reason = "仅有热卖池或 Ads 产品侧补证，缺少商品搜索/详情强验证"
    elif any(sources.get(name) for name in weak_sources):
        level = "weak"
        reason = "仅有趋势词、内容热度或关键词补证"
    else:
        level = "insufficient"
        reason = "没有可用 TikHub 业务证据"

    shop_supply_verified = bool(sources.get("shop_search_products") or sources.get("shop_product_details"))
    return {
        "level": level,
        "sources": active_sources,
        "shop_supply_verified": shop_supply_verified,
        "reason": reason,
    }


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
    evidence_sources: dict[str, bool] | None = None,
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
    seller_fit = _infer_seller_fit(
        query_terms=query_terms,
        hot_products=hot_products,
        search_products=search_products,
        product_details=product_details,
        trending_posts=trending_posts,
        brand_hint=brand_hint,
        competition_level=competition_level,
        opportunity_score=opportunity_score,
    )
    evidence_profile = _infer_evidence_profile(
        evidence_sources=evidence_sources,
        expanded_keywords=expanded_keywords,
        trend_keywords=trend_keywords,
        hot_products=hot_products,
        search_products=search_products,
        product_details=product_details,
        trending_posts=trending_posts,
    )
    return {"summary": summary, "signals": signals, "seller_fit": seller_fit, "evidence_profile": evidence_profile}


def build_result_text(query: str, target_market: str, scored: dict[str, Any], degradation: dict[str, Any]) -> str:
    summary = scored.get("summary") or {}
    signals = scored.get("signals") or {}
    seller_fit = scored.get("seller_fit") or {}
    evidence_profile = scored.get("evidence_profile") or {}
    supplier_issue = scored.get("supplier_issue") or {}
    level = summary.get("opportunity_level") or "unknown"
    confidence = summary.get("confidence")
    status = degradation.get("status") or "unknown"
    risk_flags = seller_fit.get("risk_flags") or []
    parts = [
        f"TikTok Shop 实时增强：{query} / {target_market} 当前机会等级为 {level}，置信度 {confidence}。",
        f"热点词 {signals.get('hot_keyword_count', 0)} 个，热卖商品 {signals.get('hot_product_count', 0)} 个，搜索候选商品 {signals.get('product_candidate_count', 0)} 个。",
        f"证据层级：{evidence_profile.get('level', 'insufficient')}；{evidence_profile.get('reason', '证据不足')}。",
        f"内容热度分 {signals.get('content_heat_score', 0)}，品牌集中度 {signals.get('brand_concentration_hint', 'unknown')}。",
        f"中小卖家适配结论：{seller_fit.get('fit_level', 'unknown')}，建议动作：{seller_fit.get('recommended_action', 'insufficient_evidence')}。",
    ]
    if risk_flags:
        parts.append(f"中小卖家风险标记：{', '.join(str(flag) for flag in risk_flags)}。")
    if supplier_issue:
        parts.append(f"供应商接口问题：{supplier_issue.get('issue_type')}，失败 Shop Web 端点 {supplier_issue.get('failed_endpoint_count', 0)} 个。")
    if status != "ok":
        parts.append(f"降级状态：{status}；原因：{degradation.get('reason') or 'partial evidence'}。")
    return "\n".join(parts)
