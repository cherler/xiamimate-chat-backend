"""FastAPI application assembly — startup, exception handling, router wiring."""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from data_platform.chat_backend.infra.postgres import (
    _ensure_app_schema,
    _postgres_conn,
)
from data_platform.chat_backend.infra.http import _error_response
from data_platform.chat_backend.domains.billing.service import (
    _get_event_pricing,
    _seed_billing_event_pricing,
    _seed_billing_packages,
    _seed_promotion_rules,
)

# Routers
from data_platform.chat_backend.api.public_routes import router as public_router
from data_platform.chat_backend.api.internal_routes import router as internal_router
from data_platform.chat_backend.api.admin_routes import router as admin_router
from data_platform.chat_backend.api.portal_routes import router as portal_router

app = FastAPI(title="xiamimate Chat Backend", version="2026-04-13")


@app.on_event("startup")
def initialize_chat_backend() -> None:
    with _postgres_conn() as conn:
        _ensure_app_schema(conn)
        _seed_billing_packages(conn)
        _seed_promotion_rules(conn)
        _seed_billing_event_pricing(conn)
        _get_event_pricing(conn)


@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = "REQUEST_ERROR" if exc.status_code < 500 else "INTERNAL_ERROR"
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_response(request.url.path, code, str(exc.detail)),
    )


@app.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=_error_response(request.url.path, "INTERNAL_ERROR", str(exc)),
    )


app.include_router(public_router)
app.include_router(internal_router)
app.include_router(admin_router)
app.include_router(portal_router)
