"""Billing domain — data models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class UserCreditAccount:
    user_id: str
    balance_points: int
    reserved_points: int
    lifetime_granted_points: int
    lifetime_purchased_points: int
    lifetime_spent_points: int
    created_at: Any
    updated_at: Any
