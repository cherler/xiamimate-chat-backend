"""API-key domain — data models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class UserAPIKey:
    user_id: str
    api_key_id: str
    api_key_prefix: str
    api_key_raw: str
    status: str
    created_at: Any
    updated_at: Any
    last_used_at: Any
    revoked_at: Any
