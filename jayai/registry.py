"""Server-owned tools, user-installed skill manifests, and deny-by-default policy."""

from collections.abc import Callable
from enum import StrEnum
from uuid import UUID

from jsonschema import Draft202012Validator, validate

from jayai.contracts import PermissionSpec, PolicyMode, Risk, SkillSpec, ToolSpec
from jayai.db import Repository


class Decision(StrEnum):
    ALLOW = "ALLOW"
    WAIT_FOR_APPROVAL = "WAIT_FOR_APPROVAL"
    DENY = "DENY"


def decide(permission: PermissionSpec, modes: list[str], requires_approval: bool = False) -> Decision:
    known = {mode.value for mode in PolicyMode}
    if not modes or any(mode not in known for mode in modes):
        return Decision.DENY
    if permission.mode == PolicyMode.NEVER_ALLOW or PolicyMode.NEVER_ALLOW.value in modes:
        return Decision.DENY
    if requires_approval or permission.mode == PolicyMode.ALWAYS_ASK or PolicyMode.ALWAYS_ASK.value in modes:
        return Decision.WAIT_FOR_APPROVAL
    # Medium and high risk tools always require a separate exact-action approval.
    # An APPROVE_SCOPE grant can authorize only low-risk reads/analysis.
    if permission.risk in (Risk.MEDIUM, Risk.HIGH):
        return Decision.WAIT_FOR_APPROVAL
    return Decision.ALLOW


class Registry:
    def __init__(self, repository: Repository):
        self.repository = repository
        self.tools: dict[str, tuple[ToolSpec, Callable[[UUID, dict], dict]]] = {}

    def register(self, spec: ToolSpec, operation: Callable[[UUID, dict], dict]) -> None:
        if spec.id in self.tools:
            raise ValueError("Tool already registered")
        Draft202012Validator.check_schema(spec.input_schema)
        Draft202012Validator.check_schema(spec.output_schema)
        if hasattr(self.repository, "sync_tool"):
            self.repository.sync_tool(spec)
        self.tools[spec.id] = (spec, operation)

    def install(self, user_id: UUID, skill: SkillSpec) -> None:
        Draft202012Validator.check_schema(skill.input_schema)
        Draft202012Validator.check_schema(skill.output_schema)
        if not skill.tool_ids:
            raise ValueError("Skill requires a tool")
        for tool_id in skill.tool_ids:
            if tool_id not in self.tools:
                raise ValueError(f"Unknown tool: {tool_id}")
            required = self.tools[tool_id][0].permission
            if not any(p.resource == required.resource and set(required.actions) <= set(p.actions)
                       for p in skill.permissions):
                raise ValueError(f"Skill does not declare tool permission: {tool_id}")
        self.repository.install_skill(user_id, skill)

    def invoke(self, user_id: UUID, skill_id: str, tool_id: str, inputs: dict, *,
               job_id: UUID | None = None, idempotency_key: str | None = None) -> dict:
        skill = self.repository.get_skill(user_id, skill_id)
        if skill is None or tool_id not in skill.tool_ids:
            raise PermissionError("Skill disabled, missing, or tool not installed")
        registered = self.tools.get(tool_id)
        if registered is None:
            raise PermissionError("Tool unavailable")
        spec, operation = registered
        permission = spec.permission
        matching = [p for p in skill.permissions if p.resource == permission.resource
                    and set(permission.actions) <= set(p.actions)]
        if not matching:
            raise PermissionError("Skill permission mismatch")
        per_action = [self.repository.permission_modes(user_id, permission.resource, action)
                      for action in permission.actions]
        if any(not matches for matches in per_action):
            raise PermissionError("No permission for tool action")
        modes = [mode for matches in per_action for mode in matches]
        modes.extend(p.mode.value for p in matching)
        decision = decide(permission, modes, skill.requires_approval)
        if decision != Decision.ALLOW:
            raise PermissionError(f"Tool request: {decision.value}")
        validate(inputs, spec.input_schema)
        if self.repository.is_paused(user_id):
            raise PermissionError("User actions paused")
        if job_id is not None and not idempotency_key:
            raise ValueError("Job-bound tools require an idempotency key")
        call_id = self.repository.start_tool_call(user_id, skill_id, tool_id, job_id, idempotency_key) \
            if job_id is not None else self.repository.start_tool_call(user_id, skill_id, tool_id)
        try:
            result = operation(user_id, inputs)
            validate(result, spec.output_schema)
        except Exception:
            self.repository.finish_tool_call(user_id, call_id, success=False)
            raise
        self.repository.finish_tool_call(user_id, call_id, success=True)
        return result


def built_in_registry(repository: Repository) -> Registry:
    registry = Registry(repository)
    registry.register(
        ToolSpec(
            id="text.count_words", description="Count whitespace-separated words in supplied text",
            input_schema={"type": "object", "properties": {"text": {"type": "string", "maxLength": 10000}},
                          "required": ["text"], "additionalProperties": False},
            output_schema={"type": "object", "properties": {"count": {"type": "integer", "minimum": 0}},
                           "required": ["count"], "additionalProperties": False},
            permission=PermissionSpec(resource="text.analysis", actions=["count"], risk=Risk.LOW,
                                      mode=PolicyMode.APPROVE_SCOPE),
            timeout_seconds=5, max_retries=0,
        ),
        lambda _user_id, args: {"count": len(args["text"].split())},
    )
    return registry
