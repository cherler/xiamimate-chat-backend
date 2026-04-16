"""Provider proxy domain — upstream service forwarding.

Covers: Dify workflow, Dify knowledge-base, Theme API, MiniMax (OpenAI-compat).
"""
from __future__ import annotations

import json
import os
from typing import Any

import requests as http_requests
from fastapi import HTTPException

from data_platform.chat_backend.infra.settings import (
    AGENT_OPENAI_TIMEOUT,
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


# ---------------------------------------------------------------------------
# Dify proxies
# ---------------------------------------------------------------------------

def _proxy_dify_workflow_blocking(query: str, user: str) -> dict[str, Any]:
    response = None
    try:
        response = http_requests.post(
            f"{_dify_base_url()}/v1/chat-messages",
            json={
                "inputs": {},
                "query": query,
                "response_mode": "blocking",
                "user": user,
            },
            headers={
                "Authorization": f"Bearer {_dify_workflow_api_key()}",
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


def _proxy_dify_workflow_stream(query: str, user: str) -> http_requests.Response:
    response = None
    try:
        response = http_requests.post(
            f"{_dify_base_url()}/v1/chat-messages",
            json={
                "inputs": {},
                "query": query,
                "response_mode": "streaming",
                "user": user,
            },
            headers={
                "Authorization": f"Bearer {_dify_workflow_api_key()}",
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
