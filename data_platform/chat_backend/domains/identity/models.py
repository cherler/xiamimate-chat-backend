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
    source_state: str = "active"
    source_last_seen_at: Any | None = None
    source_orphaned_at: Any | None = None
    source_recovered_at: Any | None = None
    auth_session_version: int = 1
    last_password_reset_at: Any | None = None
    invite_code: str | None = None
    email_verified_at: Any | None = None
