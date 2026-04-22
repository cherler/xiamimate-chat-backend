"""Pydantic request/response models for the API layer."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, validator

from data_platform.chat_backend.infra.settings import (
    ALLOWED_MESSAGE_ROLES,
    ALLOWED_RUN_STATUSES,
    DEFAULT_PAYMENT_PROVIDER,
)


class CreateSessionRequest(BaseModel):
    title: str | None = None
    target_platform: str = Field(..., min_length=1)
    target_market: str | None = None
    validation_marketplace: str | None = None


class CreateMessageRequest(BaseModel):
    content: str = Field(..., min_length=1)
    role: str = Field(default="user")
    message_type: str = Field(default="text", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @validator("role")
    def _validate_role(cls, value: str) -> str:  # noqa: N805
        normalized = value.strip().lower()
        if normalized not in ALLOWED_MESSAGE_ROLES:
            raise ValueError(f"unsupported role: {value}")
        return normalized


class CreateThemeRunRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    message_id: str | None = None
    product_query: str = Field(..., min_length=1)
    analysis_goal: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)


class CallbackArtifact(BaseModel):
    artifact_type: str = Field(..., min_length=1)
    artifact_key: str = Field(..., min_length=1)
    artifact_payload: dict[str, Any] = Field(default_factory=dict)


class CallbackUsageEvent(BaseModel):
    event_type: str = Field(..., min_length=1)
    units: int = Field(default=1, ge=1)
    meta: dict[str, Any] = Field(default_factory=dict)


class GrantPointsRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    points: int = Field(..., ge=1)
    entry_type: str = Field(default="admin_grant", min_length=1)
    user_email: str | None = None
    display_name: str | None = None
    plan_tier: str | None = None
    description: str | None = None
    reference_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class AdminGrantPointsRequest(BaseModel):
    points: int = Field(..., ge=1)
    entry_type: str = Field(default="admin_grant", min_length=1)
    description: str | None = None
    reference_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class CreateSystemNotificationBroadcastRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    body: str = Field(..., min_length=1, max_length=2000)
    tag: str = Field(default="系统通知", min_length=1, max_length=24)
    level: str = Field(default="info", min_length=1, max_length=16)
    action_url: str | None = Field(default=None, max_length=255)

    @validator("level")
    def _validate_level(cls, value: str) -> str:  # noqa: N805
        normalized = value.strip().lower()
        if normalized not in {"info", "success", "warning", "error"}:
            raise ValueError(f"unsupported notification level: {value}")
        return normalized


class IdentityExchangeRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    email: str | None = None
    display_name: str | None = None


class ConfirmEmailVerificationRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=8)


class RequestPasswordResetRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)


class ConfirmPasswordResetRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    code: str = Field(..., min_length=4, max_length=8)
    new_password: str = Field(..., min_length=8, max_length=72)


class BindReferralCodeRequest(BaseModel):
    invite_code: str = Field(..., min_length=4, max_length=32)


class RedeemCodeRedeemRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=64)


class AdminCreateRedeemCodeBatchRequest(BaseModel):
    points: int = Field(..., ge=1)
    code_count: int = Field(default=1, ge=1, le=500)
    code_type: str = Field(default="promotion", min_length=1, max_length=32)
    batch_name: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)
    valid_from: Any | None = None
    valid_until: Any | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    @validator("code_type")
    def _validate_code_type(cls, value: str) -> str:  # noqa: N805
        normalized = value.strip().lower()
        if normalized not in {"promotion", "promotion_reward", "gift", "bonus", "recharge", "sold", "paid", "cash"}:
            raise ValueError(f"unsupported code_type: {value}")
        return normalized


class UpdateNotificationReadStateRequest(BaseModel):
    read: bool = True
    category: str | None = None
    notification_ids: list[str] = Field(default_factory=list)

    @validator("category")
    def _validate_category(cls, value: str | None) -> str | None:  # noqa: N805
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in {"system", "user"}:
            raise ValueError(f"unsupported notification category: {value}")
        return normalized


class ConfirmSecurityVerificationRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=8)


class ChargePointsEvent(BaseModel):
    event_type: str = Field(..., min_length=1)
    units: int = Field(default=1, ge=1)
    reference_id: str | None = None
    description: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ChargePointsRequest(BaseModel):
    api_key: str = Field(..., min_length=1)
    events: list[ChargePointsEvent] = Field(..., min_length=1)


class RefundPointsRequest(BaseModel):
    api_key: str = Field(..., min_length=1)
    event_type: str = Field(..., min_length=1)
    points: int = Field(..., ge=1)
    units: int = Field(default=1, ge=1)
    reference_id: str | None = None
    description: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class CreatePaymentOrderRequest(BaseModel):
    package_code: str = Field(..., min_length=1)
    provider: str = Field(default=DEFAULT_PAYMENT_PROVIDER, min_length=1)


class PaymentProviderCallbackRequest(BaseModel):
    order_id: str = Field(..., min_length=1)
    provider_order_id: str | None = None
    provider_trade_no: str | None = None
    provider_subscription_id: str | None = None
    paid_amount_cents: int | None = Field(default=None, ge=1)
    period_start: Any | None = None
    period_end: Any | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class GrantSubscriptionRequest(BaseModel):
    period_start: Any
    period_end: Any
    provider_trade_no: str | None = None
    order_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class InternalWorkflowRunRequest(BaseModel):
    query: str = Field(..., min_length=1)
    user: str = Field(..., min_length=1)


class InternalKnowledgeRetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class InternalThemeAPICallRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class InternalMinimaxRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class DifyRunCallbackRequest(BaseModel):
    run_id: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)
    dify_run_id: str | None = None
    final_answer_text: str | None = None
    assistant_message: str | None = None
    assistant_message_type: str = Field(default="analysis_result", min_length=1)
    artifacts: list[CallbackArtifact] = Field(default_factory=list)
    usage_events: list[CallbackUsageEvent] = Field(default_factory=list)

    @validator("status")
    def _validate_status(cls, value: str) -> str:  # noqa: N805
        normalized = value.strip().lower()
        if normalized not in ALLOWED_RUN_STATUSES:
            raise ValueError(f"unsupported run status: {value}")
        return normalized


class UpdateEventPricingRequest(BaseModel):
    display_name: str | None = None
    points_per_unit: int | None = None
    status: str | None = None
    display_order: int | None = None


class UpdateSiteConfigRequest(BaseModel):
    config_value: str = Field(..., max_length=3_000_000)
