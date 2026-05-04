"""Onebound 1688 HTTP client."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

import requests as http_requests


@dataclass
class Onebound1688CallResult:
    api_name: str
    endpoint: str
    params: dict[str, Any]
    ok: bool
    status_code: int | None = None
    latency_ms: int = 0
    data: dict[str, Any] | None = None
    error: str | None = None
    error_code: str | None = None
    request_id: str | None = None
    error_payload: dict[str, Any] | None = None


@dataclass
class Onebound1688Config:
    enabled: bool
    provider: str
    base_url: str
    api_key: str
    api_secret: str
    timeout_seconds: int
    max_retries: int
    cache_ttl_seconds: int
    item_search_page_size: int
    max_item_get: int
    max_seller_info: int
    save_raw_response: bool


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def load_onebound_1688_config() -> Onebound1688Config:
    return Onebound1688Config(
        enabled=_env_bool("ONEBOUND_1688_ENABLED", True),
        provider="onebound",
        base_url=(os.environ.get("ONEBOUND_API_BASE_URL") or "https://api-gw.onebound.cn").rstrip("/"),
        api_key=(os.environ.get("ONEBOUND_API_KEY") or "").strip(),
        api_secret=(os.environ.get("ONEBOUND_API_SECRET") or "").strip(),
        timeout_seconds=max(1, int(os.environ.get("ONEBOUND_1688_TIMEOUT_SECONDS", "15"))),
        max_retries=max(0, int(os.environ.get("ONEBOUND_1688_MAX_RETRIES", "1"))),
        cache_ttl_seconds=max(0, int(os.environ.get("ONEBOUND_1688_CACHE_TTL_SECONDS", "3600"))),
        item_search_page_size=max(1, int(os.environ.get("ONEBOUND_1688_ITEM_SEARCH_PAGE_SIZE", "20"))),
        max_item_get=max(0, int(os.environ.get("ONEBOUND_1688_MAX_ITEM_GET", "20"))),
        max_seller_info=max(0, int(os.environ.get("ONEBOUND_1688_MAX_SELLER_INFO", "10"))),
        save_raw_response=_env_bool("ONEBOUND_1688_SAVE_RAW_RESPONSE", True),
    )


def _safe_json(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {"value": payload}


def _extract_error_code(payload: dict[str, Any]) -> str | None:
    for key in ("error_code", "errorCode", "code", "status_code", "statusCode"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _is_success_payload(payload: dict[str, Any]) -> bool:
    error_code = _extract_error_code(payload)
    if error_code is None:
        return True
    return error_code in {"0000", "0", "200", "success", "OK", "ok"}


@dataclass
class Onebound1688Client:
    config: Onebound1688Config
    session: Any = field(default_factory=http_requests.Session)

    def get(self, api_name: str, params: dict[str, Any]) -> Onebound1688CallResult:
        endpoint = f"/1688/{api_name}/"
        url = f"{self.config.base_url}{endpoint}"
        cleaned_params = {key: value for key, value in params.items() if value not in (None, "", [])}
        request_params = {
            "key": self.config.api_key,
            "secret": self.config.api_secret,
            **cleaned_params,
        }
        safe_params = dict(cleaned_params)
        started_at = time.monotonic()
        last_error: str | None = None
        last_error_code: str | None = None
        status_code: int | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.session.get(url, params=request_params, timeout=self.config.timeout_seconds)
                status_code = response.status_code
                latency_ms = int((time.monotonic() - started_at) * 1000)
                payload = _safe_json(response)
                error_code = _extract_error_code(payload)
                if response.status_code >= 400 or not _is_success_payload(payload):
                    last_error = f"http_{response.status_code}" if response.status_code >= 400 else str(payload.get("reason") or payload.get("error") or "onebound_error")
                    last_error_code = error_code
                    if attempt < self.config.max_retries and error_code in {"4001", "4002", "4017", "5000", None}:
                        continue
                    return Onebound1688CallResult(
                        api_name=api_name,
                        endpoint=endpoint,
                        params=safe_params,
                        ok=False,
                        status_code=response.status_code,
                        latency_ms=latency_ms,
                        data=payload,
                        error=last_error,
                        error_code=error_code,
                        error_payload=payload,
                    )
                return Onebound1688CallResult(
                    api_name=api_name,
                    endpoint=endpoint,
                    params=safe_params,
                    ok=True,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    data=payload,
                    error_code=error_code,
                )
            except Exception as exc:
                last_error = str(exc)
                if attempt < self.config.max_retries:
                    continue

        return Onebound1688CallResult(
            api_name=api_name,
            endpoint=endpoint,
            params=safe_params,
            ok=False,
            status_code=status_code,
            latency_ms=int((time.monotonic() - started_at) * 1000),
            error=last_error or "request_failed",
            error_code=last_error_code,
        )
