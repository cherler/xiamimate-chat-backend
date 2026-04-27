"""Memory profile builder for research-grade personalization."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from data_platform.chat_backend.infra.postgres import _run_pg_dict_query
from data_platform.chat_backend.infra.settings import ALLOWED_REPORT_PROFILES


_PLATFORM_KEYWORDS: dict[str, tuple[str, ...]] = {
    "amazon": ("amazon", "亚马逊", "美亚", "欧亚", "日亚"),
    "tiktok": ("tiktok", "tik tok", "抖音电商", "tiktok shop"),
    "temu": ("temu",),
    "shopify": ("shopify", "独立站"),
    "walmart": ("walmart", "沃尔玛"),
}

_MARKET_KEYWORDS: dict[str, tuple[str, ...]] = {
    "US": ("us", "usa", "美国", "美区", "美站"),
    "UK": ("uk", "英国", "英区", "英站"),
    "DE": ("de", "德国", "德区", "德站"),
    "FR": ("fr", "法国", "法区", "法站"),
    "JP": ("jp", "日本", "日区", "日站"),
}

_CONSTRAINT_PATTERN = re.compile(r"(?:避免|不要|不能|禁止|必须|优先|仅做|只做|聚焦|限定)[^，。；\n]{2,28}")
_TOPIC_SPLIT_PATTERN = re.compile(r"[，,。；;、/\\|\s]+")


def _normalize_report_profile(value: str | None) -> str:
    normalized = str(value or "research").strip().lower() or "research"
    if normalized not in ALLOWED_REPORT_PROFILES:
        return "research"
    return normalized


def _collect_recent_user_messages(conn, user_id: str, limit: int = 12) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT m.message_id, m.session_id, m.content, m.created_at
        FROM app.chat_message m
        JOIN app.chat_session s ON m.session_id = s.session_id
        WHERE s.user_id = %s AND m.role = 'user'
        ORDER BY m.created_at DESC, m.message_id DESC
        LIMIT %s
        """,
        [user_id, limit],
    )


def _collect_recent_sessions(conn, user_id: str, limit: int = 8) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT session_id, title, target_platform, target_market, validation_marketplace, updated_at
        FROM app.chat_session
        WHERE user_id = %s
        ORDER BY updated_at DESC, session_id DESC
        LIMIT %s
        """,
        [user_id, limit],
    )


def _collect_recent_runs(conn, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT r.run_id, r.session_id, r.product_query, r.analysis_goal, r.input_payload_json,
               r.status, r.created_at, r.updated_at
        FROM app.analysis_run r
        JOIN app.chat_session s ON r.session_id = s.session_id
        WHERE s.user_id = %s
        ORDER BY r.updated_at DESC, r.run_id DESC
        LIMIT %s
        """,
        [user_id, limit],
    )


def _fetch_user_row(conn, user_id: str) -> dict[str, Any]:
    rows = _run_pg_dict_query(
        conn,
        """
        SELECT user_id, email, display_name, status, plan_tier, email_verified_at, created_at, updated_at
        FROM app.app_user
        WHERE user_id = %s
        LIMIT 1
        """,
        [user_id],
    )
    if not rows:
        raise ValueError(f"user not found: {user_id}")
    return rows[0]


def _normalize_platform(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    for normalized, keywords in _PLATFORM_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return normalized
    return text[:24]


def _normalize_market(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    for normalized, keywords in _MARKET_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return normalized
    return text[:24].upper()


def _extract_constraints(texts: list[str], *, limit: int = 6) -> list[str]:
    matches: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for item in _CONSTRAINT_PATTERN.findall(text or ""):
            normalized = item.strip(" ，。；;\n")
            if normalized and normalized not in seen:
                seen.add(normalized)
                matches.append(normalized)
                if len(matches) >= limit:
                    return matches
    return matches


def _detect_risk_preference(texts: list[str]) -> tuple[str, str]:
    joined = "\n".join(texts).lower()
    conservative_hits = sum(token in joined for token in ["保守", "稳健", "先验证", "风险", "谨慎", "不要压货"])
    aggressive_hits = sum(token in joined for token in ["激进", "快速放量", "大推", "高增长", "all in"])
    if conservative_hits >= 2 and conservative_hits >= aggressive_hits:
        return "medium_conservative", "medium"
    if aggressive_hits >= 2 and aggressive_hits > conservative_hits:
        return "growth_seeking", "medium"
    return "balanced", "low"


def _detect_decision_style(texts: list[str]) -> tuple[str, str]:
    joined = "\n".join(texts).lower()
    evidence_hits = sum(token in joined for token in ["数据", "证据", "验证", "复盘", "风险", "样本", "趋势"])
    intuition_hits = sum(token in joined for token in ["感觉", "直觉", "拍脑袋", "先上"])
    if evidence_hits >= 2 and evidence_hits >= intuition_hits:
        return "evidence_first", "medium"
    if intuition_hits >= 2 and intuition_hits > evidence_hits:
        return "intuition_first", "low"
    return "mixed", "low"


def _collect_recent_topics(current_query: str, run_rows: list[dict[str, Any]], message_rows: list[dict[str, Any]], *, limit: int = 5) -> list[str]:
    topic_counter: Counter[str] = Counter()
    samples = [current_query]
    samples.extend(str(row.get("product_query") or "") for row in run_rows)
    samples.extend(str(row.get("content") or "") for row in message_rows[:6])
    for sample in samples:
        for token in _TOPIC_SPLIT_PATTERN.split(sample):
            normalized = token.strip()
            if len(normalized) < 2 or len(normalized) > 16:
                continue
            if normalized.lower() in {"amazon", "tiktok", "temu", "shopify", "research", "report"}:
                continue
            topic_counter[normalized] += 1
    return [item for item, _ in topic_counter.most_common(limit)]


def _build_identity_summary(
    user_row: dict[str, Any],
    *,
    market_focus: list[str],
    preferred_platforms: list[str],
    risk_preference: str,
    decision_style: str,
) -> str:
    verified_text = "已验证账户" if user_row.get("email_verified_at") else "未验证账户"
    plan_tier = str(user_row.get("plan_tier") or "free").strip()
    market_text = "、".join(market_focus[:2]) if market_focus else "跨市场"
    platform_text = "、".join(preferred_platforms[:2]) if preferred_platforms else "跨平台"
    risk_text = {
        "medium_conservative": "偏保守",
        "growth_seeking": "偏增长",
        "balanced": "相对均衡",
    }.get(risk_preference, "偏好待确认")
    decision_text = {
        "evidence_first": "证据优先",
        "intuition_first": "直觉优先",
        "mixed": "证据与经验混合",
    }.get(decision_style, "决策风格待确认")
    return f"{verified_text}，套餐层级 {plan_tier}，近期关注 {market_text} / {platform_text}，{risk_text}，{decision_text}。"


def build_memory_profile(
    conn,
    *,
    user_id: str,
    query: str,
    target_platform: str | None = None,
    target_market: str | None = None,
    report_profile: str | None = None,
) -> dict[str, Any]:
    user_row = _fetch_user_row(conn, user_id)
    session_rows = _collect_recent_sessions(conn, user_id)
    message_rows = _collect_recent_user_messages(conn, user_id)
    run_rows = _collect_recent_runs(conn, user_id)

    platform_candidates: list[str] = []
    market_candidates: list[str] = []

    if target_platform:
        platform_candidates.append(target_platform)
    if target_market:
        market_candidates.append(target_market)

    for row in session_rows:
        platform_candidates.append(str(row.get("target_platform") or ""))
        market_candidates.append(str(row.get("target_market") or ""))
        market_candidates.append(str(row.get("validation_marketplace") or ""))

    for row in run_rows:
        platform_candidates.append(str((row.get("input_payload_json") or {}).get("target_platform") or ""))
        market_candidates.append(str((row.get("input_payload_json") or {}).get("target_market") or ""))

    preferred_platforms = [
        item
        for item, _ in Counter(filter(None, (_normalize_platform(value) for value in platform_candidates))).most_common(3)
    ]
    market_focus = [
        item
        for item, _ in Counter(filter(None, (_normalize_market(value) for value in market_candidates))).most_common(3)
    ]

    text_evidence = [str(query or "")]
    text_evidence.extend(str(row.get("content") or "") for row in message_rows)
    text_evidence.extend(str(row.get("product_query") or "") for row in run_rows)
    text_evidence.extend(str(row.get("analysis_goal") or "") for row in run_rows)

    hard_constraints = _extract_constraints(text_evidence)
    risk_preference, risk_confidence = _detect_risk_preference(text_evidence)
    decision_style, decision_confidence = _detect_decision_style(text_evidence)
    recent_topics = _collect_recent_topics(str(query or ""), run_rows, message_rows)

    recent_report_profiles = []
    for row in run_rows:
        payload = row.get("input_payload_json") or {}
        if isinstance(payload, dict):
            candidate = _normalize_report_profile(payload.get("report_profile") or payload.get("profile"))
            if candidate:
                recent_report_profiles.append(candidate)

    role_hint = "verified_user" if user_row.get("email_verified_at") else "anonymous_user"
    if str(user_row.get("plan_tier") or "free").strip().lower() not in {"", "free"}:
        role_hint = "subscriber_user"

    memory_confidence = {
        "role_hint": "high",
        "market_focus": "high" if market_focus else "low",
        "preferred_platforms": "high" if preferred_platforms else "low",
        "risk_preference": risk_confidence,
        "decision_style": decision_confidence,
        "hard_constraints": "medium" if hard_constraints else "low",
        "recent_topics": "medium" if recent_topics else "low",
    }
    low_confidence_fields = [field for field, level in memory_confidence.items() if level == "low"]
    confidence_digest = (
        "低置信字段: " + "、".join(low_confidence_fields)
        if low_confidence_fields
        else "主要字段已有可用置信度。"
    )

    full_payload = {
        "summary_version": "memory_profile_v1",
        "user_id": user_id,
        "query": str(query or "").strip(),
        "report_profile": _normalize_report_profile(report_profile),
        "user_identity_summary": _build_identity_summary(
            user_row,
            market_focus=market_focus,
            preferred_platforms=preferred_platforms,
            risk_preference=risk_preference,
            decision_style=decision_style,
        ),
        "role_hint": role_hint,
        "market_focus": market_focus,
        "preferred_platforms": preferred_platforms,
        "preferred_price_band": {},
        "risk_preference": risk_preference,
        "decision_style": decision_style,
        "hard_constraints": hard_constraints,
        "recent_topics": recent_topics,
        "memory_confidence": memory_confidence,
        "evidence_sources": {
            "explicit_profile": int(bool(user_row.get("email_verified_at"))) + int(bool(target_platform or target_market)),
            "recent_queries": len(run_rows),
            "recent_reports": len(run_rows),
            "recent_messages": len(message_rows),
        },
        "session_context": {
            "target_platform": str(target_platform or "").strip(),
            "target_market": str(target_market or "").strip(),
        },
        "recent_queries": [str(row.get("product_query") or "") for row in run_rows[:6] if str(row.get("product_query") or "").strip()],
        "recent_report_profiles": recent_report_profiles[:6],
    }

    return {
        "user_id": user_id,
        "user_identity_summary": full_payload["user_identity_summary"],
        "role_hint": full_payload["role_hint"],
        "market_focus": full_payload["market_focus"],
        "preferred_platforms": full_payload["preferred_platforms"],
        "preferred_price_band": full_payload["preferred_price_band"],
        "risk_preference": full_payload["risk_preference"],
        "decision_style": full_payload["decision_style"],
        "hard_constraints": full_payload["hard_constraints"],
        "recent_topics": full_payload["recent_topics"],
        "memory_confidence": full_payload["memory_confidence"],
        "evidence_sources": full_payload["evidence_sources"],
        "confidence_digest": confidence_digest,
        "full_payload": full_payload,
    }