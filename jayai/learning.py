"""Explicit, user-controlled preference learning with simple secret filtering."""

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:password|passcode|api[_ -]?key|access[_ -]?token|secret|private key)\s*[:=]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{12,}"),
)


class LearningInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern="^(format|workflow|environment|accessibility)$")
    observation: str = Field(min_length=1, max_length=500)
    source: str = Field(pattern="^(USER_STATED|USER_CORRECTION)$")
    evidence_count: int = Field(default=1, ge=1, le=1000)
    confidence: float = Field(default=1.0, ge=0, le=1)

    @field_validator("observation")
    @classmethod
    def reject_secret_like_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Learning observation cannot be blank")
        if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
            raise ValueError("Do not save credentials or secret-like values as learning")
        return value.strip()


def routine_suggestions(repeat_patterns: list[dict[str, Any]], episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build review-only suggestions from repeated verified task categories.

    Suggestions contain no executable action, scope, or schedule. Those details
    require separate user decisions and routine execution is not implemented.
    """
    verified: dict[str, list[dict[str, Any]]] = {}
    for episode in episodes:
        if episode.get("outcome") != "VERIFIED":
            continue
        task_kind = episode.get("task_kind")
        if not isinstance(task_kind, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", task_kind):
            continue
        verified.setdefault(task_kind, []).append(episode)

    suggestions = []
    for pattern in repeat_patterns:
        task_kind = pattern.get("task_kind")
        count = pattern.get("verified_count")
        if not isinstance(task_kind, str) or type(count) is not int or count < 2:
            continue
        examples = verified.get(task_kind, [])[:3]
        if len(examples) < 2:
            continue
        supporting = []
        for item in examples:
            created_at = item.get("created_at")
            if isinstance(created_at, datetime):
                created_at = created_at.isoformat()
            supporting.append({
                "verified_at": created_at if isinstance(created_at, str) else None,
                "duration_seconds": item.get("duration_seconds"),
            })
        suggestions.append({
            "id": f"repeat-{task_kind}",
            "task_kind": task_kind,
            "verified_count": count,
            "supporting_examples": supporting,
            "scope": None,
            "schedule": None,
            "actions": [],
            "approval_required": ["scope", "schedule", "actions"],
            "automatic_execution": False,
        })
    return suggestions
