"""签名 token，用于公开只读的证据图链接（防 ID 遍历 + 短期过期）。

token 携带 ``{workspace_id, chart_kind, exp}``，用 HMAC-SHA256(service secret) 签名。
公开路由 ``/portal/api/evidence/chart/{token}.svg`` 只接受验签通过且未过期的 token，
因此无需登录态即可在气泡里以 ``![](...)`` 内联证据图，又不会被人枚举他人 workspace。
"""
from __future__ import annotations

import base64
import hmac
import json
import time
from hashlib import sha256
from typing import Any

from data_platform.chat_backend.infra.settings import INTERNAL_SERVICE_SECRET

# 证据图 token 默认有效期（秒）。气泡是一次性展示，给足展示窗口即可。
CHART_TOKEN_TTL_SECONDS = 7 * 24 * 3600

VALID_CHART_KINDS = ("trend", "price", "competition", "forecast", "risk")


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(payload_b64: str) -> str:
    secret = (INTERNAL_SERVICE_SECRET or "").encode("utf-8")
    digest = hmac.new(secret, payload_b64.encode("ascii"), sha256).digest()
    return _b64url_encode(digest)


def sign_chart_token(workspace_id: str, chart_kind: str, *, ttl_seconds: int = CHART_TOKEN_TTL_SECONDS) -> str:
    payload = {
        "w": workspace_id,
        "k": chart_kind,
        "exp": int(time.time()) + max(60, int(ttl_seconds)),
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{payload_b64}.{_sign(payload_b64)}"


def verify_chart_token(token: str) -> dict[str, Any] | None:
    """验签并校验过期；通过返回 ``{"workspace_id", "chart_kind"}``，否则 None。"""
    if not token or not INTERNAL_SERVICE_SECRET:
        return None
    parts = token.split(".")
    if len(parts) != 2:
        return None
    payload_b64, signature = parts
    expected = _sign(payload_b64)
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    chart_kind = payload.get("k")
    workspace_id = payload.get("w")
    if chart_kind not in VALID_CHART_KINDS or not workspace_id:
        return None
    return {"workspace_id": str(workspace_id), "chart_kind": str(chart_kind)}
