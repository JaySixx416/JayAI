"""Validated boundaries for future engine implementations; no tools execute here."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class JobState(StrEnum):
    RECEIVED = "RECEIVED"
    PLANNING = "PLANNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    EXECUTING = "EXECUTING"
    OBSERVING = "OBSERVING"
    REPLANNING = "REPLANNING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Risk(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PolicyMode(StrEnum):
    ALWAYS_ASK = "ALWAYS_ASK"
    ASK_HIGH_RISK = "ASK_HIGH_RISK"
    APPROVE_SCOPE = "APPROVE_SCOPE"
    NEVER_ALLOW = "NEVER_ALLOW"


class Limits(BaseModel):
    max_steps: int = Field(default=30, ge=1, le=1000)
    max_tool_calls: int = Field(default=100, ge=1, le=10000)
    max_retries: int = Field(default=2, ge=0, le=10)
    max_runtime_seconds: int = Field(default=900, ge=1, le=86400)
    max_cost_usd: float = Field(default=0.0, ge=0, le=10000)


class PermissionSpec(BaseModel):
    resource: str = Field(min_length=1)
    actions: list[str] = Field(min_length=1)
    risk: Risk
    mode: PolicyMode


class ToolSpec(BaseModel):
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permission: PermissionSpec
    timeout_seconds: int = Field(ge=1, le=3600)
    max_retries: int = Field(ge=0, le=10)


class SkillSpec(BaseModel):
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    instructions: str
    tool_ids: list[str]
    permissions: list[PermissionSpec]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    requires_approval: bool
    verification: str


class ConnectorSpec(BaseModel):
    id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    oauth_scopes: list[str]
    tool_ids: list[str]
    enabled: bool = False


class LearningRecord(BaseModel):
    kind: str = Field(min_length=1)
    source: str = Field(min_length=1)
    explicit: bool
    evidence_count: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)
    observation: str
