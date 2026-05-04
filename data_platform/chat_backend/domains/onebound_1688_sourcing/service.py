"""Onebound 1688 supplier discovery native-tool orchestration."""
from __future__ import annotations

import time
from typing import Any

from data_platform.chat_backend.domains.onebound_1688_sourcing.client import Onebound1688CallResult, Onebound1688Client, load_onebound_1688_config
from data_platform.chat_backend.domains.onebound_1688_sourcing.normalizer import merge_offer_detail, normalize_item_detail, normalize_search_items, normalize_seller_info
from data_platform.chat_backend.domains.onebound_1688_sourcing.repository import fetch_recent_onebound_1688_query
from data_platform.chat_backend.domains.onebound_1688_sourcing.repository import record_onebound_1688_query
from data_platform.chat_backend.domains.onebound_1688_sourcing.repository import record_onebound_1688_supplier_offers
from data_platform.chat_backend.domains.onebound_1688_sourcing.scoring import build_empty_scored, build_supplier_queries, score_supplier_result, should_skip_query
from data_platform.chat_backend.infra.postgres import _postgres_conn


CAPABILITY = "onebound_1688_supplier_discovery"
AGENT_CACHE_TTL_MINUTES = 30


def run_onebound_1688_supplier_discovery(payload: dict[str, Any]) -> dict[str, Any]:
    started_at = time.monotonic()
    config = load_onebound_1688_config()
    query = str(payload.get("query") or "").strip()
    marketplace = str(payload.get("marketplace") or payload.get("target_market") or "US").strip().upper() or "US"
    limit = max(1, min(int(payload.get("limit") or config.item_search_page_size), config.item_search_page_size))
    cost_assumptions = payload.get("cost_assumptions") if isinstance(payload.get("cost_assumptions"), dict) else {}
    supplier_query_plan = build_supplier_queries(query, _as_text_list(payload.get("supplier_queries")))
    request_payload = {
        "query": query,
        "marketplace": marketplace,
        "seller_scope": str(payload.get("seller_scope") or "cross_border_sme_v1"),
        "supplier_queries": supplier_query_plan,
        "limit": limit,
        "cost_assumptions": cost_assumptions,
    }
    agent_tool_policy = _build_agent_tool_policy(payload, query, supplier_query_plan)

    if agent_tool_policy["action"] == "skip_realtime":
        degradation = {"status": "skipped", "reason": agent_tool_policy["reason"]}
        scored = build_empty_scored(query, marketplace, status="skipped", reason=agent_tool_policy["reason"])
        scored["agent_tool_policy"] = agent_tool_policy
        return _build_response(config.provider, request_payload, [], {}, scored, degradation, started_at, None)

    if not config.enabled:
        degradation = {"status": "disabled", "reason": "Onebound 1688 provider is disabled"}
        scored = build_empty_scored(query, marketplace, status="disabled", reason=degradation["reason"])
        scored["agent_tool_policy"] = agent_tool_policy
        return _build_response(config.provider, request_payload, [], {}, scored, degradation, started_at, None)

    if not config.api_key or not config.api_secret:
        degradation = {"status": "missing_credentials", "reason": "ONEBOUND_API_KEY and ONEBOUND_API_SECRET are not configured"}
        scored = build_empty_scored(query, marketplace, status="missing_credentials", reason=degradation["reason"])
        scored["agent_tool_policy"] = agent_tool_policy
        return _build_response(config.provider, request_payload, [], {}, scored, degradation, started_at, None)

    report_run_id = str(payload.get("report_run_id") or "").strip()
    if report_run_id and not payload.get("force_refresh"):
        with _postgres_conn() as conn:
            cached = fetch_recent_onebound_1688_query(
                conn,
                report_run_id=report_run_id,
                query=query,
                marketplace=marketplace,
                max_age_minutes=AGENT_CACHE_TTL_MINUTES,
            )
        if cached:
            return _cached_response_from_snapshot(provider=config.provider, request_payload=request_payload, cached=cached, started_at=started_at)

    client = Onebound1688Client(config=config)
    results: list[Onebound1688CallResult] = []
    offers_by_id: dict[str, dict[str, Any]] = {}
    for planned_query in supplier_query_plan[:3]:
        search_result = client.get(
            "item_search",
            {
                "q": planned_query["query"],
                "page": 1,
                "page_size": limit,
                "sort": "_sale",
            },
        )
        results.append(search_result)
        for offer in normalize_search_items(_result_payload(search_result), supplier_query=planned_query["query"]):
            num_iid = str(offer.get("num_iid") or "").strip()
            if not num_iid:
                continue
            if num_iid not in offers_by_id:
                offers_by_id[num_iid] = offer
            if len(offers_by_id) >= limit:
                break
        if len(offers_by_id) >= limit:
            break

    detail_topk = max(0, min(config.max_item_get, len(offers_by_id)))
    for num_iid in list(offers_by_id.keys())[:detail_topk]:
        detail_result = client.get("item_get", {"num_iid": num_iid, "sales_data": 1})
        results.append(detail_result)
        if detail_result.ok:
            detail_offer = normalize_item_detail(
                _result_payload(detail_result),
                supplier_query=str(offers_by_id[num_iid].get("supplier_query") or query),
            )
            offers_by_id[num_iid] = merge_offer_detail(offers_by_id[num_iid], detail_offer, None)

    seller_ids = _top_seller_ids(list(offers_by_id.values()), config.max_seller_info)
    seller_info_by_id: dict[str, dict[str, Any]] = {}
    for seller_id in seller_ids:
        seller_result = client.get("seller_info", {"sid": seller_id})
        results.append(seller_result)
        if seller_result.ok:
            seller_info = normalize_seller_info(_result_payload(seller_result))
            seller_info["seller_id"] = seller_info.get("seller_id") or seller_id
            seller_info_by_id[seller_id] = seller_info

    normalized_offers = _attach_seller_info(list(offers_by_id.values()), seller_info_by_id)
    status = _safe_status(results, bool(normalized_offers))
    failed_reasons = [result.error for result in results if result.error]
    degradation = {
        "status": status,
        "reason": "; ".join(str(reason) for reason in failed_reasons[:3]) if status not in {"ok", "no_result"} else "",
    }
    scored = score_supplier_result(query=query, marketplace=marketplace, offers=normalized_offers, cost_assumptions=cost_assumptions)
    scored["agent_tool_policy"] = agent_tool_policy
    scored["top_supplier_offers"] = normalized_offers[: min(10, len(normalized_offers))]
    vendor_response_raw = _vendor_response_raw(results) if config.save_raw_response else {}
    vendor_endpoints = [_call_to_dict(result) for result in results]
    result_text = str(scored.get("result_text") or "")
    snapshot_id = _persist_if_requested(
        payload=payload,
        provider=config.provider,
        request_payload=request_payload,
        vendor_endpoints=vendor_endpoints,
        vendor_response_raw=vendor_response_raw,
        normalized_summary=scored,
        result_text=result_text,
        status=status,
        latency_ms=int((time.monotonic() - started_at) * 1000),
        offers=normalized_offers,
    )
    return _build_response(config.provider, request_payload, vendor_endpoints, vendor_response_raw, scored, degradation, started_at, snapshot_id)


def _build_agent_tool_policy(payload: dict[str, Any], query: str, supplier_query_plan: list[dict[str, str]]) -> dict[str, Any]:
    skip_query, skip_reason = should_skip_query(query)
    if not payload.get("allow_realtime", True):
        action = "skip_realtime"
        reason = "allow_realtime=false"
    elif skip_query:
        action = "skip_realtime"
        reason = skip_reason
    elif not supplier_query_plan:
        action = "skip_realtime"
        reason = "supplier_query_missing"
    else:
        action = "call_onebound_1688"
        reason = "clear_supplier_query"
    return {
        "action": action,
        "reason": reason,
        "cache_ttl_minutes": AGENT_CACHE_TTL_MINUTES,
        "supplier_query_count": len(supplier_query_plan),
        "supplier_queries": supplier_query_plan,
        "p0_endpoints": ["item_search", "item_get", "seller_info"],
        "temu_status": "pending_not_used_in_p0",
    }


def _cached_response_from_snapshot(
    *,
    provider: str,
    request_payload: dict[str, Any],
    cached: dict[str, Any],
    started_at: float,
) -> dict[str, Any]:
    scored = cached.get("normalized_summary") or {}
    agent_tool_policy = dict(scored.get("agent_tool_policy") or {})
    agent_tool_policy.update(
        {
            "action": "reuse_cached",
            "reason": "same_report_query_market_within_ttl",
            "cache_ttl_minutes": AGENT_CACHE_TTL_MINUTES,
            "cached_snapshot_id": str(cached.get("id") or ""),
        }
    )
    scored["agent_tool_policy"] = agent_tool_policy
    degradation = {"status": str(cached.get("status") or "partial"), "reason": "reused recent Onebound 1688 realtime snapshot"}
    response = _build_response(
        provider,
        request_payload,
        cached.get("vendor_endpoints") or [],
        cached.get("vendor_response_raw") or {},
        scored,
        degradation,
        started_at,
        str(cached.get("id") or "") or None,
    )
    response["source_meta"]["cache_hit"] = True
    response["source_meta"]["data_freshness"] = "reused_realtime_snapshot"
    response["source_meta"]["cached_created_at"] = str(cached.get("created_at") or "")
    return response


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
    offers: list[dict[str, Any]],
) -> str | None:
    report_run_id = str(payload.get("report_run_id") or "").strip()
    if not report_run_id:
        return None
    with _postgres_conn() as conn:
        snapshot_id = record_onebound_1688_query(
            conn,
            report_run_id=report_run_id,
            query=request_payload["query"],
            marketplace=request_payload["marketplace"],
            provider=provider,
            request_payload=request_payload,
            vendor_endpoints=vendor_endpoints,
            vendor_response_raw=vendor_response_raw,
            normalized_summary=normalized_summary,
            result_text=result_text,
            status=status,
            latency_ms=latency_ms,
        )
        record_onebound_1688_supplier_offers(conn, snapshot_id=snapshot_id, report_run_id=report_run_id, offers=offers)
        return snapshot_id


def _build_response(
    provider: str,
    request_payload: dict[str, Any],
    vendor_endpoints: list[dict[str, Any]],
    vendor_response_raw: dict[str, Any],
    scored: dict[str, Any],
    degradation: dict[str, Any],
    started_at: float,
    snapshot_id: str | None,
) -> dict[str, Any]:
    source_meta = {
        "latency_ms": int((time.monotonic() - started_at) * 1000),
        "data_freshness": "realtime" if vendor_endpoints else "not_requested",
        "snapshot_id": snapshot_id,
        "endpoint_count": len(vendor_endpoints),
    }
    return {
        "provider": provider,
        "capability": CAPABILITY,
        "query": request_payload["query"],
        "marketplace": request_payload["marketplace"],
        "summary": scored.get("summary") or {},
        "signals": scored.get("signals") or {},
        "supplier_feasibility": scored.get("supplier_feasibility") or {},
        "risk_exclusion": scored.get("risk_exclusion") or {},
        "cost_floor": scored.get("cost_floor") or {},
        "agent_tool_policy": scored.get("agent_tool_policy") or {},
        "top_supplier_offers": scored.get("top_supplier_offers") or [],
        "vendor_endpoints": vendor_endpoints,
        "vendor_response_keys": sorted(vendor_response_raw.keys()),
        "result_text": scored.get("result_text") or "",
        "source_meta": source_meta,
        "degradation": degradation,
    }


def _call_to_dict(result: Onebound1688CallResult) -> dict[str, Any]:
    return {
        "endpoint": result.endpoint,
        "params": result.params,
        "ok": result.ok,
        "status_code": result.status_code,
        "latency_ms": result.latency_ms,
        "error": result.error,
        "request_id": result.request_id,
        "error_payload": result.error_payload,
    }


def _result_payload(result: Onebound1688CallResult) -> dict[str, Any]:
    return result.data if result.ok and isinstance(result.data, dict) else {}


def _safe_status(results: list[Onebound1688CallResult], has_offers: bool) -> str:
    if not results:
        return "failed"
    ok_count = sum(1 for result in results if result.ok)
    if ok_count == len(results):
        return "ok" if has_offers else "no_result"
    if ok_count > 0:
        if any("timeout" in str(result.error).lower() for result in results if result.error):
            return "timeout"
        return "partial" if has_offers else "no_result"
    if any("timeout" in str(result.error).lower() for result in results if result.error):
        return "timeout"
    return "failed"


def _vendor_response_raw(results: list[Onebound1688CallResult]) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    for index, result in enumerate(results, start=1):
        if result.ok and isinstance(result.data, dict):
            raw[f"{index}:{result.endpoint}"] = result.data
    return raw


def _top_seller_ids(offers: list[dict[str, Any]], limit: int) -> list[str]:
    ids: list[str] = []
    for offer in offers:
        seller_id = str(offer.get("seller_id") or "").strip()
        if seller_id and seller_id not in ids:
            ids.append(seller_id)
        if len(ids) >= limit:
            break
    return ids


def _attach_seller_info(offers: list[dict[str, Any]], seller_info_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for offer in offers:
        item = dict(offer)
        seller_id = str(item.get("seller_id") or "").strip()
        if seller_id and seller_id in seller_info_by_id:
            item["seller_info"] = seller_info_by_id[seller_id]
            item.setdefault("seller_name", seller_info_by_id[seller_id].get("seller_name"))
            item.setdefault("shop_name", seller_info_by_id[seller_id].get("shop_name"))
        merged.append(item)
    return merged


def _as_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
