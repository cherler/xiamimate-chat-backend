"""Workspace API routes — 商品工作台。

对外（portal 用户态）：/portal/api/workspaces*
对内（服务间，需 internal secret）：/internal/workspace/*

整个路由仅在 ``WORKSPACE_FEATURE_ENABLED`` 开启时由 app.py 挂载；关闭即不存在。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from data_platform.chat_backend.infra.postgres import _postgres_conn
from data_platform.chat_backend.infra.http import _success_response, _require_internal_service
from data_platform.chat_backend.domains.portal.service import _require_portal_user, _portal_public_base_url
from data_platform.chat_backend.domains.workspace import service as workspace_service
from data_platform.chat_backend.domains.workspace.tokens import verify_chart_token
from data_platform.chat_backend.domains.workspace.schemas import (
    AddDetailPageAssetRequest,
    SetWatchRequest,
    UpsertWorkspaceFromAnalysisRequest,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Portal (user-facing)
# ---------------------------------------------------------------------------

@router.get("/portal/api/workspaces")
def portal_list_workspaces(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        items = workspace_service.list_workspaces(conn, user_id)
    return _success_response("/portal/api/workspaces", {"items": items}, "workspaces loaded")


@router.get("/portal/api/workspaces/alerts")
def portal_list_workspace_alerts(request: Request) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        items = workspace_service.list_alerts(conn, user_id)
    return _success_response("/portal/api/workspaces/alerts", {"items": items}, "alerts loaded")


@router.get("/portal/api/workspaces/{workspace_id}")
def portal_get_workspace(request: Request, workspace_id: str) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        detail = workspace_service.get_workspace_detail(conn, user_id, workspace_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return _success_response("/portal/api/workspaces/{workspace_id}", detail, "workspace loaded")


@router.post("/portal/api/workspaces/{workspace_id}/watch")
def portal_set_workspace_watch(
    request: Request, workspace_id: str, payload: SetWatchRequest
) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        watch = workspace_service.set_watch(
            conn,
            user_id=user_id,
            workspace_id=workspace_id,
            watch_enabled=payload.watch_enabled,
            watch_config=payload.watch_config,
        )
    if watch is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return _success_response(
        "/portal/api/workspaces/{workspace_id}/watch", watch, "watch updated"
    )


@router.post("/portal/api/workspaces/{workspace_id}/assets/detail-page")
def portal_add_detail_page_asset(
    request: Request, workspace_id: str, payload: AddDetailPageAssetRequest
) -> dict[str, Any]:
    user_id = _require_portal_user(request)
    with _postgres_conn() as conn:
        asset = workspace_service.add_detail_page_asset(
            conn,
            user_id=user_id,
            workspace_id=workspace_id,
            title=payload.title,
            content=payload.content,
        )
    if asset is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return _success_response(
        "/portal/api/workspaces/{workspace_id}/assets/detail-page", asset, "asset created"
    )


# ---------------------------------------------------------------------------
# Public read-only (token-signed evidence chart SVG, no login required)
# ---------------------------------------------------------------------------

@router.get("/portal/api/evidence/chart/{chart_token}.svg")
def public_evidence_chart_svg(chart_token: str) -> Response:
    claims = verify_chart_token(chart_token)
    if claims is None:
        raise HTTPException(status_code=404, detail="chart not found")
    with _postgres_conn() as conn:
        evidence = workspace_service.get_workspace_evidence(conn, claims["workspace_id"])
    svg = workspace_service.render_workspace_chart(evidence, claims["chart_kind"])
    # 证据图按 workspace 内容签名、内容稳定，可被气泡/浏览器短期缓存。
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "private, max-age=300"},
    )


# ---------------------------------------------------------------------------
# Internal (service-to-service)
# ---------------------------------------------------------------------------

@router.post("/internal/workspace/upsert-from-analysis")
def internal_upsert_workspace_from_analysis(
    request: Request, payload: UpsertWorkspaceFromAnalysisRequest
) -> dict[str, Any]:
    _require_internal_service(request, scope="/internal/workspace/upsert-from-analysis")
    with _postgres_conn() as conn:
        workspace = workspace_service.upsert_workspace_from_analysis(
            conn,
            user_id=payload.user_id,
            theme_key=payload.theme_key,
            title=payload.title,
            source_run_id=payload.source_run_id,
            brief=payload.brief,
            evidence=payload.evidence,
        )
    # 附带证据图链接与工作台入口，供 bridge 直接拼到气泡里（无需 bridge 持有签名密钥）。
    public_base = _portal_public_base_url()
    workspace_id = workspace.get("workspace_id")
    workspace["evidence_charts"] = workspace_service.build_evidence_chart_links(
        workspace_id, workspace.get("evidence"), public_base_url=public_base, limit=3
    )
    workspace["workspace_url"] = f"{public_base.rstrip('/')}/portal/workspace?id={workspace_id}"
    return _success_response(
        "/internal/workspace/upsert-from-analysis", workspace, "workspace upserted"
    )
