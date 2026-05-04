"""Redeem-code helpers for the billing domain."""
from __future__ import annotations

from fastapi import HTTPException

from data_platform.chat_backend.infra.settings import _generate_invite_code, _hash_text


def _normalize_redeem_code(raw_code: str) -> str:
    normalized = "".join(ch for ch in str(raw_code or "").strip().upper() if ch.isalnum())
    if len(normalized) < 6:
        raise HTTPException(status_code=400, detail="invalid redeem code")
    return normalized


def _build_redeem_code_hash(raw_code: str) -> str:
    return _hash_text(f"redeem_code:{_normalize_redeem_code(raw_code)}")


def _mask_redeem_code(raw_code: str) -> str:
    normalized = _normalize_redeem_code(raw_code)
    if len(normalized) <= 8:
        return normalized[:2] + "****" + normalized[-2:]
    return normalized[:4] + "****" + normalized[-4:]


def _format_generated_redeem_code(raw_code: str) -> str:
    normalized = _normalize_redeem_code(raw_code)
    return "-".join(normalized[index:index + 4] for index in range(0, len(normalized), 4))


def _normalize_redeem_code_type(code_type: str | None) -> str:
    normalized = str(code_type or "promotion").strip().lower() or "promotion"
    if normalized in {"promotion", "promotion_reward", "gift", "bonus"}:
        return "promotion"
    if normalized in {"recharge", "sold", "paid", "cash"}:
        return "recharge"
    raise HTTPException(status_code=400, detail=f"unsupported redeem code type: {code_type}")


def _generate_redeem_code_value(length: int = 12) -> str:
    return _format_generated_redeem_code(_generate_invite_code(length=max(8, length)))
