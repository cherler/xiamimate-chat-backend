"""Score 1688 supplier feasibility and supply-side risk."""
from __future__ import annotations

from statistics import median
from typing import Any


DEFAULT_COST_ASSUMPTIONS = {
    "fx_cny_usd": 7.25,
    "domestic_shipping_usd_per_unit": 0.4,
    "international_shipping_usd_per_unit": 2.0,
    "packaging_usd_per_unit": 0.3,
    "duty_usd_per_unit": 0.2,
    "platform_fee_rate": 0.15,
    "payment_fee_rate": 0.03,
    "return_reserve_rate": 0.08,
    "target_margin_rate": 0.25,
}

QUERY_TRANSLATIONS = {
    "portable blender": ["便携式榨汁机", "便携榨汁杯 外贸", "榨汁杯 工厂"],
    "personal blender": ["便携式榨汁机", "榨汁杯", "便携榨汁杯 工厂"],
    "digital photo frame": ["数码相框", "电子相框 外贸", "数码相框 工厂"],
    "handheld shower head": ["手持花洒", "手持淋浴喷头 外贸", "花洒 工厂"],
    "pet grooming vacuum": ["宠物吸毛器", "宠物美容吸尘器 外贸", "宠物吸毛器 工厂"],
}

GENERIC_QUERY_TERMS = {"home", "kitchen", "beauty", "pet", "pets", "toy", "toys", "gift", "gifts", "electronics"}
OUT_OF_SCOPE_TERMS = {"software", "app", "ebook", "movie", "music", "weapon", "medicine", "supplement"}


def build_supplier_queries(query: str, supplied_queries: list[str] | None = None) -> list[dict[str, str]]:
    if supplied_queries:
        return [{"query": item.strip(), "source": "user_input"} for item in supplied_queries if item and item.strip()][:5]
    normalized = " ".join(str(query or "").lower().split())
    translated = QUERY_TRANSLATIONS.get(normalized)
    if translated:
        return [{"query": item, "source": "rule_translation"} for item in translated]
    if any("\u4e00" <= char <= "\u9fff" for char in query):
        base = query.strip()
        candidates = [base, f"{base} 外贸", f"{base} 工厂"]
        return [{"query": item, "source": "rule_expansion"} for item in candidates[:5]]
    return [{"query": query.strip(), "source": "user_input"}] if query.strip() else []


def should_skip_query(query: str) -> tuple[bool, str]:
    normalized = " ".join(str(query or "").lower().replace("/", " ").replace("-", " ").split())
    tokens = normalized.split()
    if not normalized:
        return True, "query_missing"
    if normalized in GENERIC_QUERY_TERMS or (len(tokens) == 1 and tokens[0] in GENERIC_QUERY_TERMS):
        return True, "query_too_broad"
    if any(term in normalized for term in OUT_OF_SCOPE_TERMS):
        return True, "out_of_scope"
    return False, "clear_supplier_query"


def score_supplier_result(
    *,
    query: str,
    marketplace: str,
    offers: list[dict[str, Any]],
    cost_assumptions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assumptions = {**DEFAULT_COST_ASSUMPTIONS, **(cost_assumptions or {})}
    valid_prices = [float(offer["price_cny"]) for offer in offers if _positive_number(offer.get("price_cny"))]
    moqs = [int(offer["moq"]) for offer in offers if _positive_number(offer.get("moq"))]
    supplier_ids = {_supplier_key(offer) for offer in offers if _supplier_key(offer)}
    recent_sales_supported = [offer for offer in offers if _positive_number(offer.get("sales_30d"))]
    low_moq_offers = [offer for offer in offers if _positive_number(offer.get("moq")) and int(offer["moq"]) <= 50]
    supplier_scores = [_single_supplier_score(offer) for offer in offers]
    price_p20 = _percentile(valid_prices, 0.2)
    price_p50 = _percentile(valid_prices, 0.5)
    price_p80 = _percentile(valid_prices, 0.8)
    moq_p50 = median(moqs) if moqs else None
    cost_floor = _build_cost_floor(price_p20 or price_p50, assumptions)
    supply_crowding_level = _crowding_level(len(offers), len(supplier_ids))
    copyability_level = _copyability_level(len(offers), len(low_moq_offers), price_p20, price_p80)
    risk_exclusion = _build_risk_exclusion(
        offer_count=len(offers),
        supplier_count=len(supplier_ids),
        supply_crowding_level=supply_crowding_level,
        copyability_level=copyability_level,
        moq_p50=moq_p50,
        supplier_score_avg=round(sum(supplier_scores) / len(supplier_scores), 2) if supplier_scores else None,
        cost_floor=cost_floor,
        recent_sales_supported_count=len(recent_sales_supported),
    )
    supplier_score = round(sum(supplier_scores) / len(supplier_scores), 2) if supplier_scores else 0
    supplier_feasibility = _supplier_feasibility(supplier_score, len(supplier_ids), len(offers), len(low_moq_offers), risk_exclusion["verdict"])
    signals = {
        "offer_count": len(offers),
        "supplier_count": len(supplier_ids),
        "factory_evidence_count": 0,
        "unit_price_cny_p20": price_p20,
        "unit_price_cny_p50": price_p50,
        "unit_price_cny_p80": price_p80,
        "moq_median": moq_p50,
        "low_moq_offer_count": len(low_moq_offers),
        "recent_sales_supported_count": len(recent_sales_supported),
        "supplier_score_avg": supplier_score,
        "supply_crowding_level": supply_crowding_level,
        "copyability_level": copyability_level,
    }
    summary = {
        "supplier_feasibility": supplier_feasibility["verdict"],
        "supplier_score": supplier_score,
        "risk_verdict": risk_exclusion["verdict"],
        "confidence": _confidence(signals, risk_exclusion),
    }
    return {
        "source_tool": "onebound_1688_supplier_discovery",
        "query": query,
        "marketplace": marketplace,
        "summary": summary,
        "signals": signals,
        "supplier_feasibility": supplier_feasibility,
        "risk_exclusion": risk_exclusion,
        "cost_floor": cost_floor,
        "cost_assumptions": assumptions,
        "result_text": build_result_text(query, marketplace, summary, signals, cost_floor, risk_exclusion),
        "evidence_contract": {
            "tool_facts": ["onebound_1688_item_search", "onebound_1688_item_get", "onebound_1688_seller_info"],
            "derived_metrics": ["supplier_score", "risk_score", "cost_floor"],
            "hypotheses": ["supplier_query_rewrite", "default_cost_assumptions"],
        },
    }


def build_empty_scored(query: str, marketplace: str, *, status: str, reason: str) -> dict[str, Any]:
    risk_exclusion = {
        "verdict": "unknown",
        "risk_score": None,
        "reasons": [reason],
        "risk_flags": [status],
        "evidence_confidence": "low",
    }
    supplier_feasibility = {
        "verdict": "unknown",
        "supplier_score": 0,
        "supplier_count": 0,
        "offer_count": 0,
        "factory_evidence_count": 0,
        "confidence": "low",
    }
    summary = {"supplier_feasibility": "unknown", "supplier_score": 0, "risk_verdict": "unknown", "confidence": "low"}
    signals = {"offer_count": 0, "supplier_count": 0, "supply_crowding_level": "unknown"}
    return {
        "source_tool": "onebound_1688_supplier_discovery",
        "query": query,
        "marketplace": marketplace,
        "summary": summary,
        "signals": signals,
        "supplier_feasibility": supplier_feasibility,
        "risk_exclusion": risk_exclusion,
        "cost_floor": {},
        "result_text": build_result_text(query, marketplace, summary, signals, {}, risk_exclusion),
        "evidence_contract": {"tool_facts": [], "derived_metrics": [], "hypotheses": []},
    }


def build_result_text(
    query: str,
    marketplace: str,
    summary: dict[str, Any],
    signals: dict[str, Any],
    cost_floor: dict[str, Any],
    risk_exclusion: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "## 1688 供应商发现结果",
            f"主题: {query} | 目标市场: {marketplace}",
            f"供应商结论: {summary.get('supplier_feasibility')} | 供应商分: {summary.get('supplier_score')} | 置信度: {summary.get('confidence')}",
            f"供给证据: 有效商品 {signals.get('offer_count', 0)} 个，去重供应商 {signals.get('supplier_count', 0)} 个，低 MOQ 商品 {signals.get('low_moq_offer_count', 0)} 个。",
            f"成本底线: P20 供应价 {cost_floor.get('unit_price_cny_p20')} CNY，估算到岸成本 {cost_floor.get('landed_cost_usd_estimated')} USD，目标售价 {cost_floor.get('target_selling_price_usd_estimated')} USD。",
            f"风险排除: {risk_exclusion.get('verdict')}；原因: {'；'.join(risk_exclusion.get('reasons') or []) or '证据不足'}。",
            "证据限制: Onebound 1688 实时结果只代表本次查询；成本为默认假设推导，真实采购前仍需核验物流、包装、认证与样品质量。",
        ]
    )


def _positive_number(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _supplier_key(offer: dict[str, Any]) -> str:
    return str(offer.get("seller_id") or offer.get("shop_id") or offer.get("shop_name") or "").strip()


def _single_supplier_score(offer: dict[str, Any]) -> float:
    price_score = 80 if _positive_number(offer.get("price_cny")) else 20
    moq = offer.get("moq")
    if _positive_number(moq):
        moq_score = 90 if int(moq) <= 50 else 60 if int(moq) <= 300 else 20
    else:
        moq_score = 40
    seller = offer.get("seller_info") if isinstance(offer.get("seller_info"), dict) else {}
    scores = seller.get("scores") if isinstance(seller.get("scores"), dict) else {}
    score_values = [float(value) for value in scores.values() if _positive_number(value)]
    reliability_score = min(100, max(30, (sum(score_values) / len(score_values)) * 20)) if score_values else 45
    sales_score = 85 if _positive_number(offer.get("sales_30d")) else 35
    factory_score = 50
    match_score = 70 if offer.get("title") else 40
    return round(
        0.25 * price_score + 0.20 * moq_score + 0.20 * reliability_score + 0.15 * sales_score + 0.10 * factory_score + 0.10 * match_score,
        2,
    )


def _percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    index = min(len(sorted_values) - 1, max(0, int(round((len(sorted_values) - 1) * ratio))))
    return round(sorted_values[index], 2)


def _build_cost_floor(price_cny: float | None, assumptions: dict[str, Any]) -> dict[str, Any]:
    if price_cny is None:
        return {"cost_confidence": "low", "reason": "price_missing"}
    fx = float(assumptions.get("fx_cny_usd") or DEFAULT_COST_ASSUMPTIONS["fx_cny_usd"])
    unit_price_usd = price_cny / fx if fx else 0
    landed = unit_price_usd + float(assumptions.get("domestic_shipping_usd_per_unit") or 0) + float(assumptions.get("international_shipping_usd_per_unit") or 0) + float(assumptions.get("packaging_usd_per_unit") or 0) + float(assumptions.get("duty_usd_per_unit") or 0)
    fee_rate = float(assumptions.get("platform_fee_rate") or 0) + float(assumptions.get("payment_fee_rate") or 0) + float(assumptions.get("return_reserve_rate") or 0)
    break_even = landed / max(0.01, 1 - fee_rate)
    target = break_even / max(0.01, 1 - float(assumptions.get("target_margin_rate") or 0))
    return {
        "unit_price_cny_p20": round(price_cny, 2),
        "unit_price_usd_p20": round(unit_price_usd, 2),
        "landed_cost_usd_estimated": round(landed, 2),
        "break_even_price_usd_estimated": round(break_even, 2),
        "target_selling_price_usd_estimated": round(target, 2),
        "cost_confidence": "medium",
    }


def _crowding_level(offer_count: int, supplier_count: int) -> str:
    if offer_count >= 60 or supplier_count >= 30:
        return "high"
    if offer_count >= 20 or supplier_count >= 10:
        return "medium"
    if offer_count > 0:
        return "low"
    return "unknown"


def _copyability_level(offer_count: int, low_moq_count: int, price_p20: float | None, price_p80: float | None) -> str:
    price_spread_narrow = price_p20 is not None and price_p80 is not None and price_p80 <= price_p20 * 1.5
    if offer_count >= 30 and low_moq_count >= 10 and price_spread_narrow:
        return "high"
    if offer_count >= 10 and low_moq_count >= 3:
        return "medium"
    if offer_count > 0:
        return "low"
    return "unknown"


def _build_risk_exclusion(**kwargs: Any) -> dict[str, Any]:
    reasons: list[str] = []
    flags: list[str] = []
    risk_score = 0
    if kwargs["supply_crowding_level"] == "high":
        risk_score += 30
        flags.append("supply_crowding_high")
        reasons.append("1688 供给数量很高，存在同款低价竞争风险")
    elif kwargs["supply_crowding_level"] == "medium":
        risk_score += 18
        flags.append("supply_crowding_medium")
        reasons.append("1688 供给数量较多，需要筛选差异化变体")
    if kwargs["copyability_level"] == "high":
        risk_score += 25
        flags.append("copyability_high")
        reasons.append("低 MOQ 近似供给较多，容易被复制")
    if kwargs["moq_p50"] is not None and kwargs["moq_p50"] > 300:
        risk_score += 25
        flags.append("moq_unfriendly")
        reasons.append("MOQ 中位数偏高，不适合小批量验证")
    if kwargs["supplier_score_avg"] is not None and kwargs["supplier_score_avg"] < 45:
        risk_score += 20
        flags.append("supplier_evidence_weak")
        reasons.append("Top 供应商评分或成交证据不足")
    if kwargs["recent_sales_supported_count"] == 0 and kwargs["offer_count"] > 0:
        risk_score += 10
        flags.append("recent_sales_missing")
        reasons.append("缺少近 30 天成交证据")
    if kwargs["offer_count"] == 0:
        return {"verdict": "unknown", "risk_score": None, "reasons": ["Onebound 1688 未返回有效供应商候选"], "risk_flags": ["no_supplier_evidence"], "evidence_confidence": "low"}
    verdict = "exclude" if risk_score >= 70 else "caution" if risk_score >= 35 else "pass"
    return {"verdict": verdict, "risk_score": risk_score, "reasons": reasons or ["供应侧未发现明显排除信号"], "risk_flags": flags, "evidence_confidence": "medium"}


def _supplier_feasibility(supplier_score: float, supplier_count: int, offer_count: int, low_moq_count: int, risk_verdict: str) -> dict[str, Any]:
    if supplier_count == 0:
        verdict = "unknown"
    elif risk_verdict == "exclude":
        verdict = "not_feasible"
    elif supplier_score >= 65 and low_moq_count >= 3:
        verdict = "feasible"
    else:
        verdict = "limited"
    return {"verdict": verdict, "supplier_score": supplier_score, "supplier_count": supplier_count, "offer_count": offer_count, "factory_evidence_count": 0, "confidence": "medium" if supplier_count else "low"}


def _confidence(signals: dict[str, Any], risk_exclusion: dict[str, Any]) -> str:
    if signals.get("offer_count", 0) >= 10 and signals.get("supplier_count", 0) >= 5:
        return "medium" if risk_exclusion.get("evidence_confidence") != "high" else "high"
    if signals.get("offer_count", 0) > 0:
        return "low"
    return "low"
