"""Identity domain — data models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RequestUser:
    user_id: str
    email: str
    display_name: str
    status: str
    plan_tier: str
    created_at: Any
    updated_at: Any
    invite_code: str | None = None
    email_verified_at: Any | None = None
