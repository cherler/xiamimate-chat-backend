"""TikHub HTTP client for TikTok Shop opportunity signals."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

import requests as http_requests


@dataclass
class TikHubCallResult:
    endpoint: str
    params: dict[str, Any]
    ok: bool
    status_code: int | None = None
    latency_ms: int = 0
    data: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class TikHubConfig:
    enabled: bool
    provider: str
    base_url: str
    api_key: str
    target_region: str
    timeout_seconds: int
    max_retries: int
    topn: int
    detail_topk: int
    enable_p1_content_heat: bool
    enable_p2_ads: bool


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def load_tikhub_config() -> TikHubConfig:
    third_party_enabled = _env_bool("THIRD_PARTY_MARKET_ENABLED", True)
    opportunity_enabled = _env_bool("TIKTOK_OPPORTUNITY_ENABLED", True)
    return TikHubConfig(
        enabled=third_party_enabled and opportunity_enabled,
        provider=(os.environ.get("TIKTOK_PROVIDER") or "tikhub").strip().lower() or "tikhub",
        base_url=(os.environ.get("TIKTOK_API_BASE_URL") or "https://api.tikhub.io").rstrip("/"),
        api_key=(os.environ.get("TIKTOK_API_KEY") or "").strip(),
        target_region=(os.environ.get("TIKTOK_TARGET_REGION") or "US").strip().upper() or "US",
        timeout_seconds=max(1, int(os.environ.get("THIRD_PARTY_MARKET_TIMEOUT_SECONDS", "15"))),
        max_retries=max(0, int(os.environ.get("THIRD_PARTY_MARKET_MAX_RETRIES", "1"))),
        topn=max(1, int(os.environ.get("TIKTOK_TOPN", "20"))),
        detail_topk=max(0, int(os.environ.get("TIKTOK_DETAIL_TOPK", "5"))),
        enable_p1_content_heat=_env_bool("TIKTOK_ENABLE_P1_CONTENT_HEAT", True),
        enable_p2_ads=_env_bool("TIKTOK_ENABLE_P2_ADS", False),
    )


@dataclass
class TikHubClient:
    config: TikHubConfig
    session: Any = field(default_factory=http_requests.Session)

    def get(self, endpoint: str, params: dict[str, Any]) -> TikHubCallResult:
        url = f"{self.config.base_url}{endpoint}"
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        cleaned_params = {key: value for key, value in params.items() if value not in (None, "", [])}
        started_at = time.monotonic()
        last_error: str | None = None
        status_code: int | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=cleaned_params,
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                )
                status_code = response.status_code
                latency_ms = int((time.monotonic() - started_at) * 1000)
                if response.status_code >= 400:
                    last_error = f"http_{response.status_code}"
                    if attempt < self.config.max_retries:
                        continue
                    return TikHubCallResult(
                        endpoint=endpoint,
                        params=cleaned_params,
                        ok=False,
                        status_code=response.status_code,
                        latency_ms=latency_ms,
                        error=last_error,
                    )
                payload = response.json()
                data = payload if isinstance(payload, dict) else {"value": payload}
                return TikHubCallResult(
                    endpoint=endpoint,
                    params=cleaned_params,
                    ok=True,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    data=data,
                )
            except Exception as exc:
                last_error = str(exc)
                if attempt < self.config.max_retries:
                    continue

        return TikHubCallResult(
            endpoint=endpoint,
            params=cleaned_params,
            ok=False,
            status_code=status_code,
            latency_ms=int((time.monotonic() - started_at) * 1000),
            error=last_error or "request_failed",
        )
