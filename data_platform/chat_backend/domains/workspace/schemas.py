"""Pydantic request models for the workspace domain."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UpsertWorkspaceFromAnalysisRequest(BaseModel):
    """内部请求：一次分析完成后把结果落成/更新一个工作台。"""

    user_id: str = Field(..., min_length=1)
    theme_key: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    source_run_id: str | None = None
    brief: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)


class SetWatchRequest(BaseModel):
    """开启/关闭某工作台的追踪。"""

    watch_enabled: bool = True
    watch_config: dict[str, Any] = Field(default_factory=dict)


class AddDetailPageAssetRequest(BaseModel):
    """把一次详情页大纲生成结果挂到工作台资产下。"""

    title: str | None = None
    content: dict[str, Any] = Field(default_factory=dict)
