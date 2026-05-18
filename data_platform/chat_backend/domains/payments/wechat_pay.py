"""WeChat Pay API v3 helpers for Native Pay."""
from __future__ import annotations

import base64
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

import requests as http_requests
from fastapi import HTTPException

from data_platform.chat_backend.infra.settings import (
    WECHAT_API_V3_KEY,
    WECHAT_APP_ID,
    WECHAT_CERT_SERIAL_NO,
    WECHAT_MCH_ID,
    WECHAT_NATIVE_QR_TTL_SECONDS,
    WECHAT_NOTIFY_URL,
    WECHAT_PAY_ENABLED,
    WECHAT_PLATFORM_CERT_FILE,
    WECHAT_PLATFORM_PUBLIC_KEY_FILE,
    WECHAT_PLATFORM_PUBLIC_KEY_ID,
    WECHAT_PRIVATE_KEY,
    WECHAT_PRIVATE_KEY_FILE,
)

WECHAT_PAY_API_BASE = "https://api.mch.weixin.qq.com"
WECHAT_NATIVE_PREPAY_PATH = "/v3/pay/transactions/native"
WECHAT_NOTIFY_MAX_SKEW_SECONDS = 300


def _load_crypto_modules():
    try:
        from cryptography import x509
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:  # pragma: no cover - depends on runtime env
        raise HTTPException(status_code=503, detail="cryptography package is required for WeChat Pay") from exc
    return InvalidSignature, hashes, serialization, padding, AESGCM, x509


def _read_secret_file(path_value: str) -> bytes:
    path = Path(path_value).expanduser()
    if not path.exists():
        raise HTTPException(status_code=503, detail=f"WeChat Pay secret file not found: {path}")
    return path.read_bytes()


def _wechat_private_key_bytes() -> bytes:
    if WECHAT_PRIVATE_KEY_FILE:
        return _read_secret_file(WECHAT_PRIVATE_KEY_FILE)
    if WECHAT_PRIVATE_KEY:
        return WECHAT_PRIVATE_KEY.replace("\\n", "\n").encode("utf-8")
    raise HTTPException(status_code=503, detail="WeChat Pay merchant private key is not configured")


def _wechat_platform_public_key_bytes() -> bytes:
    if WECHAT_PLATFORM_PUBLIC_KEY_FILE:
        return _read_secret_file(WECHAT_PLATFORM_PUBLIC_KEY_FILE)
    if WECHAT_PLATFORM_CERT_FILE:
        return _read_secret_file(WECHAT_PLATFORM_CERT_FILE)
    raise HTTPException(status_code=503, detail="WeChat Pay platform public key/cert is not configured")


def _ensure_wechat_pay_configured() -> None:
    missing = []
    if not WECHAT_PAY_ENABLED:
        missing.append("CHAT_BACKEND_WECHAT_PAY_ENABLED")
    for name, value in [
        ("CHAT_BACKEND_WECHAT_MCH_ID", WECHAT_MCH_ID),
        ("CHAT_BACKEND_WECHAT_APP_ID", WECHAT_APP_ID),
        ("CHAT_BACKEND_WECHAT_API_V3_KEY", WECHAT_API_V3_KEY),
        ("CHAT_BACKEND_WECHAT_CERT_SERIAL_NO", WECHAT_CERT_SERIAL_NO),
        ("CHAT_BACKEND_WECHAT_NOTIFY_URL", WECHAT_NOTIFY_URL),
    ]:
        if not value:
            missing.append(name)
    if not WECHAT_PRIVATE_KEY and not WECHAT_PRIVATE_KEY_FILE:
        missing.append("CHAT_BACKEND_WECHAT_PRIVATE_KEY_FILE")
    if not WECHAT_PLATFORM_PUBLIC_KEY_FILE and not WECHAT_PLATFORM_CERT_FILE:
        missing.append("CHAT_BACKEND_WECHAT_PLATFORM_PUBLIC_KEY_FILE")
    if missing:
        raise HTTPException(status_code=503, detail="WeChat Pay config missing: " + ", ".join(missing))


def _load_private_key():
    _, _, serialization, _, _, _ = _load_crypto_modules()
    try:
        return serialization.load_pem_private_key(_wechat_private_key_bytes(), password=None)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="failed to load WeChat Pay merchant private key") from exc


def _load_platform_public_key():
    _, _, serialization, _, _, x509 = _load_crypto_modules()
    data = _wechat_platform_public_key_bytes()
    try:
        if b"BEGIN CERTIFICATE" in data:
            cert = x509.load_pem_x509_certificate(data)
            return cert.public_key()
        return serialization.load_pem_public_key(data)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="failed to load WeChat Pay platform public key/cert") from exc


def _wechat_authorization(method: str, url_path_with_query: str, body: str) -> str:
    _, hashes, _, asym_padding, _, _ = _load_crypto_modules()
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(16)
    message = f"{method.upper()}\n{url_path_with_query}\n{timestamp}\n{nonce}\n{body}\n"
    signature = _load_private_key().sign(
        message.encode("utf-8"),
        asym_padding.PKCS1v15(),
        hashes.SHA256(),
    )
    signature_text = base64.b64encode(signature).decode("ascii")
    return (
        'WECHATPAY2-SHA256-RSA2048 '
        f'mchid="{WECHAT_MCH_ID}",'
        f'nonce_str="{nonce}",'
        f'signature="{signature_text}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{WECHAT_CERT_SERIAL_NO}"'
    )


def _wechat_api_request(method: str, path_with_query: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    _ensure_wechat_pay_configured()
    body = "" if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    headers = {
        "Accept": "application/json",
        "User-Agent": "xiamimate-chat-backend/2026-05-18",
        "Authorization": _wechat_authorization(method, path_with_query, body),
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    try:
        response = http_requests.request(
            method=method.upper(),
            url=WECHAT_PAY_API_BASE + path_with_query,
            headers=headers,
            data=body.encode("utf-8") if payload is not None else None,
            timeout=12,
        )
    except Exception as exc:  # pragma: no cover - network failure only
        raise HTTPException(status_code=502, detail=f"WeChat Pay API request failed: {exc}") from exc
    try:
        data = response.json() if response.text.strip() else {}
    except Exception:
        data = {"raw_response": response.text.strip()}
    if response.status_code < 200 or response.status_code >= 300:
        message = data.get("message") or data.get("code") or response.reason or "WeChat Pay API error"
        raise HTTPException(status_code=502, detail=f"WeChat Pay API error: {message}")
    return data


def _coerce_utc_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _wechat_time_expire(order_row: dict[str, Any]) -> datetime:
    order_created_at = _coerce_utc_datetime(order_row.get("created_at"))
    if order_created_at is None:
        order_created_at = datetime.now(timezone.utc)
    return order_created_at + timedelta(seconds=WECHAT_NATIVE_QR_TTL_SECONDS)


def _format_wechat_rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def create_wechat_native_prepay(order_row: dict[str, Any], package_row: dict[str, Any]) -> dict[str, Any]:
    expires_at = _wechat_time_expire(order_row)
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="WeChat payment order has expired")
    package_meta = package_row.get("meta_json") or {}
    description = str(package_meta.get("display_name") or package_row.get("package_name") or order_row["package_code"])
    payload = {
        "appid": WECHAT_APP_ID,
        "mchid": WECHAT_MCH_ID,
        "description": description[:127],
        "out_trade_no": order_row["order_id"],
        "time_expire": _format_wechat_rfc3339(expires_at),
        "notify_url": WECHAT_NOTIFY_URL,
        "amount": {
            "total": int(order_row["amount_cents"]),
            "currency": "CNY",
        },
    }
    response = _wechat_api_request("POST", WECHAT_NATIVE_PREPAY_PATH, payload)
    code_url = str(response.get("code_url") or "").strip()
    if not code_url:
        raise HTTPException(status_code=502, detail="WeChat Pay did not return code_url")
    return {
        "provider_order_id": order_row["order_id"],
        "qr_code_url": code_url,
        "expires_at": expires_at,
        "request_payload": payload,
        "response_payload": response,
    }


def query_wechat_order_by_out_trade_no(order_id: str) -> dict[str, Any]:
    quoted_order_id = quote(str(order_id), safe="")
    path = f"/v3/pay/transactions/out-trade-no/{quoted_order_id}?mchid={quote(WECHAT_MCH_ID, safe='')}"
    return _wechat_api_request("GET", path, None)


def close_wechat_order_by_out_trade_no(order_id: str) -> dict[str, Any]:
    quoted_order_id = quote(str(order_id), safe="")
    path = f"/v3/pay/transactions/out-trade-no/{quoted_order_id}/close"
    return _wechat_api_request("POST", path, {"mchid": WECHAT_MCH_ID})


def verify_and_decrypt_wechat_notify(headers: Mapping[str, str], raw_body: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    _ensure_wechat_pay_configured()
    InvalidSignature, hashes, _, asym_padding, AESGCM, _ = _load_crypto_modules()
    timestamp = str(headers.get("Wechatpay-Timestamp") or headers.get("wechatpay-timestamp") or "").strip()
    nonce = str(headers.get("Wechatpay-Nonce") or headers.get("wechatpay-nonce") or "").strip()
    signature_text = str(headers.get("Wechatpay-Signature") or headers.get("wechatpay-signature") or "").strip()
    serial = str(headers.get("Wechatpay-Serial") or headers.get("wechatpay-serial") or "").strip()
    if not timestamp or not nonce or not signature_text or not serial:
        raise HTTPException(status_code=400, detail="missing WeChat Pay notify signature headers")
    if WECHAT_PLATFORM_PUBLIC_KEY_ID and serial != WECHAT_PLATFORM_PUBLIC_KEY_ID:
        raise HTTPException(status_code=400, detail="WeChat Pay notify serial does not match configured public key id")
    try:
        timestamp_int = int(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid WeChat Pay notify timestamp") from exc
    if abs(int(time.time()) - timestamp_int) > WECHAT_NOTIFY_MAX_SKEW_SECONDS:
        raise HTTPException(status_code=400, detail="WeChat Pay notify timestamp is outside allowed window")

    message = timestamp.encode("utf-8") + b"\n" + nonce.encode("utf-8") + b"\n" + raw_body + b"\n"
    try:
        _load_platform_public_key().verify(
            base64.b64decode(signature_text),
            message,
            asym_padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except InvalidSignature as exc:
        raise HTTPException(status_code=400, detail="invalid WeChat Pay notify signature") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="failed to verify WeChat Pay notify signature") from exc

    try:
        notification = json.loads(raw_body.decode("utf-8"))
        resource = notification["resource"]
        nonce_value = str(resource["nonce"])
        ciphertext = base64.b64decode(str(resource["ciphertext"]))
        associated_data = str(resource.get("associated_data") or "").encode("utf-8") or None
        plaintext = AESGCM(WECHAT_API_V3_KEY.encode("utf-8")).decrypt(
            nonce_value.encode("utf-8"),
            ciphertext,
            associated_data,
        )
        decrypted = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="failed to decrypt WeChat Pay notify resource") from exc
    return notification, decrypted


def extract_wechat_trade_payload(trade_payload: dict[str, Any]) -> dict[str, Any]:
    amount = trade_payload.get("amount") or {}
    return {
        "order_id": str(trade_payload.get("out_trade_no") or "").strip(),
        "provider_order_id": str(trade_payload.get("out_trade_no") or "").strip() or None,
        "provider_trade_no": str(trade_payload.get("transaction_id") or "").strip() or None,
        "trade_state": str(trade_payload.get("trade_state") or "").strip().upper(),
        "paid_amount_cents": int(amount.get("total") or 0) if amount.get("total") is not None else None,
        "payer": trade_payload.get("payer") or {},
        "raw": trade_payload,
    }


def wechat_trade_state_to_session_status(trade_state: str) -> str:
    normalized = str(trade_state or "").strip().upper()
    if normalized == "SUCCESS":
        return "paid"
    if normalized == "CLOSED":
        return "closed"
    if normalized == "REFUND":
        return "refunded"
    if normalized in {"NOTPAY", "USERPAYING", "ACCEPT"}:
        return "pending"
    return "failed" if normalized else "pending"