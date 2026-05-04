"""Aggregates portal routers."""
from __future__ import annotations

from fastapi import APIRouter

from data_platform.chat_backend.api.portal_routes import router as legacy_portal_router


router = APIRouter()
router.include_router(legacy_portal_router)
