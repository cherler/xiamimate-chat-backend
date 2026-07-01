"""Internal provider proxy routes."""
from __future__ import annotations

import json
from typing import Any

import requests as http_requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from data_platform.chat_backend.infra.http import _require_internal_service, _success_response
from data_platform.chat_backend.infra.postgres import _postgres_conn
from data_platform.chat_backend.domains.memory_profile.service import build_memory_profile
from data_platform.chat_backend.domains.provider_proxy.service import (
    _dify_report_stream_idle_timeout,
    _proxy_anthropic_message,
    _proxy_dify_workflow_blocking,
    _proxy_dify_workflow_stream,
    _proxy_ima_get_media_info,
    _proxy_ima_retrieve,
    _proxy_ima_search_knowledge_bases,
    _proxy_customer_help_retrieve,
    _proxy_knowledge_retrieve,
    _proxy_minimax_chat_completion,
    _proxy_minimax_chat_completion_stream,
    _proxy_openai_chat_completion,
    _proxy_openai_chat_completion_stream,
    _proxy_report_blocking,
    _proxy_report_stream,
    _proxy_tavily_search,
    _proxy_theme_api,
)
from data_platform.chat_backend.api.models import (
    InternalIMAKnowledgeBaseSearchRequest,
    InternalIMAKnowledgeSearchRequest,
    InternalIMAMediaInfoRequest,
    InternalKnowledgeRetrieveRequest,
    InternalLLMRequest,
    InternalMemoryProfileBuildRequest,
    InternalMinimaxRequest,
    InternalReportRunRequest,
    InternalTavilySearchRequest,
    InternalThemeAPICallRequest,
    InternalWorkflowRunRequest,
)


router = APIRouter()


def _sse_data_event(payload: dict[str, Any]) -> bytes:
    return ("data: %s\n\n" % json.dumps(payload, ensure_ascii=False)).encode("utf-8")


def _report_stream_finished_title(payload: dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    title = str(data.get("title") or data.get("node_id") or "").strip()
    return title[:120]


def _report_evidence_nodes_completed(finished_titles: list[str]) -> bool:
    evidence_markers = {
        "候选池统计整理",
        "趋势结果整理",
        "类目基准整理",
        "弱信号结果整理",
        "头部 ASIN 结果整理",
        "知识结果整理",
    }
    return bool(evidence_markers.intersection(finished_titles))


def _report_stream_timeout_event(
    *,
    profile: str,
    idle_timeout_seconds: int,
    finished_titles: list[str],
    error_text: str,
) -> bytes:
    evidence_completed = _report_evidence_nodes_completed(finished_titles)
    error_code = "report_final_answer_timeout" if evidence_completed else "report_stream_idle_timeout"
    if evidence_completed:
        message = (
            "证据节点已完成，但最终总结在 %d 秒内未返回。"
            "本次已停止等待，避免报告流停在 98%%。请稍后重试，或收窄问题后重跑。"
        ) % idle_timeout_seconds
    else:
        message = (
            "Dify report 上游在 %d 秒内没有返回新事件，已停止本次流式请求。"
            "请稍后重试。"
        ) % idle_timeout_seconds
    return _sse_data_event(
        {
            "event": "error",
            "message": message,
            "error": error_code,
            "data": {
                "error": error_code,
                "message": message,
                "profile": profile,
                "phase": "final_answer" if evidence_completed else "upstream_stream",
                "idle_timeout_seconds": idle_timeout_seconds,
                "completed_node_count": len(finished_titles),
                "completed_nodes_tail": finished_titles[-8:],
                "recoverable": True,
                "upstream_error": error_text[:500],
            },
        }
    )


def _iter_report_stream_chunks(upstream_response: http_requests.Response, *, profile: str) -> Any:
    idle_timeout_seconds = _dify_report_stream_idle_timeout()
    finished_titles: list[str] = []
    try:
        for raw_line in upstream_response.iter_lines(decode_unicode=True):
            line = "" if raw_line is None else str(raw_line)
            if line.startswith("data:"):
                raw_payload = line[5:].strip()
                if raw_payload and raw_payload != "[DONE]":
                    try:
                        payload = json.loads(raw_payload)
                    except json.JSONDecodeError:
                        payload = {}
                    if isinstance(payload, dict) and str(payload.get("event") or "") == "node_finished":
                        title = _report_stream_finished_title(payload)
                        if title and title not in finished_titles:
                            finished_titles.append(title)
            yield (line + "\n").encode("utf-8")
    except http_requests.RequestException as exc:
        yield _report_stream_timeout_event(
            profile=profile,
            idle_timeout_seconds=idle_timeout_seconds,
            finished_titles=finished_titles,
            error_text=str(exc),
        )
    finally:
        upstream_response.close()


@router.post("/internal/provider/dify-workflow/run")
def internal_run_dify_workflow(request: Request, payload: InternalWorkflowRunRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    provider_response = _proxy_dify_workflow_blocking(query=payload.query, user=payload.user)
    return _success_response(
        "/internal/provider/dify-workflow/run",
        provider_response,
        "dify workflow proxied",
    )


@router.post("/internal/provider/dify-workflow/run-stream")
def internal_run_dify_workflow_stream(request: Request, payload: InternalWorkflowRunRequest) -> StreamingResponse:
    _require_internal_service(request, request.url.path)
    upstream_response = _proxy_dify_workflow_stream(query=payload.query, user=payload.user)

    def iterate_stream() -> Any:
        try:
            for chunk in upstream_response.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk
        finally:
            upstream_response.close()

    return StreamingResponse(
        iterate_stream(),
        media_type=upstream_response.headers.get("content-type") or "text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.post("/internal/provider/report/run")
def internal_run_report(request: Request, payload: InternalReportRunRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    provider_response = _proxy_report_blocking(query=payload.query, user=payload.user, profile=payload.profile)
    return _success_response(
        "/internal/provider/report/run",
        provider_response,
        "report request proxied",
    )


@router.post("/internal/provider/report/run-stream")
def internal_run_report_stream(request: Request, payload: InternalReportRunRequest) -> StreamingResponse:
    _require_internal_service(request, request.url.path)
    upstream_response = _proxy_report_stream(query=payload.query, user=payload.user, profile=payload.profile)

    return StreamingResponse(
        _iter_report_stream_chunks(upstream_response, profile=payload.profile),
        media_type=upstream_response.headers.get("content-type") or "text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.post("/internal/provider/dify-web-search/run")
def internal_run_dify_web_search(request: Request, payload: InternalWorkflowRunRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    raise HTTPException(
        status_code=410,
        detail="Dify web-search chatflow is deprecated. Use /internal/provider/web-search/tavily instead.",
    )


@router.post("/internal/provider/dify-web-search/run-stream")
def internal_run_dify_web_search_stream(request: Request, payload: InternalWorkflowRunRequest) -> StreamingResponse:
    _require_internal_service(request, request.url.path)
    raise HTTPException(
        status_code=410,
        detail="Dify web-search chatflow streaming is deprecated. Use /internal/provider/web-search/tavily instead.",
    )


@router.post("/internal/provider/web-search/tavily")
def internal_run_tavily_search(request: Request, payload: InternalTavilySearchRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    provider_response = _proxy_tavily_search(payload=jsonable_encoder(payload))
    return _success_response(
        "/internal/provider/web-search/tavily",
        provider_response,
        "tavily search proxied",
    )


@router.post("/internal/provider/dify-dataset/retrieve")
def internal_retrieve_knowledge(request: Request, payload: InternalKnowledgeRetrieveRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    result = _proxy_knowledge_retrieve(query=payload.query, top_k=payload.top_k)
    return _success_response(
        "/internal/provider/dify-dataset/retrieve",
        {"result": result},
        "knowledge retrieval proxied",
    )


@router.post("/internal/provider/dify-customer-help/retrieve")
def internal_retrieve_customer_help(request: Request, payload: InternalKnowledgeRetrieveRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    result = _proxy_customer_help_retrieve(query=payload.query, top_k=payload.top_k)
    return _success_response(
        "/internal/provider/dify-customer-help/retrieve",
        {"result": result},
        "customer help retrieval proxied",
    )


@router.post("/internal/provider/external-kb/ima-knowledge-bases/search")
def internal_search_ima_knowledge_bases(
    request: Request,
    payload: InternalIMAKnowledgeBaseSearchRequest,
) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    result = _proxy_ima_search_knowledge_bases(query=payload.query, cursor=payload.cursor, limit=payload.limit)
    return _success_response(
        "/internal/provider/external-kb/ima-knowledge-bases/search",
        result,
        "IMA knowledge base search proxied",
    )


@router.post("/internal/provider/external-kb/ima-search")
def internal_search_ima_knowledge(request: Request, payload: InternalIMAKnowledgeSearchRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    result = _proxy_ima_retrieve(
        query=payload.query,
        top_k=payload.top_k,
        knowledge_base_ids=payload.knowledge_base_ids,
        knowledge_base_query=payload.knowledge_base_query,
        knowledge_base_limit=payload.knowledge_base_limit,
    )
    return _success_response(
        "/internal/provider/external-kb/ima-search",
        result,
        "IMA knowledge retrieval proxied",
    )


@router.post("/internal/provider/external-kb/ima-media-info")
def internal_get_ima_media_info(request: Request, payload: InternalIMAMediaInfoRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    result = _proxy_ima_get_media_info(media_id=payload.media_id)
    return _success_response(
        "/internal/provider/external-kb/ima-media-info",
        result,
        "IMA media info proxied",
    )


@router.post("/internal/provider/memory-profile/build")
def internal_build_memory_profile(request: Request, payload: InternalMemoryProfileBuildRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    with _postgres_conn() as conn:
        result = build_memory_profile(
            conn,
            user_id=payload.user_id,
            query=payload.query,
            target_platform=payload.target_platform,
            target_market=payload.target_market,
            report_profile=payload.report_profile,
        )
    return _success_response(
        "/internal/provider/memory-profile/build",
        result,
        "memory profile built",
    )


@router.post("/internal/provider/theme-api/{operation}")
def internal_call_theme_api(operation: str, request: Request, payload: InternalThemeAPICallRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    result = _proxy_theme_api(operation=operation, payload=payload.payload)
    return _success_response(
        f"/internal/provider/theme-api/{operation}",
        {"result": result},
        "theme api proxied",
    )


@router.post("/internal/provider/minimax/chat-completions", deprecated=True)
def internal_minimax_chat_completion(request: Request, payload: InternalMinimaxRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    provider_response = _proxy_minimax_chat_completion(payload=payload.payload)
    return _success_response(
        "/internal/provider/minimax/chat-completions",
        provider_response,
        "deprecated minimax openai-compatible request proxied; use /internal/provider/anthropic/messages",
    )


@router.post("/internal/provider/minimax/chat-completions/stream", deprecated=True)
def internal_minimax_chat_completion_stream(request: Request, payload: InternalMinimaxRequest) -> StreamingResponse:
    _require_internal_service(request, request.url.path)
    upstream_response = _proxy_minimax_chat_completion_stream(payload=payload.payload)

    def iterate_stream() -> Any:
        try:
            for chunk in upstream_response.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk
        finally:
            upstream_response.close()

    return StreamingResponse(
        iterate_stream(),
        media_type=upstream_response.headers.get("content-type") or "text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Deprecated-Route": "use /internal/provider/anthropic/messages for MiniMax-M2.7",
        },
    )


@router.post("/internal/provider/openai/chat-completions")
def internal_openai_chat_completion(request: Request, payload: InternalLLMRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    provider_response = _proxy_openai_chat_completion(payload=payload.payload, provider_profile=payload.provider_profile)
    return _success_response(
        "/internal/provider/openai/chat-completions",
        provider_response,
        "openai-compatible request proxied",
    )


@router.post("/internal/provider/openai/chat-completions/stream")
def internal_openai_chat_completion_stream(request: Request, payload: InternalLLMRequest) -> StreamingResponse:
    _require_internal_service(request, request.url.path)
    upstream_response = _proxy_openai_chat_completion_stream(
        payload=payload.payload,
        provider_profile=payload.provider_profile,
    )

    def iterate_stream() -> Any:
        try:
            for chunk in upstream_response.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk
        finally:
            upstream_response.close()

    return StreamingResponse(
        iterate_stream(),
        media_type=upstream_response.headers.get("content-type") or "text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.post("/internal/provider/anthropic/messages")
def internal_anthropic_messages(request: Request, payload: InternalLLMRequest) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    provider_response = _proxy_anthropic_message(payload=payload.payload)
    return _success_response(
        "/internal/provider/anthropic/messages",
        provider_response,
        "anthropic-compatible request proxied",
    )