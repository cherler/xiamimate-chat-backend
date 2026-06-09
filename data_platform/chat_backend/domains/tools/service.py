"""Free seller tools — rule-based calculators + MiniMax-backed content tools.

设计原则（见产品方案 docs/阶段二/虾米选品免费工具集产品方案-2026-06-08.md）:

1. 算数/规则类（利润、定价）: 纯公式计算，结果可复现，绝不交给 LLM。
2. 内容类（标题诊断优化）: 规则负责评分与问题诊断，MiniMax 负责基于诊断结果
   生成优化版本。AI 调用复用已购年包（AGENT_ANTHROPIC），并带配额保护。
3. 所有工具统一返回 ``{summary, details, prompt_template, meta}`` 四段结构。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from typing import Any

from data_platform.llm_client import (
    LLMJSONParseError,
    build_llm_provider,
)

# --------------------------------------------------------------------------- #
# 输入边界 / 配额保护配置
# --------------------------------------------------------------------------- #

MAX_TITLE_LENGTH = 600
MAX_KEYWORD_INPUT_LENGTH = 4000
_MAX_NUMERIC_VALUE = 1_000_000_000.0

# 内容类（AI）工具的配额保护
_AI_RATE_LIMIT_MAX_CALLS = int(os.environ.get("TOOLS_AI_RATE_LIMIT_MAX_CALLS", "20") or "20")
_AI_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("TOOLS_AI_RATE_LIMIT_WINDOW_SECONDS", "600") or "600")
_AI_DAILY_CALL_CAP = int(os.environ.get("TOOLS_AI_DAILY_CALL_CAP", "800") or "800")
_AI_CACHE_TTL_SECONDS = int(os.environ.get("TOOLS_AI_CACHE_TTL_SECONDS", "3600") or "3600")
_AI_CACHE_MAX_ENTRIES = 512

_AI_GUARD_LOCK = threading.Lock()
_AI_IP_BUCKETS: dict[str, list[float]] = {}
_AI_DAILY_COUNTER: dict[str, int] = {"day": 0, "count": 0}
_AI_RESULT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


class ToolInputError(ValueError):
    """用户输入不合法（由路由层转成 400）。"""


class ToolQuotaExceeded(RuntimeError):
    """AI 配额触顶，需降级为复制提示词跳转。"""


# --------------------------------------------------------------------------- #
# 通用辅助
# --------------------------------------------------------------------------- #

def _coerce_float(value: Any, field: str, *, required: bool = True, default: float = 0.0) -> float:
    if value is None or value == "":
        if required:
            raise ToolInputError(f"缺少必填字段: {field}")
        return float(default)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ToolInputError(f"字段 {field} 需要是数字")
    if number != number or number in (float("inf"), float("-inf")):
        raise ToolInputError(f"字段 {field} 数值不合法")
    if number < 0:
        raise ToolInputError(f"字段 {field} 不能为负数")
    if number > _MAX_NUMERIC_VALUE:
        raise ToolInputError(f"字段 {field} 数值超出允许范围")
    return number


def _coerce_rate(value: Any, field: str, *, required: bool = False, default: float = 0.0) -> float:
    """把百分比字段（如 15 或 15%）转成 0-1 之间的费率。"""
    if value is None or value == "":
        if required:
            raise ToolInputError(f"缺少必填字段: {field}")
        return float(default)
    text = str(value).strip().rstrip("%").strip()
    try:
        number = float(text)
    except (TypeError, ValueError):
        raise ToolInputError(f"字段 {field} 需要是百分比数字")
    if number != number:
        raise ToolInputError(f"字段 {field} 数值不合法")
    if number < 0:
        raise ToolInputError(f"字段 {field} 不能为负数")
    # 支持输入 0.15 或 15 两种写法
    rate = number / 100.0 if number > 1 else number
    if rate >= 1:
        raise ToolInputError(f"字段 {field} 比例需要小于 100%")
    return rate


def _round2(value: float) -> float:
    return round(float(value) + 1e-9, 2)


# --------------------------------------------------------------------------- #
# 工具 1: 利润计算器（纯规则）
# --------------------------------------------------------------------------- #

def compute_profit_calculator(payload: dict[str, Any]) -> dict[str, Any]:
    price = _coerce_float(payload.get("price"), "售价", required=True)
    if price <= 0:
        raise ToolInputError("售价需要大于 0")
    cost = _coerce_float(payload.get("cost"), "采购成本", required=True)
    domestic_shipping = _coerce_float(payload.get("domestic_shipping"), "国内运费", required=False)
    head_shipping = _coerce_float(payload.get("head_shipping"), "头程运费", required=False)
    last_mile = _coerce_float(payload.get("last_mile"), "尾程/仓配", required=False)
    commission_rate = _coerce_rate(payload.get("commission_rate"), "平台佣金比例", required=False)
    refund_rate = _coerce_rate(payload.get("refund_rate"), "退款损耗比例", required=False)
    ad_rate = _coerce_rate(payload.get("ad_rate"), "广告成本占比", required=False, default=0.0)

    proportional_rate = commission_rate + ad_rate + refund_rate
    if proportional_rate >= 1:
        raise ToolInputError("佣金、广告、退款损耗合计比例需要小于 100%")

    fixed_cost = cost + domestic_shipping + head_shipping + last_mile
    commission_cost = price * commission_rate
    ad_cost = price * ad_rate
    refund_loss = price * refund_rate
    total_cost = fixed_cost + commission_cost + ad_cost + refund_loss
    gross_profit = price - total_cost
    gross_margin = gross_profit / price if price else 0.0
    breakeven_price = fixed_cost / (1 - proportional_rate)

    if gross_margin < 0:
        risk = "亏损"
        risk_note = "当前售价无法覆盖成本，建议提高售价或压缩成本。"
    elif gross_margin < 0.1:
        risk = "偏低"
        risk_note = "毛利率偏低，抗风险能力弱，建议优化成本或定价。"
    elif gross_margin < 0.25:
        risk = "可接受"
        risk_note = "毛利率处于可接受区间，可结合广告和退货情况持续观察。"
    else:
        risk = "较优"
        risk_note = "毛利率较优，有一定让利和投放空间。"

    suggested_low = _round2(max(breakeven_price, price * 0.95))
    suggested_high = _round2(price * 1.15)

    summary = {
        "headline": f"毛利率 {round(gross_margin * 100, 1)}%（{risk}）",
        "gross_profit": _round2(gross_profit),
        "gross_margin_pct": round(gross_margin * 100, 1),
        "breakeven_price": _round2(breakeven_price),
        "risk": risk,
    }
    details = {
        "cost_breakdown": [
            {"label": "采购成本", "value": _round2(cost)},
            {"label": "国内运费", "value": _round2(domestic_shipping)},
            {"label": "头程运费", "value": _round2(head_shipping)},
            {"label": "尾程/仓配", "value": _round2(last_mile)},
            {"label": "平台佣金", "value": _round2(commission_cost)},
            {"label": "广告成本", "value": _round2(ad_cost)},
            {"label": "退款损耗", "value": _round2(refund_loss)},
        ],
        "total_cost": _round2(total_cost),
        "suggested_price_range": [suggested_low, suggested_high],
        "risk_note": risk_note,
    }
    prompt_template = (
        "请根据下面的成本结构，帮我判断这个商品的定价是否合理，"
        "并给出低价稳单、中档利润、冲高客单三种定价策略。\n"
        f"- 售价: {_round2(price)}\n"
        f"- 总成本: {_round2(total_cost)}（含采购{_round2(cost)}、头程{_round2(head_shipping)}、"
        f"尾程{_round2(last_mile)}、佣金{_round2(commission_cost)}、广告{_round2(ad_cost)}、"
        f"退款损耗{_round2(refund_loss)}）\n"
        f"- 毛利额: {_round2(gross_profit)}，毛利率: {round(gross_margin * 100, 1)}%\n"
        f"- 保本价: {_round2(breakeven_price)}"
    )
    return {
        "summary": summary,
        "details": details,
        "prompt_template": prompt_template,
        "meta": {"tool": "profit_calculator", "tier": "rule", "ai_used": False},
    }


# --------------------------------------------------------------------------- #
# 工具 2: 定价倒推器（纯规则）
# --------------------------------------------------------------------------- #

def compute_pricing_reverse(payload: dict[str, Any]) -> dict[str, Any]:
    total_cost = _coerce_float(payload.get("total_cost"), "总成本", required=True)
    if total_cost <= 0:
        raise ToolInputError("总成本需要大于 0")
    target_margin = _coerce_rate(payload.get("target_margin"), "目标毛利率", required=True)
    commission_rate = _coerce_rate(payload.get("commission_rate"), "平台佣金比例", required=False)
    ad_rate = _coerce_rate(payload.get("ad_rate"), "广告占比", required=False, default=0.0)

    proportional_rate = commission_rate + ad_rate

    def _price_for_margin(margin: float) -> float | None:
        denom = 1 - proportional_rate - margin
        if denom <= 0:
            return None
        return total_cost / denom

    breakeven_denom = 1 - proportional_rate
    if breakeven_denom <= 0:
        raise ToolInputError("佣金与广告合计比例需要小于 100%")
    min_price = total_cost / breakeven_denom
    safe_price = _price_for_margin(target_margin * 0.5)
    target_price = _price_for_margin(target_margin)

    if target_price is None:
        summary = {
            "headline": "目标毛利率过高，无法满足",
            "feasible": False,
            "min_price": _round2(min_price),
        }
        details = {
            "risk_note": (
                "在当前佣金和广告占比下，目标毛利率过高，没有可行售价。"
                "建议降低目标毛利率，或压缩佣金/广告占比。"
            ),
            "price_ladder": [
                {"label": "保本价（毛利 0）", "value": _round2(min_price)},
            ],
        }
    else:
        summary = {
            "headline": f"目标利润价约 {_round2(target_price)}",
            "feasible": True,
            "min_price": _round2(min_price),
            "target_price": _round2(target_price),
        }
        details = {
            "price_ladder": [
                {"label": "最低可卖（保本价）", "value": _round2(min_price), "scene": "清库存、引流款可短期接近此价。"},
                {"label": "建议安全价", "value": _round2(safe_price) if safe_price else _round2(target_price), "scene": "兼顾出单与利润的中间锚点。"},
                {"label": "目标利润价", "value": _round2(target_price), "scene": "满足目标毛利率的定价。"},
            ],
            "risk_note": (
                "目标毛利率较高，定价压力较大，建议结合市场价格带判断是否可行。"
                if (1 - proportional_rate - target_margin) < 0.1
                else "定价空间相对合理，可结合竞品价格带做最终决定。"
            ),
        }

    prompt_template = (
        "请基于下面的成本和目标毛利，帮我判断在目标市场的合理价格带，"
        "并给出保守、主推、冲高三档定价建议。\n"
        f"- 总成本: {_round2(total_cost)}\n"
        f"- 目标毛利率: {round(target_margin * 100, 1)}%\n"
        f"- 平台佣金比例: {round(commission_rate * 100, 1)}%，广告占比: {round(ad_rate * 100, 1)}%\n"
        f"- 保本价: {_round2(min_price)}"
        + (f"，目标利润价: {_round2(target_price)}" if target_price else "")
    )
    return {
        "summary": summary,
        "details": details,
        "prompt_template": prompt_template,
        "meta": {"tool": "pricing_reverse", "tier": "rule", "ai_used": False},
    }


# --------------------------------------------------------------------------- #
# 工具 3: 标题诊断优化器（规则评分 + MiniMax 生成）
# --------------------------------------------------------------------------- #

_TITLE_STOPWORDS = {
    "the", "a", "an", "for", "with", "and", "or", "of", "to", "in", "on",
    "by", "from", "your", "you", "our", "is", "are", "new", "best",
}

_TITLE_LENGTH_RANGES = {
    # site -> (min_ideal, max_ideal, hard_max)
    "amazon": (80, 200, 250),
    "tiktok": (30, 100, 120),
    "temu": (30, 130, 160),
    "default": (40, 160, 220),
}


def _normalize_title(title: str) -> str:
    text = re.sub(r"\s+", " ", str(title or "").strip())
    return text


def _title_tokens(title: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z0-9']+", title)]


def _diagnose_title_rule(title: str, site: str, brand: str, keywords: list[str]) -> dict[str, Any]:
    normalized = _normalize_title(title)
    length = len(normalized)
    site_key = site if site in _TITLE_LENGTH_RANGES else "default"
    min_ideal, max_ideal, hard_max = _TITLE_LENGTH_RANGES[site_key]

    issues: list[str] = []
    score = 100

    # 长度评估
    if length == 0:
        raise ToolInputError("标题不能为空")
    if length < min_ideal:
        deduct = min(25, (min_ideal - length) // 4 + 5)
        score -= deduct
        length_status = "偏短"
        issues.append(f"标题偏短（{length} 字符），建议补充核心属性和使用场景。")
    elif length > hard_max:
        score -= 20
        length_status = "过长"
        issues.append(f"标题过长（{length} 字符），可能被平台截断，建议精简。")
    elif length > max_ideal:
        score -= 8
        length_status = "偏长"
        issues.append(f"标题略长（{length} 字符），可考虑精简弱价值词。")
    else:
        length_status = "合理"

    # 重复词 / 堆砌
    tokens = _title_tokens(normalized)
    freq: dict[str, int] = {}
    for tok in tokens:
        if tok in _TITLE_STOPWORDS or len(tok) <= 2:
            continue
        freq[tok] = freq.get(tok, 0) + 1
    repeated = sorted([w for w, c in freq.items() if c >= 3], key=lambda w: -freq[w])
    if repeated:
        score -= min(20, len(repeated) * 6)
        issues.append("存在关键词堆砌/重复：" + "、".join(repeated[:5]))

    # 关键词与品牌覆盖
    lower_title = normalized.lower()
    missing_keywords = [kw for kw in keywords if kw and kw.lower() not in lower_title]
    if missing_keywords:
        score -= min(18, len(missing_keywords) * 6)
        issues.append("以下核心关键词未出现在标题中：" + "、".join(missing_keywords[:5]))
    brand_missing = bool(brand) and brand.lower() not in lower_title
    if brand_missing:
        score -= 6
        issues.append(f"品牌词「{brand}」未出现在标题中。")

    score = max(0, min(100, score))
    if score >= 85:
        verdict = "标题质量较好"
    elif score >= 70:
        verdict = "标题基本可用，有优化空间"
    elif score >= 50:
        verdict = "标题存在明显问题，建议优化"
    else:
        verdict = "标题问题较多，建议重写"

    return {
        "score": score,
        "verdict": verdict,
        "length": length,
        "length_status": length_status,
        "repeated_words": repeated[:8],
        "missing_keywords": missing_keywords[:8],
        "brand_missing": brand_missing,
        "issues": issues,
    }


def diagnose_title(payload: dict[str, Any], *, client_ip: str) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip()
    if not title:
        raise ToolInputError("请填写商品标题")
    if len(title) > MAX_TITLE_LENGTH:
        raise ToolInputError(f"标题过长，请控制在 {MAX_TITLE_LENGTH} 字符以内")
    site = str(payload.get("site") or "amazon").strip().lower()
    brand = str(payload.get("brand") or "").strip()[:60]
    keywords_raw = payload.get("keywords") or ""
    if isinstance(keywords_raw, list):
        keywords = [str(k).strip() for k in keywords_raw if str(k).strip()]
    else:
        keywords = [k.strip() for k in re.split(r"[,，;；\n]+", str(keywords_raw)) if k.strip()]
    keywords = keywords[:10]

    rule_result = _diagnose_title_rule(title, site, brand, keywords)

    prompt_template = (
        "请基于下面这条标题的评分结果，生成 3 个更适合目标站点的优化版本，"
        "并分别说明适用场景、保留词和建议强化词。\n"
        f"- 站点: {site}\n"
        f"- 原标题: {title}\n"
        f"- 评分: {rule_result['score']}（{rule_result['verdict']}）\n"
        f"- 主要问题: {'；'.join(rule_result['issues']) or '无明显问题'}"
    )

    ai_section: dict[str, Any] = {"status": "skipped", "variants": []}
    try:
        variants = _generate_title_variants(
            title=title,
            site=site,
            brand=brand,
            keywords=keywords,
            rule_result=rule_result,
            client_ip=client_ip,
        )
        ai_section = {"status": "ok", "variants": variants}
    except ToolQuotaExceeded:
        ai_section = {
            "status": "degraded",
            "variants": [],
            "note": "AI 优化今日调用较多，已暂时降级。可复制下方提问模板，到对话页继续生成优化标题。",
        }
    except Exception:
        ai_section = {
            "status": "error",
            "variants": [],
            "note": "AI 优化暂时不可用，可复制下方提问模板，到对话页继续生成优化标题。",
        }

    summary = {
        "headline": f"标题评分 {rule_result['score']}（{rule_result['verdict']}）",
        "score": rule_result["score"],
        "verdict": rule_result["verdict"],
        "length": rule_result["length"],
        "length_status": rule_result["length_status"],
    }
    details = {
        "issues": rule_result["issues"],
        "repeated_words": rule_result["repeated_words"],
        "missing_keywords": rule_result["missing_keywords"],
        "ai_variants": ai_section,
    }
    return {
        "summary": summary,
        "details": details,
        "prompt_template": prompt_template,
        "meta": {
            "tool": "title_diagnose",
            "tier": "rule+ai",
            "ai_used": ai_section.get("status") == "ok",
            "ai_status": ai_section.get("status"),
        },
    }


# --------------------------------------------------------------------------- #
# 工具 4: 关键词去重清洗 + 扩词（规则去重 + MiniMax 扩词）
# --------------------------------------------------------------------------- #

_KW_SPLIT_RE = re.compile(r"[,，;；、|\n\r\t]+")
_KW_MAX_CLEANED = 200
_KW_MAX_DUP_GROUPS = 40


def _normalize_kw(kw: str) -> str:
    return re.sub(r"\s+", " ", str(kw or "").strip()).strip()


def _kw_dedup_key(kw: str) -> str:
    low = kw.lower()
    low = re.sub(r"[^a-z0-9\u4e00-\u9fff ]+", " ", low)
    low = re.sub(r"\s+", " ", low).strip()
    if not low:
        return ""
    tokens = []
    for tok in low.split(" "):
        # 简单单复数归一：去掉非 ss 结尾的尾部 s
        if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
            tok = tok[:-1]
        tokens.append(tok)
    # 排序 token 以捕获仅词序不同的重复
    return " ".join(sorted(tokens))


def clean_and_expand_keywords(payload: dict[str, Any], *, client_ip: str) -> dict[str, Any]:
    raw = payload.get("keywords")
    if isinstance(raw, list):
        raw_text = "\n".join(str(x) for x in raw)
    else:
        raw_text = str(raw or "")
    if not raw_text.strip():
        raise ToolInputError("请粘贴需要清洗的关键词")
    if len(raw_text) > MAX_KEYWORD_INPUT_LENGTH:
        raise ToolInputError(f"关键词文本过长，请控制在 {MAX_KEYWORD_INPUT_LENGTH} 字符以内")

    site = str(payload.get("site") or "amazon").strip().lower()
    parts = [_normalize_kw(p) for p in _KW_SPLIT_RE.split(raw_text)]
    parts = [p for p in parts if p]
    input_count = len(parts)
    if input_count == 0:
        raise ToolInputError("没有解析到有效关键词，请用逗号或换行分隔")

    representative: dict[str, str] = {}
    members: dict[str, list[str]] = {}
    order: list[str] = []
    for token in parts:
        key = _kw_dedup_key(token) or token.lower()
        if key not in representative:
            representative[key] = token
            members[key] = [token]
            order.append(key)
        else:
            members[key].append(token)
            if len(token) > len(representative[key]):
                representative[key] = token

    cleaned = [representative[k] for k in order][:_KW_MAX_CLEANED]
    cleaned_count = len(order)
    removed_count = input_count - cleaned_count

    dup_groups: list[dict[str, Any]] = []
    for key in order:
        group = members[key]
        if len(group) <= 1:
            continue
        rep = representative[key]
        dropped: list[str] = []
        seen_rep = False
        for item in group:
            if item == rep and not seen_rep:
                seen_rep = True
                continue
            dropped.append(item)
        dup_groups.append({"kept": rep, "dropped": dropped})
        if len(dup_groups) >= _KW_MAX_DUP_GROUPS:
            break

    expansion: dict[str, Any] = {"status": "skipped", "groups": [], "count": 0}
    try:
        expansion = _expand_keywords(cleaned=cleaned, site=site, client_ip=client_ip)
        expansion["status"] = "ok"
    except ToolQuotaExceeded:
        expansion = {
            "status": "degraded",
            "groups": [],
            "count": 0,
            "note": "AI 扩词今日调用较多，已暂时降级。可复制下方提问模板，到对话页继续扩词。",
        }
    except Exception:
        expansion = {
            "status": "error",
            "groups": [],
            "count": 0,
            "note": "AI 扩词暂时不可用，去重结果仍可使用；可复制提问模板到对话页继续扩词。",
        }

    expanded_count = int(expansion.get("count") or 0)
    headline = f"清洗后 {cleaned_count} 个关键词（去重 {removed_count} 个）"
    if expansion.get("status") == "ok" and expanded_count:
        headline += f"，AI 扩展 {expanded_count} 个"

    prompt_template = (
        "请基于下面这组已去重的核心关键词，帮我做关键词扩展：补充长尾词、近义词和高转化场景词，"
        "按主题分组，并标注每个词的大致搜索意图。\n"
        f"- 站点: {site}\n"
        f"- 核心关键词（{cleaned_count} 个）: {('、'.join(cleaned[:60]))}"
    )

    return {
        "summary": {
            "headline": headline,
            "input_count": input_count,
            "cleaned_count": cleaned_count,
            "removed_count": removed_count,
            "expanded_count": expanded_count,
        },
        "details": {
            "cleaned": cleaned,
            "duplicates": dup_groups,
            "expansion": expansion,
        },
        "prompt_template": prompt_template,
        "meta": {
            "tool": "keyword_clean",
            "tier": "rule+ai",
            "ai_used": expansion.get("status") == "ok",
            "ai_status": expansion.get("status"),
        },
    }


# --------------------------------------------------------------------------- #
# 工具 5: 五点描述生成器（规则整理 + MiniMax 生成）
# --------------------------------------------------------------------------- #

_DESC_SITE_LANG = {
    "amazon": "英文",
    "tiktok": "英文",
    "temu": "英文",
    "default": "英文",
}


def generate_description(payload: dict[str, Any], *, client_ip: str) -> dict[str, Any]:
    product_name = str(payload.get("product_name") or payload.get("title") or "").strip()
    if not product_name:
        raise ToolInputError("请填写商品名称")
    if len(product_name) > 300:
        raise ToolInputError("商品名称过长，请控制在 300 字符以内")

    site = str(payload.get("site") or "amazon").strip().lower()
    audience = str(payload.get("audience") or "").strip()[:200]

    raw_points = payload.get("selling_points")
    if isinstance(raw_points, list):
        points_text = "\n".join(str(x) for x in raw_points)
    else:
        points_text = str(raw_points or "")
    if len(points_text) > MAX_KEYWORD_INPUT_LENGTH:
        raise ToolInputError(f"卖点文本过长，请控制在 {MAX_KEYWORD_INPUT_LENGTH} 字符以内")
    selling_points = [_normalize_kw(p) for p in _KW_SPLIT_RE.split(points_text)]
    selling_points = [p for p in selling_points if p][:12]

    keywords_raw = payload.get("keywords") or ""
    if isinstance(keywords_raw, list):
        keywords = [str(k).strip() for k in keywords_raw if str(k).strip()]
    else:
        keywords = [k.strip() for k in _KW_SPLIT_RE.split(str(keywords_raw)) if k.strip()]
    keywords = keywords[:12]

    ai_section: dict[str, Any] = {"status": "skipped", "bullets": [], "description": ""}
    try:
        ai_section = _generate_description(
            product_name=product_name,
            site=site,
            audience=audience,
            selling_points=selling_points,
            keywords=keywords,
            client_ip=client_ip,
        )
        ai_section["status"] = "ok"
    except ToolQuotaExceeded:
        ai_section = {
            "status": "degraded",
            "bullets": [],
            "description": "",
            "note": "AI 文案今日调用较多，已暂时降级。可复制下方提问模板，到对话页继续生成五点描述。",
        }
    except Exception:
        ai_section = {
            "status": "error",
            "bullets": [],
            "description": "",
            "note": "AI 文案暂时不可用，可复制下方提问模板，到对话页继续生成五点描述。",
        }

    bullet_count = len(ai_section.get("bullets") or [])
    if ai_section.get("status") == "ok" and bullet_count:
        headline = f"已生成 {bullet_count} 条卖点描述"
    else:
        headline = "卖点描述生成"

    lang = _DESC_SITE_LANG.get(site, _DESC_SITE_LANG["default"])
    prompt_template = (
        f"请为下面这个商品生成 5 条 {lang} 的卖点描述（Listing bullet points）和一段简短商品描述，"
        "每条卖点先用一个大写要点词，再补充具体说明，突出差异化和使用场景。\n"
        f"- 站点: {site}\n"
        f"- 商品名称: {product_name}\n"
        f"- 目标人群: {audience or '（未指定）'}\n"
        f"- 已有卖点: {('；'.join(selling_points)) or '（未提供，请合理发挥）'}\n"
        f"- 核心关键词: {('、'.join(keywords)) or '（无）'}"
    )

    return {
        "summary": {
            "headline": headline,
            "bullet_count": bullet_count,
        },
        "details": {
            "ai_description": ai_section,
            "input_points": selling_points,
        },
        "prompt_template": prompt_template,
        "meta": {
            "tool": "description_generator",
            "tier": "rule+ai",
            "ai_used": ai_section.get("status") == "ok",
            "ai_status": ai_section.get("status"),
        },
    }


# --------------------------------------------------------------------------- #
# 工具 6: 敏感词与合规检查（规则种子 + MiniMax 政策审查）
# --------------------------------------------------------------------------- #

MAX_COMPLIANCE_TEXT_LENGTH = 4000

# 高风险模式“种子”——不是大词表，只覆盖跨平台确定性强的几类。
# 命中即按规则提示；更细的政策判断交给 MiniMax。
_COMPLIANCE_RULES: list[dict[str, Any]] = [
    {
        "code": "cn_superlative",
        "category": "中国广告法极限词",
        "severity": "high",
        "pattern": re.compile(
            r"(最佳|最好|最优|最高|最低|最便宜|第一品牌|国家级|世界级|顶级|"
            r"绝无仅有|独一无二|史上最|全网最|百分之百|100%好评)",
        ),
        "hint": "疑似中国广告法极限词，建议替换为可量化或相对化表述。",
    },
    {
        "code": "absolute_claim",
        "category": "绝对化宣传",
        "severity": "high",
        "pattern": re.compile(
            r"\b(best|no\.?\s?1|number\s?one|#1|guaranteed|100%|"
            r"perfect|world'?s\s+best|top\s+rated|undisputed)\b",
            re.IGNORECASE,
        ),
        "hint": "绝对化/排名宣传，多数平台禁止无依据的最高级表述。",
    },
    {
        "code": "medical_claim",
        "category": "医疗/功效声明",
        "severity": "high",
        "pattern": re.compile(
            r"\b(cure|cures|treat|treats|heal|prevent\s+disease|"
            r"fda\s+approved|clinically\s+proven|anti[-\s]?bacterial|"
            r"kills?\s+(99|virus|bacteria)|medical[-\s]?grade)\b",
            re.IGNORECASE,
        ),
        "hint": "医疗/功效类声明需资质与证据，易触发平台审核或下架。",
    },
    {
        "code": "contact_redirect",
        "category": "站外联系/导流",
        "severity": "medium",
        "pattern": re.compile(
            r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|"
            r"https?://|www\.|微信|加微|whatsapp|telegram|"
            r"\+?\d[\d\s-]{7,}\d)",
            re.IGNORECASE,
        ),
        "hint": "包含联系方式/外链/导流信息，多数平台禁止站外引流。",
    },
    {
        "code": "restricted_category",
        "category": "受限类目信号",
        "severity": "medium",
        "pattern": re.compile(
            r"\b(cbd|thc|nicotine|vape|prescription|weapon|firearm|"
            r"pepper\s+spray|counterfeit|replica|knock[-\s]?off)\b",
            re.IGNORECASE,
        ),
        "hint": "疑似受限/敏感类目词，需确认平台类目政策与资质要求。",
    },
    {
        "code": "ip_infringement",
        "category": "疑似侵权/蹭品牌",
        "severity": "medium",
        "pattern": re.compile(
            r"\b(for\s+(apple|nike|disney|gucci|samsung)|"
            r"compatible\s+with\s+iphone|style\s+of|inspired\s+by)\b",
            re.IGNORECASE,
        ),
        "hint": "疑似蹭品牌/兼容性表述，需确认是否构成商标或外观侵权。",
    },
]

_SEVERITY_WEIGHT = {"high": 25, "medium": 12, "low": 5}


def _scan_compliance_rule(text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for rule in _COMPLIANCE_RULES:
        seen: set[str] = set()
        hits: list[str] = []
        for match in rule["pattern"].finditer(text):
            token = match.group(0).strip()
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            hits.append(token)
            if len(hits) >= 8:
                break
        if hits:
            findings.append(
                {
                    "code": rule["code"],
                    "category": rule["category"],
                    "severity": rule["severity"],
                    "matches": hits,
                    "hint": rule["hint"],
                }
            )
    return findings


def check_compliance(payload: dict[str, Any], *, client_ip: str) -> dict[str, Any]:
    text = str(payload.get("text") or payload.get("content") or "").strip()
    if not text:
        raise ToolInputError("请粘贴需要检查的文案")
    if len(text) > MAX_COMPLIANCE_TEXT_LENGTH:
        raise ToolInputError(f"文案过长，请控制在 {MAX_COMPLIANCE_TEXT_LENGTH} 字符以内")

    site = str(payload.get("site") or "amazon").strip().lower()
    rule_findings = _scan_compliance_rule(text)

    rule_score = 100
    for item in rule_findings:
        rule_score -= _SEVERITY_WEIGHT.get(item["severity"], 5) * min(len(item["matches"]), 3)
    rule_score = max(0, min(100, rule_score))
    high_count = sum(1 for f in rule_findings if f["severity"] == "high")

    ai_section: dict[str, Any] = {"status": "skipped", "findings": [], "overall": ""}
    try:
        ai_section = _review_compliance(text=text, site=site, client_ip=client_ip)
        ai_section["status"] = "ok"
    except ToolQuotaExceeded:
        ai_section = {
            "status": "degraded",
            "findings": [],
            "overall": "",
            "note": "AI 政策审查今日调用较多，已暂时降级。规则检查结果仍可参考；可复制提问模板到对话页继续。",
        }
    except Exception:
        ai_section = {
            "status": "error",
            "findings": [],
            "overall": "",
            "note": "AI 政策审查暂时不可用，规则检查结果仍可参考；可复制提问模板到对话页继续。",
        }

    if rule_findings or (ai_section.get("findings")):
        if high_count or any(
            f.get("severity") == "high" for f in (ai_section.get("findings") or [])
        ):
            verdict = "存在高风险表述，建议修改后再发布"
        else:
            verdict = "有需要注意的合规点，建议核对"
    else:
        verdict = "规则未命中明显敏感词"
        if ai_section.get("status") == "ok":
            verdict = "规则未命中明显敏感词，AI 也未发现重大问题"

    headline = f"规则命中 {len(rule_findings)} 类风险"
    if high_count:
        headline += f"（含 {high_count} 类高风险）"

    prompt_template = (
        "请基于目标平台政策，帮我审查这段商品文案是否有敏感词、违规宣传、医疗/绝对化声明、"
        "站外导流或侵权风险，逐条列出风险点、风险等级和合规改写建议。\n"
        f"- 站点: {site}\n"
        f"- 文案: {text[:1500]}"
    )

    return {
        "summary": {
            "headline": headline,
            "verdict": verdict,
            "rule_score": rule_score,
            "rule_hit_categories": len(rule_findings),
            "high_risk_count": high_count,
        },
        "details": {
            "rule_findings": rule_findings,
            "ai_review": ai_section,
        },
        "prompt_template": prompt_template,
        "meta": {
            "tool": "compliance_check",
            "tier": "rule+ai",
            "ai_used": ai_section.get("status") == "ok",
            "ai_status": ai_section.get("status"),
        },
    }


# --------------------------------------------------------------------------- #
# 工具 7: ACoS 盈亏平衡计算器（纯规则）
# --------------------------------------------------------------------------- #

def compute_acos_breakeven(payload: dict[str, Any]) -> dict[str, Any]:
    price = _coerce_float(payload.get("price"), "售价", required=True)
    if price <= 0:
        raise ToolInputError("售价需要大于 0")
    product_cost = _coerce_float(payload.get("product_cost"), "产品成本", required=True)
    fba_fee = _coerce_float(payload.get("fba_fee"), "FBA/履约费", required=False)
    referral_rate = _coerce_rate(payload.get("referral_rate"), "平台佣金比例", required=False, default=0.15)
    other_cost = _coerce_float(payload.get("other_cost"), "其他成本", required=False)
    target_margin = _coerce_rate(payload.get("target_margin"), "目标净利率", required=False, default=0.0)

    referral_fee = price * referral_rate
    unit_cost = product_cost + fba_fee + referral_fee + other_cost
    pre_ad_profit = price - unit_cost  # 未投广告时的单件毛利

    if pre_ad_profit <= 0:
        return {
            "summary": {
                "headline": "未投广告即亏损，无广告投放空间",
                "feasible": False,
                "pre_ad_profit": _round2(pre_ad_profit),
                "pre_ad_margin_pct": round((pre_ad_profit / price) * 100, 1),
            },
            "details": {
                "cost_breakdown": [
                    {"label": "产品成本", "value": _round2(product_cost)},
                    {"label": "FBA/履约费", "value": _round2(fba_fee)},
                    {"label": "平台佣金", "value": _round2(referral_fee)},
                    {"label": "其他成本", "value": _round2(other_cost)},
                ],
                "risk_note": "在没有广告的情况下单件已亏损，需要先优化成本或提价，再谈广告投放。",
            },
            "prompt_template": (
                "我的商品未投广告就已亏损，请帮我分析如何优化成本结构或定价，"
                f"使其有正向毛利再做广告。售价{_round2(price)}，单件成本{_round2(unit_cost)}。"
            ),
            "meta": {"tool": "acos_breakeven", "tier": "rule", "ai_used": False},
        }

    # 盈亏平衡 ACoS = 盈亏平衡前的单件毛利 / 售价
    breakeven_acos = pre_ad_profit / price
    breakeven_roas = (price / pre_ad_profit) if pre_ad_profit > 0 else None
    # 目标净利后的可承受 ACoS
    target_profit_amount = price * target_margin
    target_acos = max(0.0, (pre_ad_profit - target_profit_amount) / price)
    target_roas = (1.0 / target_acos) if target_acos > 0 else None

    headline = f"盈亏平衡 ACoS 约 {round(breakeven_acos * 100, 1)}%"

    return {
        "summary": {
            "headline": headline,
            "feasible": True,
            "pre_ad_profit": _round2(pre_ad_profit),
            "pre_ad_margin_pct": round((pre_ad_profit / price) * 100, 1),
            "breakeven_acos_pct": round(breakeven_acos * 100, 1),
            "breakeven_roas": _round2(breakeven_roas) if breakeven_roas else None,
        },
        "details": {
            "metric_ladder": [
                {
                    "label": "盈亏平衡 ACoS",
                    "value": f"{round(breakeven_acos * 100, 1)}%",
                    "scene": "广告花费占比到此值时单件不赚不亏，是广告 ACoS 的上限。",
                },
                {
                    "label": "盈亏平衡 ROAS",
                    "value": _round2(breakeven_roas) if breakeven_roas else "-",
                    "scene": "对应的最低广告投产比（销售额 / 广告花费）。",
                },
                {
                    "label": "目标净利后可承受 ACoS",
                    "value": f"{round(target_acos * 100, 1)}%",
                    "scene": "要保住目标净利率时，ACoS 不应超过此值。",
                },
                {
                    "label": "目标 ROAS 下限",
                    "value": _round2(target_roas) if target_roas else "-",
                    "scene": "要保住目标净利时的最低投产比。",
                },
            ],
            "cost_breakdown": [
                {"label": "产品成本", "value": _round2(product_cost)},
                {"label": "FBA/履约费", "value": _round2(fba_fee)},
                {"label": "平台佣金", "value": _round2(referral_fee)},
                {"label": "其他成本", "value": _round2(other_cost)},
            ],
            "unit_cost": _round2(unit_cost),
            "risk_note": (
                "实际投放 ACoS 应明显低于盈亏平衡值才有利润，建议预留缓冲。"
                if breakeven_acos < 0.2
                else "盈亏平衡 ACoS 较高，说明利润空间充足，可适当用广告抢量。"
            ),
        },
        "prompt_template": (
            "请基于下面的盈亏平衡数据，帮我制定广告投放策略和 ACoS 目标：\n"
            f"- 售价: {_round2(price)}\n"
            f"- 单件成本: {_round2(unit_cost)}\n"
            f"- 盈亏平衡 ACoS: {round(breakeven_acos * 100, 1)}%\n"
            f"- 目标净利率: {round(target_margin * 100, 1)}%"
        ),
        "meta": {"tool": "acos_breakeven", "tier": "rule", "ai_used": False},
    }


# --------------------------------------------------------------------------- #
# 工具 8: 体积重 / 计费重计算器（纯规则）
# --------------------------------------------------------------------------- #

# 常见物流体积重除数（cm³ -> kg），可按承运商调整
_DIM_DIVISORS = {
    "international_express": 5000,  # 国际快递 DHL/UPS/FedEx
    "air": 6000,                   # 空运
    "amazon": 5000,                # 亚马逊一般标准
    "express_express": 5000,
    "default": 5000,
}


def compute_dimensional_weight(payload: dict[str, Any]) -> dict[str, Any]:
    length = _coerce_float(payload.get("length"), "长(cm)", required=True)
    width = _coerce_float(payload.get("width"), "宽(cm)", required=True)
    height = _coerce_float(payload.get("height"), "高(cm)", required=True)
    actual_weight = _coerce_float(payload.get("actual_weight"), "实际重量(kg)", required=True)
    if length <= 0 or width <= 0 or height <= 0:
        raise ToolInputError("长宽高都需要大于 0")
    if actual_weight <= 0:
        raise ToolInputError("实际重量需要大于 0")

    carrier = str(payload.get("carrier") or "default").strip().lower()
    divisor_override = payload.get("divisor")
    if divisor_override not in (None, ""):
        divisor = _coerce_float(divisor_override, "体积重除数", required=False, default=0.0)
        if divisor <= 0:
            raise ToolInputError("体积重除数需要大于 0")
    else:
        divisor = _DIM_DIVISORS.get(carrier, _DIM_DIVISORS["default"])

    volume = length * width * height
    dim_weight = volume / divisor
    billable_weight = max(actual_weight, dim_weight)
    basis = "体积重" if dim_weight > actual_weight else "实际重量"

    rate_per_kg = payload.get("rate_per_kg")
    estimated_cost = None
    if rate_per_kg not in (None, ""):
        rate = _coerce_float(rate_per_kg, "运费单价(每kg)", required=False, default=0.0)
        if rate > 0:
            estimated_cost = _round2(billable_weight * rate)

    details: dict[str, Any] = {
        "metric_ladder": [
            {"label": "体积(cm³)", "value": _round2(volume)},
            {"label": "体积重(kg)", "value": _round2(dim_weight)},
            {"label": "实际重量(kg)", "value": _round2(actual_weight)},
            {"label": f"计费重量(kg) · 按{basis}", "value": _round2(billable_weight)},
        ],
        "divisor": divisor,
        "basis": basis,
        "risk_note": (
            f"该包裹按{basis}计费（除数 {int(divisor)}）。"
            + ("体积重大于实际重量，属抛货，建议优化包装尺寸以降低计费重。"
               if basis == "体积重"
               else "实际重量大于体积重，属重货，计费按实重。")
        ),
    }
    if estimated_cost is not None:
        details["estimated_cost"] = estimated_cost

    headline = f"计费重量 {_round2(billable_weight)} kg（按{basis}）"
    if estimated_cost is not None:
        headline += f"，预估运费 {estimated_cost}"

    return {
        "summary": {
            "headline": headline,
            "billable_weight": _round2(billable_weight),
            "dim_weight": _round2(dim_weight),
            "actual_weight": _round2(actual_weight),
            "basis": basis,
        },
        "details": details,
        "prompt_template": (
            "请帮我判断这个包裹的物流计费方式是否合理，以及如何优化包装降低计费重：\n"
            f"- 尺寸: {_round2(length)}×{_round2(width)}×{_round2(height)} cm\n"
            f"- 实际重量: {_round2(actual_weight)} kg\n"
            f"- 体积重: {_round2(dim_weight)} kg（除数 {int(divisor)}）\n"
            f"- 计费重: {_round2(billable_weight)} kg（按{basis}）"
        ),
        "meta": {"tool": "dimensional_weight", "tier": "rule", "ai_used": False},
    }


# --------------------------------------------------------------------------- #
# MiniMax 调用 + 配额保护
# --------------------------------------------------------------------------- #

def _today_key() -> int:
    return int(time.time() // 86400)


def _cache_key(tool: str, payload: dict[str, Any]) -> str:
    blob = json.dumps({"tool": tool, "payload": payload}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> dict[str, Any] | None:
    now = time.time()
    with _AI_GUARD_LOCK:
        entry = _AI_RESULT_CACHE.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if expires_at < now:
            _AI_RESULT_CACHE.pop(key, None)
            return None
        return value


def _cache_put(key: str, value: dict[str, Any]) -> None:
    with _AI_GUARD_LOCK:
        if len(_AI_RESULT_CACHE) >= _AI_CACHE_MAX_ENTRIES:
            # 简单淘汰：删掉最早过期的若干条
            for stale_key in sorted(_AI_RESULT_CACHE, key=lambda k: _AI_RESULT_CACHE[k][0])[:64]:
                _AI_RESULT_CACHE.pop(stale_key, None)
        _AI_RESULT_CACHE[key] = (time.time() + _AI_CACHE_TTL_SECONDS, value)


def _check_ai_quota(client_ip: str) -> None:
    now = time.time()
    today = _today_key()
    with _AI_GUARD_LOCK:
        if _AI_DAILY_COUNTER["day"] != today:
            _AI_DAILY_COUNTER["day"] = today
            _AI_DAILY_COUNTER["count"] = 0
        if _AI_DAILY_COUNTER["count"] >= _AI_DAILY_CALL_CAP:
            raise ToolQuotaExceeded("daily AI cap reached")

        bucket = _AI_IP_BUCKETS.setdefault(client_ip or "-", [])
        cutoff = now - _AI_RATE_LIMIT_WINDOW_SECONDS
        bucket[:] = [t for t in bucket if t >= cutoff]
        if len(bucket) >= _AI_RATE_LIMIT_MAX_CALLS:
            raise ToolQuotaExceeded("ip rate limit reached")
        bucket.append(now)
        _AI_DAILY_COUNTER["count"] += 1


def _generate_title_variants(
    *,
    title: str,
    site: str,
    brand: str,
    keywords: list[str],
    rule_result: dict[str, Any],
    client_ip: str,
) -> list[dict[str, str]]:
    cache_key = _cache_key(
        "title_variants",
        {"title": title, "site": site, "brand": brand, "keywords": keywords},
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached.get("variants", [])

    _check_ai_quota(client_ip)

    provider = build_llm_provider(
        "AGENT_ANTHROPIC",
        provider_default="anthropic_compatible",
        enabled_default=False,
    )
    if not provider.enabled or not provider.configured:
        raise RuntimeError("AGENT_ANTHROPIC provider not configured")

    system_prompt = (
        "你是跨境电商标题优化助手。请根据给定站点和原标题，输出 3 个更优的标题版本。"
        "要求：覆盖核心关键词、避免堆砌、长度适合该站点、信息完整。"
        '只返回 JSON，格式为 {"variants":[{"title":"...","scene":"适用场景","keep":"保留词","strengthen":"建议强化词"}]}。'
    )
    user_prompt = (
        f"站点: {site}\n"
        f"品牌词: {brand or '（无）'}\n"
        f"核心关键词: {('、'.join(keywords)) or '（无）'}\n"
        f"原标题: {title}\n"
        f"已发现的问题: {'；'.join(rule_result['issues']) or '无明显问题'}\n"
        "请给出 3 个优化版本。"
    )
    try:
        result = provider.json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
        )
    except LLMJSONParseError:
        raise RuntimeError("AI response parse failed")

    raw_variants = result.get("variants") if isinstance(result, dict) else None
    variants: list[dict[str, str]] = []
    if isinstance(raw_variants, list):
        for item in raw_variants[:3]:
            if not isinstance(item, dict):
                continue
            variant_title = str(item.get("title") or "").strip()
            if not variant_title:
                continue
            variants.append(
                {
                    "title": variant_title[:300],
                    "scene": str(item.get("scene") or "").strip()[:120],
                    "keep": str(item.get("keep") or "").strip()[:120],
                    "strengthen": str(item.get("strengthen") or "").strip()[:120],
                }
            )
    if not variants:
        raise RuntimeError("AI returned no usable variants")

    _cache_put(cache_key, {"variants": variants})
    return variants


def _expand_keywords(*, cleaned: list[str], site: str, client_ip: str) -> dict[str, Any]:
    seed = cleaned[:40]
    cache_key = _cache_key("kw_expand", {"seed": seed, "site": site})
    cached = _cache_get(cache_key)
    if cached is not None:
        return dict(cached)

    _check_ai_quota(client_ip)

    provider = build_llm_provider(
        "AGENT_ANTHROPIC",
        provider_default="anthropic_compatible",
        enabled_default=False,
    )
    if not provider.enabled or not provider.configured:
        raise RuntimeError("AGENT_ANTHROPIC provider not configured")

    system_prompt = (
        "你是跨境电商关键词研究助手。请基于给定站点和已有核心关键词，扩展相关长尾词、近义词和高转化场景词。"
        "要求：按主题分组，每组 3-8 个词，总数不超过 30 个，不要重复已有关键词，使用与站点匹配的语言。"
        '只返回 JSON，格式为 {"groups":[{"theme":"主题名","keywords":["词1","词2"]}]}。'
    )
    user_prompt = (
        f"站点: {site}\n"
        f"已有核心关键词: {('、'.join(seed)) or '（无）'}\n"
        "请扩展相关关键词并分组。"
    )
    try:
        result = provider.json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
        )
    except LLMJSONParseError:
        raise RuntimeError("AI response parse failed")

    raw_groups = result.get("groups") if isinstance(result, dict) else None
    groups: list[dict[str, Any]] = []
    total = 0
    existing = {kw.lower() for kw in cleaned}
    if isinstance(raw_groups, list):
        for grp in raw_groups[:8]:
            if not isinstance(grp, dict):
                continue
            theme = str(grp.get("theme") or "").strip()[:60]
            raw_kw = grp.get("keywords")
            words: list[str] = []
            if isinstance(raw_kw, list):
                for kw in raw_kw:
                    text = _normalize_kw(str(kw))
                    if not text or text.lower() in existing:
                        continue
                    existing.add(text.lower())
                    words.append(text[:80])
                    if len(words) >= 8:
                        break
            if words:
                groups.append({"theme": theme or "相关词", "keywords": words})
                total += len(words)
            if total >= 30:
                break

    if not groups:
        raise RuntimeError("AI returned no usable keywords")

    payload = {"groups": groups, "count": total}
    _cache_put(cache_key, payload)
    return dict(payload)


def _generate_description(
    *,
    product_name: str,
    site: str,
    audience: str,
    selling_points: list[str],
    keywords: list[str],
    client_ip: str,
) -> dict[str, Any]:
    cache_key = _cache_key(
        "description",
        {
            "product_name": product_name,
            "site": site,
            "audience": audience,
            "selling_points": selling_points,
            "keywords": keywords,
        },
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return dict(cached)

    _check_ai_quota(client_ip)

    provider = build_llm_provider(
        "AGENT_ANTHROPIC",
        provider_default="anthropic_compatible",
        enabled_default=False,
    )
    if not provider.enabled or not provider.configured:
        raise RuntimeError("AGENT_ANTHROPIC provider not configured")

    lang = _DESC_SITE_LANG.get(site, _DESC_SITE_LANG["default"])
    system_prompt = (
        "你是跨境电商 Listing 文案专家。请根据商品信息生成 5 条卖点描述（bullet points）和一段简短商品描述。"
        f"输出语言使用{lang}。每条卖点先用一个简短的大写要点词（headline），再补充一句具体说明（detail），"
        "突出差异化、材质/功能和使用场景，自然融入关键词，不要堆砌、不要虚假宣传。"
        '只返回 JSON，格式为 {"bullets":[{"headline":"...","detail":"..."}],"description":"..."}。'
    )
    user_prompt = (
        f"站点: {site}\n"
        f"商品名称: {product_name}\n"
        f"目标人群: {audience or '（未指定）'}\n"
        f"已有卖点: {('；'.join(selling_points)) or '（未提供，请基于商品名合理发挥）'}\n"
        f"核心关键词: {('、'.join(keywords)) or '（无）'}\n"
        "请生成 5 条卖点和一段简短描述。"
    )
    try:
        result = provider.json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.6,
        )
    except LLMJSONParseError:
        raise RuntimeError("AI response parse failed")

    raw_bullets = result.get("bullets") if isinstance(result, dict) else None
    bullets: list[dict[str, str]] = []
    if isinstance(raw_bullets, list):
        for item in raw_bullets[:5]:
            if isinstance(item, dict):
                headline = str(item.get("headline") or "").strip()
                detail = str(item.get("detail") or "").strip()
            else:
                headline = ""
                detail = str(item).strip()
            if not headline and not detail:
                continue
            bullets.append({"headline": headline[:80], "detail": detail[:300]})
    if not bullets:
        raise RuntimeError("AI returned no usable bullets")

    description = ""
    if isinstance(result, dict):
        description = str(result.get("description") or "").strip()[:800]

    payload = {"bullets": bullets, "description": description}
    _cache_put(cache_key, payload)
    return dict(payload)


def _review_compliance(*, text: str, site: str, client_ip: str) -> dict[str, Any]:
    cache_key = _cache_key("compliance", {"text": text, "site": site})
    cached = _cache_get(cache_key)
    if cached is not None:
        return dict(cached)

    _check_ai_quota(client_ip)

    provider = build_llm_provider(
        "AGENT_ANTHROPIC",
        provider_default="anthropic_compatible",
        enabled_default=False,
    )
    if not provider.enabled or not provider.configured:
        raise RuntimeError("AGENT_ANTHROPIC provider not configured")

    system_prompt = (
        "你是跨境电商合规审查助手，熟悉 Amazon、TikTok Shop、Temu 等平台政策与中国广告法。"
        "请审查给定商品文案，找出敏感词、违规宣传、医疗/绝对化声明、站外导流、商标/外观侵权、"
        "受限类目等风险。对每个风险点给出：风险类别、风险等级(high/medium/low)、命中片段、合规改写建议。"
        '只返回 JSON，格式为 {"findings":[{"category":"...","severity":"high","snippet":"...","suggestion":"..."}],"overall":"一句话总体结论"}。'
        "没有风险时 findings 返回空数组。"
    )
    user_prompt = (
        f"目标平台: {site}\n"
        f"待审查文案:\n{text}\n"
        "请逐条列出风险点和改写建议。"
    )
    try:
        result = provider.json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
    except LLMJSONParseError:
        raise RuntimeError("AI response parse failed")

    raw_findings = result.get("findings") if isinstance(result, dict) else None
    findings: list[dict[str, str]] = []
    if isinstance(raw_findings, list):
        for item in raw_findings[:12]:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            suggestion = str(item.get("suggestion") or "").strip()
            severity = str(item.get("severity") or "medium").strip().lower()
            if severity not in ("high", "medium", "low"):
                severity = "medium"
            if not category and not snippet and not suggestion:
                continue
            findings.append(
                {
                    "category": category[:60] or "风险点",
                    "severity": severity,
                    "snippet": snippet[:160],
                    "suggestion": suggestion[:240],
                }
            )

    overall = ""
    if isinstance(result, dict):
        overall = str(result.get("overall") or "").strip()[:240]

    payload = {"findings": findings, "overall": overall}
    _cache_put(cache_key, payload)
    return dict(payload)


# --------------------------------------------------------------------------- #
# 工具 9: 多站点含税到手价换算（纯规则）
# --------------------------------------------------------------------------- #

def compute_landed_price(payload: dict[str, Any]) -> dict[str, Any]:
    product_cost = _coerce_float(payload.get("product_cost"), "商品成本", required=True)
    if product_cost <= 0:
        raise ToolInputError("商品成本需要大于 0")
    shipping_cost = _coerce_float(payload.get("shipping_cost"), "物流/头程", required=False)
    other_fee = _coerce_float(payload.get("other_fee"), "其他费用", required=False)
    exchange_rate = _coerce_float(payload.get("exchange_rate"), "汇率", required=False, default=1.0)
    if exchange_rate <= 0:
        exchange_rate = 1.0
    duty_rate = _coerce_rate(payload.get("duty_rate"), "关税率", required=False)
    vat_rate = _coerce_rate(payload.get("vat_rate"), "增值税/VAT", required=False)
    platform_fee_rate = _coerce_rate(payload.get("platform_fee_rate"), "平台佣金比例", required=False)
    target_margin = _coerce_rate(payload.get("target_margin"), "目标毛利率", required=False)

    # CIF 货值（目标币种）= (成本 + 物流 + 其他) × 汇率
    cif = (product_cost + shipping_cost + other_fee) * exchange_rate
    duty = cif * duty_rate
    # 进口增值税一般以 (CIF + 关税) 为税基
    vat = (cif + duty) * vat_rate
    landed_cost = cif + duty + vat

    ladder: list[dict[str, Any]] = [
        {"label": "CIF 货值(目标币种)", "value": _round2(cif), "scene": "采购+物流+其他费用按汇率折算后的到岸货值。"},
        {"label": "进口关税", "value": _round2(duty), "scene": f"按关税率 {round(duty_rate * 100, 1)}% 计算。"},
        {"label": "进口增值税/VAT", "value": _round2(vat), "scene": f"按 VAT {round(vat_rate * 100, 1)}%，税基为 CIF+关税。"},
        {"label": "含税到手成本", "value": _round2(landed_cost), "scene": "落地后的单件全成本，是定价的底线。"},
    ]

    denom = 1 - platform_fee_rate - target_margin
    suggested_price = None
    if (platform_fee_rate or target_margin) and denom > 0:
        suggested_price = landed_cost / denom
        ladder.append({
            "label": "建议零售价",
            "value": _round2(suggested_price),
            "scene": f"覆盖平台佣金 {round(platform_fee_rate * 100, 1)}% 并保住目标毛利 {round(target_margin * 100, 1)}% 的定价。",
        })

    headline = f"含税到手成本 {_round2(landed_cost)}（目标币种）"
    if suggested_price is not None:
        headline += f"，建议零售价 {_round2(suggested_price)}"

    risk_note = (
        "关税或 VAT 占比偏高，落地成本被显著抬高，定价时要留足税务缓冲。"
        if landed_cost > cif * 1.2
        else "税费占比适中，落地成本接近货值，可按常规定价策略推进。"
    )
    if denom <= 0 and (platform_fee_rate or target_margin):
        risk_note = "平台佣金与目标毛利合计已≥100%，无法反推出建议零售价，请下调目标毛利或佣金占比。"

    return {
        "summary": {
            "headline": headline,
            "landed_cost": _round2(landed_cost),
            "duty": _round2(duty),
            "vat": _round2(vat),
            "suggested_price": _round2(suggested_price) if suggested_price is not None else None,
        },
        "details": {
            "metric_ladder": ladder,
            "cost_breakdown": [
                {"label": "商品成本(源币种)", "value": _round2(product_cost)},
                {"label": "物流/头程", "value": _round2(shipping_cost)},
                {"label": "其他费用", "value": _round2(other_fee)},
                {"label": "汇率", "value": _round2(exchange_rate)},
            ],
            "risk_note": risk_note,
        },
        "prompt_template": (
            "请基于下面的含税到手成本，帮我判断在目标站点的合理定价与利润空间：\n"
            f"- 含税到手成本: {_round2(landed_cost)}（目标币种）\n"
            f"- 其中关税: {_round2(duty)}，VAT: {_round2(vat)}\n"
            f"- 平台佣金比例: {round(platform_fee_rate * 100, 1)}%，目标毛利率: {round(target_margin * 100, 1)}%"
            + (f"\n- 当前建议零售价: {_round2(suggested_price)}" if suggested_price is not None else "")
        ),
        "meta": {"tool": "landed_price", "tier": "rule", "ai_used": False},
    }


# --------------------------------------------------------------------------- #
# 工具 10: Listing 健康度评分（纯规则，复用标题诊断规则）
# --------------------------------------------------------------------------- #

def score_listing_health(payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip()
    if not title:
        raise ToolInputError("请填写商品标题")
    if len(title) > MAX_TITLE_LENGTH:
        raise ToolInputError(f"标题过长，请控制在 {MAX_TITLE_LENGTH} 字符以内")
    site = str(payload.get("site") or "amazon").strip().lower()
    brand = str(payload.get("brand") or "").strip()[:60]

    keywords_raw = payload.get("keywords") or ""
    if isinstance(keywords_raw, list):
        keywords = [str(k).strip() for k in keywords_raw if str(k).strip()]
    else:
        keywords = [k.strip() for k in _KW_SPLIT_RE.split(str(keywords_raw)) if k.strip()]
    keywords = keywords[:12]

    bullets_raw = payload.get("bullets") or payload.get("selling_points") or ""
    if isinstance(bullets_raw, list):
        bullets_text = "\n".join(str(x) for x in bullets_raw)
    else:
        bullets_text = str(bullets_raw)
    if len(bullets_text) > MAX_KEYWORD_INPUT_LENGTH:
        raise ToolInputError(f"五点描述过长，请控制在 {MAX_KEYWORD_INPUT_LENGTH} 字符以内")
    bullets = [_normalize_kw(b) for b in re.split(r"[\n\r]+", bullets_text)]
    bullets = [b for b in bullets if b][:10]

    issues: list[str] = []

    # 1) 标题评分（复用规则）
    title_rule = _diagnose_title_rule(title, site, brand, keywords)
    title_score = int(title_rule["score"])
    for it in title_rule["issues"]:
        issues.append("标题：" + it)

    # 2) 五点评分
    bullet_count = len(bullets)
    if bullet_count == 0:
        bullet_score = 0
        issues.append("五点描述：未填写，建议补齐 5 条卖点。")
    else:
        bullet_score = 100
        if bullet_count < 5:
            bullet_score -= (5 - bullet_count) * 12
            issues.append(f"五点描述：只有 {bullet_count} 条，建议补齐到 5 条。")
        short_bullets = [b for b in bullets if len(b) < 40]
        if short_bullets:
            bullet_score -= min(20, len(short_bullets) * 6)
            issues.append(f"五点描述：有 {len(short_bullets)} 条偏短，建议补充材质/功能/场景细节。")
        bullet_score = max(0, bullet_score)

    # 3) 关键词覆盖
    combined = (title + " " + " ".join(bullets)).lower()
    keyword_score = None
    covered: list[str] = []
    missing: list[str] = []
    if keywords:
        for kw in keywords:
            (covered if kw.lower() in combined else missing).append(kw)
        keyword_score = round(len(covered) / len(keywords) * 100)
        if missing:
            issues.append("关键词覆盖：以下核心词未出现在标题或五点中：" + "、".join(missing[:6]))

    # 综合分（标题 0.4 / 五点 0.3 / 关键词 0.3，按可用项归一）
    weights = {"title": 0.4, "bullet": 0.3, "keyword": 0.3}
    scores = {"title": title_score, "bullet": bullet_score}
    if keyword_score is not None:
        scores["keyword"] = keyword_score
    total_w = sum(weights[k] for k in scores)
    composite = round(sum(scores[k] * weights[k] for k in scores) / total_w)
    composite = max(0, min(100, composite))

    if composite >= 85:
        verdict = "Listing 健康度较好"
    elif composite >= 70:
        verdict = "Listing 基本健康，有优化空间"
    elif composite >= 50:
        verdict = "Listing 存在明显短板，建议优化"
    else:
        verdict = "Listing 问题较多，建议系统性重做"

    ladder = [
        {"label": "综合健康分", "value": composite, "scene": verdict},
        {"label": "标题分", "value": title_score, "scene": title_rule["verdict"]},
        {"label": "五点分", "value": bullet_score, "scene": f"已填写 {bullet_count} 条卖点。"},
    ]
    if keyword_score is not None:
        ladder.append({
            "label": "关键词覆盖",
            "value": f"{keyword_score}%",
            "scene": f"{len(covered)}/{len(keywords)} 个核心词被覆盖。",
        })

    return {
        "summary": {
            "headline": f"Listing 健康分 {composite}（{verdict}）",
            "score": composite,
            "verdict": verdict,
            "title_score": title_score,
            "bullet_score": bullet_score,
            "keyword_coverage_pct": keyword_score,
        },
        "details": {
            "metric_ladder": ladder,
            "issues": issues,
            "covered_keywords": covered,
            "missing_keywords": missing,
            "risk_note": (
                "综合分较高，可在细节上继续打磨；重点保持关键词覆盖与卖点完整。"
                if composite >= 70
                else "综合分偏低，建议优先补齐五点和关键词覆盖，再优化标题。"
            ),
        },
        "prompt_template": (
            "请基于下面的 Listing 健康度评分，帮我系统优化标题、五点和关键词覆盖：\n"
            f"- 综合健康分: {composite}（{verdict}）\n"
            f"- 标题分: {title_score}，五点分: {bullet_score}"
            + (f"，关键词覆盖: {keyword_score}%" if keyword_score is not None else "")
            + f"\n- 主要短板: {'；'.join(issues[:6]) or '无明显短板'}"
        ),
        "meta": {"tool": "listing_health", "tier": "rule", "ai_used": False},
    }


# --------------------------------------------------------------------------- #
# 内容类工具共用：长文输入边界 + 高频词提取（规则层）
# --------------------------------------------------------------------------- #

MAX_LONG_TEXT_LENGTH = 8000

_CONTENT_STOPWORDS = _TITLE_STOPWORDS | {
    "this", "that", "these", "those", "it", "its", "they", "them", "have",
    "has", "had", "was", "were", "be", "been", "but", "not", "very", "so",
    "i", "me", "my", "we", "us", "he", "she", "his", "her", "as", "at", "if",
    "all", "out", "up", "do", "does", "did", "will", "can", "just", "than",
    "too", "also", "get", "got", "one", "two", "would", "could", "really",
    "product", "item", "amazon", "use", "used", "using", "well", "much",
}


def _top_tokens(text: str, *, limit: int = 15, min_len: int = 3) -> list[dict[str, Any]]:
    freq: dict[str, int] = {}
    for tok in re.findall(r"[A-Za-z][A-Za-z'\-]+", str(text or "")):
        low = tok.lower()
        if len(low) < min_len or low in _CONTENT_STOPWORDS:
            continue
        freq[low] = freq.get(low, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"word": w, "count": c} for w, c in ranked[:limit]]


def _split_blocks(text: str, *, limit: int = 6) -> list[str]:
    parts = re.split(r"(?:\n\s*\n|\n?-{3,}\n?|\n?={3,}\n?)", str(text or ""))
    blocks = [re.sub(r"\s+", " ", p).strip() for p in parts]
    blocks = [b for b in blocks if b]
    return blocks[:limit]


def _ai_provider_or_raise():
    provider = build_llm_provider(
        "AGENT_ANTHROPIC",
        provider_default="anthropic_compatible",
        enabled_default=False,
    )
    if not provider.enabled or not provider.configured:
        raise RuntimeError("AGENT_ANTHROPIC provider not configured")
    return provider


def _degraded_section(action: str) -> dict[str, Any]:
    return {
        "status": "degraded",
        "note": f"AI {action}今日调用较多，已暂时降级。可复制下方提问模板，到对话页继续。",
    }


def _error_section(action: str) -> dict[str, Any]:
    return {
        "status": "error",
        "note": f"AI {action}暂时不可用，可复制下方提问模板，到对话页继续。",
    }


# --------------------------------------------------------------------------- #
# 工具 11: 竞品标题/卖点差异提取（规则高频词 + MiniMax 差异分析）
# --------------------------------------------------------------------------- #

def _ai_competitor_gaps(*, my_listing: str, competitors: list[str], site: str, client_ip: str) -> dict[str, Any]:
    cache_key = _cache_key("competitor_gaps", {"my": my_listing, "comp": competitors, "site": site})
    cached = _cache_get(cache_key)
    if cached is not None:
        return dict(cached)
    _check_ai_quota(client_ip)
    provider = _ai_provider_or_raise()

    system_prompt = (
        "你是跨境电商竞品分析助手。请对比我方 listing 与 2-3 个竞品 listing，找出差异化卖点缺口。"
        "重点输出：竞品普遍强调但我方缺失的卖点(gaps)、竞品共同宣称的卖点(common_claims)、"
        "我方可切入的差异化机会(opportunities)。"
        '只返回 JSON，格式为 {"gaps":[{"point":"缺口卖点","suggestion":"补强建议"}],'
        '"common_claims":["共同卖点1"],"opportunities":["差异化机会1"],"overall":"一句话结论"}。'
    )
    comp_text = "\n\n---\n\n".join(f"竞品{i+1}: {c}" for i, c in enumerate(competitors))
    user_prompt = (
        f"站点: {site}\n"
        f"我方 listing: {my_listing or '（未提供，请基于竞品共性反推我方可能的缺口）'}\n\n"
        f"竞品 listing：\n{comp_text}\n\n"
        "请提炼差异化卖点缺口。"
    )
    try:
        result = provider.json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
        )
    except LLMJSONParseError:
        raise RuntimeError("AI response parse failed")

    def _str_list(key: str, cap: int) -> list[str]:
        raw = result.get(key) if isinstance(result, dict) else None
        out: list[str] = []
        if isinstance(raw, list):
            for x in raw[:cap]:
                s = str(x).strip()
                if s:
                    out.append(s[:160])
        return out

    gaps: list[dict[str, str]] = []
    raw_gaps = result.get("gaps") if isinstance(result, dict) else None
    if isinstance(raw_gaps, list):
        for item in raw_gaps[:10]:
            if isinstance(item, dict):
                point = str(item.get("point") or "").strip()
                suggestion = str(item.get("suggestion") or "").strip()
            else:
                point = str(item).strip()
                suggestion = ""
            if point:
                gaps.append({"point": point[:160], "suggestion": suggestion[:240]})
    if not gaps and not _str_list("common_claims", 1):
        raise RuntimeError("AI returned no usable competitor analysis")

    overall = str(result.get("overall") or "").strip()[:240] if isinstance(result, dict) else ""
    payload = {
        "gaps": gaps,
        "common_claims": _str_list("common_claims", 12),
        "opportunities": _str_list("opportunities", 10),
        "overall": overall,
    }
    _cache_put(cache_key, payload)
    return dict(payload)


def extract_competitor_gaps(payload: dict[str, Any], *, client_ip: str) -> dict[str, Any]:
    competitors_raw = payload.get("competitors") or payload.get("competitor_listings") or ""
    if isinstance(competitors_raw, list):
        competitors_text = "\n\n---\n\n".join(str(x) for x in competitors_raw)
    else:
        competitors_text = str(competitors_raw)
    if not competitors_text.strip():
        raise ToolInputError("请粘贴 2-3 个竞品的标题/卖点")
    if len(competitors_text) > MAX_LONG_TEXT_LENGTH:
        raise ToolInputError(f"竞品文本过长，请控制在 {MAX_LONG_TEXT_LENGTH} 字符以内")

    site = str(payload.get("site") or "amazon").strip().lower()
    my_listing = str(payload.get("my_listing") or payload.get("my") or "").strip()[:2000]
    competitors = _split_blocks(competitors_text, limit=5)
    if len(competitors) < 1:
        raise ToolInputError("没有解析到竞品内容，请用空行或 --- 分隔不同竞品")

    rule_common = _top_tokens(competitors_text, limit=15)

    ai_section: dict[str, Any] = {"status": "skipped"}
    try:
        ai_section = _ai_competitor_gaps(
            my_listing=my_listing, competitors=competitors, site=site, client_ip=client_ip
        )
        ai_section["status"] = "ok"
    except ToolQuotaExceeded:
        ai_section = _degraded_section("竞品分析")
    except Exception:
        ai_section = _error_section("竞品分析")

    gap_count = len(ai_section.get("gaps") or [])
    headline = f"已对比 {len(competitors)} 个竞品"
    if ai_section.get("status") == "ok" and gap_count:
        headline += f"，发现 {gap_count} 个差异化缺口"

    prompt_template = (
        "请对比下面的竞品 listing，找出竞品普遍强调但我方缺失的差异化卖点，并给出补强建议。\n"
        f"- 站点: {site}\n"
        f"- 我方 listing: {my_listing or '（未提供）'}\n"
        f"- 竞品高频词: {('、'.join(t['word'] for t in rule_common[:12])) or '（无）'}\n"
        f"- 竞品内容: \n{competitors_text[:1500]}"
    )

    return {
        "summary": {"headline": headline, "competitor_count": len(competitors), "gap_count": gap_count},
        "details": {"rule_common": rule_common, "ai": ai_section},
        "prompt_template": prompt_template,
        "meta": {
            "tool": "competitor_gaps",
            "tier": "rule+ai",
            "ai_used": ai_section.get("status") == "ok",
            "ai_status": ai_section.get("status"),
        },
    }


# --------------------------------------------------------------------------- #
# 工具 12: A+ / 详情页文案大纲生成（规则整理 + MiniMax 模块化大纲）
# --------------------------------------------------------------------------- #

def _ai_aplus_outline(
    *, product_name: str, site: str, audience: str, selling_points: list[str], client_ip: str
) -> dict[str, Any]:
    cache_key = _cache_key(
        "aplus_outline",
        {"name": product_name, "site": site, "audience": audience, "points": selling_points},
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return dict(cached)
    _check_ai_quota(client_ip)
    provider = _ai_provider_or_raise()

    system_prompt = (
        "你是跨境电商 A+ / 详情页文案策划。请根据商品信息，规划一套模块化的 A+ 详情页大纲，"
        "通常包含品牌故事/痛点引入、核心卖点、功能细节、使用场景、规格参数、对比/信任背书等模块。"
        "每个模块给出：模块名(name)、本模块目标(goal)、建议文案要点(copy)、配图建议(image)。"
        '只返回 JSON，格式为 {"modules":[{"name":"...","goal":"...","copy":"...","image":"..."}],"overall":"一句话排版建议"}。'
        "模块数量 5-7 个，文案要点用英文，其余说明可用中文。"
    )
    user_prompt = (
        f"站点: {site}\n"
        f"商品名称: {product_name}\n"
        f"目标人群: {audience or '（未指定）'}\n"
        f"核心卖点: {('；'.join(selling_points)) or '（未提供，请基于商品名合理发挥）'}\n"
        "请输出模块化 A+ 大纲。"
    )
    try:
        result = provider.json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.55,
        )
    except LLMJSONParseError:
        raise RuntimeError("AI response parse failed")

    raw_modules = result.get("modules") if isinstance(result, dict) else None
    modules: list[dict[str, str]] = []
    if isinstance(raw_modules, list):
        for item in raw_modules[:8]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            modules.append({
                "name": name[:80],
                "goal": str(item.get("goal") or "").strip()[:160],
                "copy": str(item.get("copy") or "").strip()[:400],
                "image": str(item.get("image") or "").strip()[:200],
            })
    if not modules:
        raise RuntimeError("AI returned no usable modules")

    overall = str(result.get("overall") or "").strip()[:240] if isinstance(result, dict) else ""
    payload = {"modules": modules, "overall": overall}
    _cache_put(cache_key, payload)
    return dict(payload)


def generate_aplus_outline(payload: dict[str, Any], *, client_ip: str) -> dict[str, Any]:
    product_name = str(payload.get("product_name") or payload.get("title") or "").strip()
    if not product_name:
        raise ToolInputError("请填写商品名称")
    if len(product_name) > 300:
        raise ToolInputError("商品名称过长，请控制在 300 字符以内")

    site = str(payload.get("site") or "amazon").strip().lower()
    audience = str(payload.get("audience") or "").strip()[:200]

    points_raw = payload.get("selling_points")
    if isinstance(points_raw, list):
        points_text = "\n".join(str(x) for x in points_raw)
    else:
        points_text = str(points_raw or "")
    if len(points_text) > MAX_KEYWORD_INPUT_LENGTH:
        raise ToolInputError(f"卖点文本过长，请控制在 {MAX_KEYWORD_INPUT_LENGTH} 字符以内")
    selling_points = [_normalize_kw(p) for p in _KW_SPLIT_RE.split(points_text)]
    selling_points = [p for p in selling_points if p][:12]

    ai_section: dict[str, Any] = {"status": "skipped"}
    try:
        ai_section = _ai_aplus_outline(
            product_name=product_name, site=site, audience=audience,
            selling_points=selling_points, client_ip=client_ip,
        )
        ai_section["status"] = "ok"
    except ToolQuotaExceeded:
        ai_section = _degraded_section("A+ 大纲")
    except Exception:
        ai_section = _error_section("A+ 大纲")

    module_count = len(ai_section.get("modules") or [])
    headline = f"已生成 {module_count} 个 A+ 模块大纲" if module_count else "A+ 详情页大纲"

    prompt_template = (
        "请为下面这个商品规划一套模块化 A+ / 详情页大纲（5-7 个模块），"
        "每个模块给出模块名、目标、文案要点和配图建议。\n"
        f"- 站点: {site}\n"
        f"- 商品名称: {product_name}\n"
        f"- 目标人群: {audience or '（未指定）'}\n"
        f"- 核心卖点: {('；'.join(selling_points)) or '（未提供）'}"
    )

    return {
        "summary": {"headline": headline, "module_count": module_count},
        "details": {"ai": ai_section, "input_points": selling_points},
        "prompt_template": prompt_template,
        "meta": {
            "tool": "aplus_outline",
            "tier": "rule+ai",
            "ai_used": ai_section.get("status") == "ok",
            "ai_status": ai_section.get("status"),
        },
    }


# --------------------------------------------------------------------------- #
# 工具 13: Review 关键词 / 差评归因提炼（规则高频词 + MiniMax 归因）
# --------------------------------------------------------------------------- #

def _ai_mine_reviews(*, reviews: str, product_name: str, client_ip: str) -> dict[str, Any]:
    cache_key = _cache_key("mine_reviews", {"reviews": reviews, "name": product_name})
    cached = _cache_get(cache_key)
    if cached is not None:
        return dict(cached)
    _check_ai_quota(client_ip)
    provider = _ai_provider_or_raise()

    system_prompt = (
        "你是跨境电商评论分析助手。请分析给定的用户评论，提炼两类信息："
        "1) 高频好评卖点(praises)——用户反复称赞的卖点关键词及说明；"
        "2) 差评归因(complaints)——质量/物流/描述不符等问题，标注严重度(high/medium/low)与改进建议。"
        '只返回 JSON，格式为 {"praises":[{"keyword":"...","note":"..."}],'
        '"complaints":[{"issue":"...","severity":"high","suggestion":"..."}],"overall":"一句话总体结论"}。'
    )
    user_prompt = (
        f"商品: {product_name or '（未指定）'}\n"
        f"用户评论：\n{reviews}\n"
        "请提炼好评卖点和差评归因。"
    )
    try:
        result = provider.json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
    except LLMJSONParseError:
        raise RuntimeError("AI response parse failed")

    praises: list[dict[str, str]] = []
    raw_p = result.get("praises") if isinstance(result, dict) else None
    if isinstance(raw_p, list):
        for item in raw_p[:12]:
            if isinstance(item, dict):
                keyword = str(item.get("keyword") or "").strip()
                note = str(item.get("note") or "").strip()
            else:
                keyword = str(item).strip()
                note = ""
            if keyword:
                praises.append({"keyword": keyword[:80], "note": note[:200]})

    complaints: list[dict[str, str]] = []
    raw_c = result.get("complaints") if isinstance(result, dict) else None
    if isinstance(raw_c, list):
        for item in raw_c[:12]:
            if not isinstance(item, dict):
                continue
            issue = str(item.get("issue") or "").strip()
            if not issue:
                continue
            severity = str(item.get("severity") or "medium").strip().lower()
            if severity not in ("high", "medium", "low"):
                severity = "medium"
            complaints.append({
                "issue": issue[:160],
                "severity": severity,
                "suggestion": str(item.get("suggestion") or "").strip()[:240],
            })

    if not praises and not complaints:
        raise RuntimeError("AI returned no usable review analysis")

    overall = str(result.get("overall") or "").strip()[:240] if isinstance(result, dict) else ""
    payload = {"praises": praises, "complaints": complaints, "overall": overall}
    _cache_put(cache_key, payload)
    return dict(payload)


def mine_reviews(payload: dict[str, Any], *, client_ip: str) -> dict[str, Any]:
    reviews_raw = payload.get("reviews") or payload.get("text") or ""
    if isinstance(reviews_raw, list):
        reviews_text = "\n".join(str(x) for x in reviews_raw)
    else:
        reviews_text = str(reviews_raw)
    if not reviews_text.strip():
        raise ToolInputError("请粘贴需要分析的评论")
    if len(reviews_text) > MAX_LONG_TEXT_LENGTH:
        raise ToolInputError(f"评论文本过长，请控制在 {MAX_LONG_TEXT_LENGTH} 字符以内")

    product_name = str(payload.get("product_name") or "").strip()[:200]
    review_lines = [ln for ln in re.split(r"[\n\r]+", reviews_text) if ln.strip()]
    rule_keywords = _top_tokens(reviews_text, limit=18)

    ai_section: dict[str, Any] = {"status": "skipped"}
    try:
        ai_section = _ai_mine_reviews(reviews=reviews_text, product_name=product_name, client_ip=client_ip)
        ai_section["status"] = "ok"
    except ToolQuotaExceeded:
        ai_section = _degraded_section("评论分析")
    except Exception:
        ai_section = _error_section("评论分析")

    complaint_count = len(ai_section.get("complaints") or [])
    praise_count = len(ai_section.get("praises") or [])
    headline = f"已分析 {len(review_lines)} 条评论"
    if ai_section.get("status") == "ok":
        headline += f"，好评卖点 {praise_count} / 差评点 {complaint_count}"

    prompt_template = (
        "请分析下面的用户评论，提炼高频好评卖点（可用于 listing）和差评归因（质量/物流/描述不符）及改进建议。\n"
        f"- 商品: {product_name or '（未指定）'}\n"
        f"- 高频词: {('、'.join(t['word'] for t in rule_keywords[:12])) or '（无）'}\n"
        f"- 评论: \n{reviews_text[:1500]}"
    )

    return {
        "summary": {
            "headline": headline,
            "review_count": len(review_lines),
            "praise_count": praise_count,
            "complaint_count": complaint_count,
        },
        "details": {"rule_keywords": rule_keywords, "ai": ai_section},
        "prompt_template": prompt_template,
        "meta": {
            "tool": "review_mining",
            "tier": "rule+ai",
            "ai_used": ai_section.get("status") == "ok",
            "ai_status": ai_section.get("status"),
        },
    }


# --------------------------------------------------------------------------- #
# 工具 14: 退货原因话术 / 客服回复模板（场景规则 + MiniMax 生成英文回复）
# --------------------------------------------------------------------------- #

_SERVICE_SCENARIOS = {
    "damaged": "商品损坏/破损",
    "wrong_item": "发错货/收到错误商品",
    "size_mismatch": "尺寸/规格不符",
    "quality_issue": "质量问题/功能故障",
    "shipping_delay": "物流延迟/未收到",
    "return_refund": "退货退款申请",
    "negative_review": "差评安抚/挽回",
    "general": "其他/通用咨询",
}


def _ai_service_reply(*, scenario_label: str, detail: str, tone: str, product_name: str, client_ip: str) -> dict[str, Any]:
    cache_key = _cache_key(
        "service_reply",
        {"scenario": scenario_label, "detail": detail, "tone": tone, "name": product_name},
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return dict(cached)
    _check_ai_quota(client_ip)
    provider = _ai_provider_or_raise()

    system_prompt = (
        "你是跨境电商资深客服。请针对给定场景，生成 2 个可直接发送的英文客服回复模板，"
        "语气专业、礼貌、有同理心，给出明确的解决方案（补发/退款/退货指引/折扣挽回等），"
        "不要承诺无法兑现的内容。每个回复给出：适用语气标签(scene)、邮件主题(subject)、正文(text)。"
        '只返回 JSON，格式为 {"replies":[{"scene":"...","subject":"...","text":"..."}],"tips":"一句话沟通提醒"}。'
    )
    user_prompt = (
        f"场景: {scenario_label}\n"
        f"商品: {product_name or '（未指定）'}\n"
        f"语气要求: {tone or '专业且有同理心'}\n"
        f"补充情况: {detail or '（无）'}\n"
        "请生成 2 个英文客服回复模板。"
    )
    try:
        result = provider.json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
        )
    except LLMJSONParseError:
        raise RuntimeError("AI response parse failed")

    replies: list[dict[str, str]] = []
    raw = result.get("replies") if isinstance(result, dict) else None
    if isinstance(raw, list):
        for item in raw[:4]:
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                scene = str(item.get("scene") or "").strip()
                subject = str(item.get("subject") or "").strip()
            else:
                text = str(item).strip()
                scene = ""
                subject = ""
            if text:
                replies.append({"scene": scene[:80], "subject": subject[:160], "text": text[:1200]})
    if not replies:
        raise RuntimeError("AI returned no usable replies")

    tips = str(result.get("tips") or "").strip()[:240] if isinstance(result, dict) else ""
    payload = {"replies": replies, "tips": tips}
    _cache_put(cache_key, payload)
    return dict(payload)


def generate_service_reply(payload: dict[str, Any], *, client_ip: str) -> dict[str, Any]:
    scenario = str(payload.get("scenario") or "general").strip().lower()
    scenario_label = _SERVICE_SCENARIOS.get(scenario, _SERVICE_SCENARIOS["general"])
    detail = str(payload.get("detail") or "").strip()
    if len(detail) > MAX_KEYWORD_INPUT_LENGTH:
        raise ToolInputError(f"补充情况过长，请控制在 {MAX_KEYWORD_INPUT_LENGTH} 字符以内")
    tone = str(payload.get("tone") or "").strip()[:120]
    product_name = str(payload.get("product_name") or "").strip()[:200]

    ai_section: dict[str, Any] = {"status": "skipped"}
    try:
        ai_section = _ai_service_reply(
            scenario_label=scenario_label, detail=detail, tone=tone,
            product_name=product_name, client_ip=client_ip,
        )
        ai_section["status"] = "ok"
    except ToolQuotaExceeded:
        ai_section = _degraded_section("客服回复")
    except Exception:
        ai_section = _error_section("客服回复")

    reply_count = len(ai_section.get("replies") or [])
    headline = f"已生成 {reply_count} 个英文客服回复模板" if reply_count else f"客服回复模板 · {scenario_label}"

    prompt_template = (
        "请针对下面的客服场景，生成 2 个可直接发送的英文客服回复模板，语气专业、礼貌、有同理心，"
        "并给出明确的解决方案。\n"
        f"- 场景: {scenario_label}\n"
        f"- 商品: {product_name or '（未指定）'}\n"
        f"- 语气要求: {tone or '专业且有同理心'}\n"
        f"- 补充情况: {detail or '（无）'}"
    )

    return {
        "summary": {"headline": headline, "scenario": scenario_label, "reply_count": reply_count},
        "details": {"ai": ai_section, "scenario": scenario_label},
        "prompt_template": prompt_template,
        "meta": {
            "tool": "service_reply",
            "tier": "rule+ai",
            "ai_used": ai_section.get("status") == "ok",
            "ai_status": ai_section.get("status"),
        },
    }
