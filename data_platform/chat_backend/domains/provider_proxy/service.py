"""Provider proxy domain — upstream service forwarding.

Covers: Dify workflow, Dify knowledge-base, Theme API, MiniMax (OpenAI-compat).
"""
from __future__ import annotations

import json
import os
from typing import Any

import requests as http_requests
from fastapi import HTTPException

from data_platform.llm_client import build_llm_provider
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


# ---------------------------------------------------------------------------
# Theme API proxy
# ---------------------------------------------------------------------------

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
        return json.dumps(response.json(), ensure_ascii=False, indent=2)
    except http_requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=("theme_api 请求失败:\n" + _request_error_detail(response, exc))[:4000])
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"theme_api 返回了无法解析的 JSON: {str(exc)}")


# ---------------------------------------------------------------------------
# MiniMax (OpenAI-compatible) proxy
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
