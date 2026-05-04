"""Internal native tool/provider routes.

TikTok Shop/TikHub and future native tool endpoints should be registered here
or in sub-routers included from this module.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from data_platform.chat_backend.api.models import InternalOnebound1688SupplierDiscoveryRequest, InternalTikTokOpportunityRequest
from data_platform.chat_backend.domains.onebound_1688_sourcing.service import run_onebound_1688_supplier_discovery
from data_platform.chat_backend.domains.tiktok_shop_opportunity.service import run_tiktok_opportunity
from data_platform.chat_backend.infra.http import _require_internal_service, _success_response


router = APIRouter()


@router.get("/internal/tools/health")
def internal_tools_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "router": "internal_tools",
    }


@router.post("/internal/provider/external-market/tiktok/opportunity")
def internal_tiktok_opportunity(
    request: Request,
    payload: InternalTikTokOpportunityRequest,
) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    result = run_tiktok_opportunity(payload.dict())
    return _success_response(
        "/internal/provider/external-market/tiktok/opportunity",
        result,
        "tiktok opportunity enhanced",
    )


@router.post("/internal/provider/sourcing/1688/supplier-discovery")
def internal_onebound_1688_supplier_discovery(
    request: Request,
    payload: InternalOnebound1688SupplierDiscoveryRequest,
) -> dict[str, Any]:
    _require_internal_service(request, request.url.path)
    result = run_onebound_1688_supplier_discovery(payload.dict())
    return _success_response(
        "/internal/provider/sourcing/1688/supplier-discovery",
        result,
        "onebound 1688 supplier discovery",
    )
