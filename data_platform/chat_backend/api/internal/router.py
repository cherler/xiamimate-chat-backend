"""Aggregates modular internal API routers."""
from __future__ import annotations

from fastapi import APIRouter

from data_platform.chat_backend.api.internal_routes import router as legacy_internal_router
from data_platform.chat_backend.api.internal.provider_routes import router as provider_router
from data_platform.chat_backend.api.internal.tool_routes import router as tool_router


router = APIRouter()
router.include_router(provider_router)
router.include_router(legacy_internal_router)
router.include_router(tool_router)

