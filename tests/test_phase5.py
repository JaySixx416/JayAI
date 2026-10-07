from uuid import uuid4

import pytest
from jsonschema import ValidationError

from jayai.contracts import PermissionSpec, PolicyMode, Risk, SkillSpec
from jayai.registry import Decision, built_in_registry, decide


class MemoryStore:
    def __init__(self):
        self.skills = {}
        self.modes = []
        self.calls = []
        self.paused = False

    def is_paused(self, user):
        return self.paused

    def install_skill(self, user, skill):
        self.skills[(user, skill.id)] = skill

    def get_skill(self, user, skill_id):
        return self.skills.get((user, skill_id))

    def permission_modes(self, user, resource, action):
        return self.modes if resource == "text.analysis" and action == "count" else []

    def start_tool_call(self, user, skill_id, tool_id):
        self.calls.append("STARTED")
        return uuid4()

    def finish_tool_call(self, user, call_id, success):
        self.calls.append("SUCCEEDED" if success else "FAILED")


def text_skill(requires_approval=False):
    return SkillSpec(
        id="text.summary", version="1.0.0", instructions="Count words", tool_ids=["text.count_words"],
        permissions=[PermissionSpec(resource="text.analysis", actions=["count"], risk=Risk.LOW,
                                    mode=PolicyMode.APPROVE_SCOPE)],
        input_schema={"type": "object"}, output_schema={"type": "object"},
        requires_approval=requires_approval, verification="Compare count to input",
    )


def test_registry_denies_without_permission_and_validates_input():
    store = MemoryStore()
    user = uuid4()
    registry = built_in_registry(store)
    registry.install(user, text_skill())
    with pytest.raises(PermissionError):
        registry.invoke(user, "text.summary", "text.count_words", {"text": "two words"})
    assert store.calls == []
    store.modes = ["APPROVE_SCOPE"]
    with pytest.raises(ValidationError):
        registry.invoke(user, "text.summary", "text.count_words", {"extra": 1})
    assert store.calls == []
    assert registry.invoke(user, "text.summary", "text.count_words", {"text": "two words"}) == {"count": 2}
    assert store.calls == ["STARTED", "SUCCEEDED"]


def test_skill_cannot_add_undeclared_tool_or_bypass_approval():
    store = MemoryStore()
    registry = built_in_registry(store)
    user = uuid4()
    invalid = text_skill()
    invalid.permissions = []
    with pytest.raises(ValueError):
        registry.install(user, invalid)
    registry.install(user, text_skill(requires_approval=True))
    store.modes = ["APPROVE_SCOPE"]
    with pytest.raises(PermissionError, match="WAIT_FOR_APPROVAL"):
        registry.invoke(user, "text.summary", "text.count_words", {"text": "hello"})
    assert store.calls == []


def test_never_allow_overrides_other_policies():
    permission = PermissionSpec(resource="text.analysis", actions=["count"], risk=Risk.LOW,
                                mode=PolicyMode.APPROVE_SCOPE)
    assert decide(permission, ["APPROVE_SCOPE", "NEVER_ALLOW"]) == Decision.DENY
    assert decide(permission, ["UNRECOGNIZED"]) == Decision.DENY


def test_pause_blocks_tool_before_execution_and_audit_start():
    store = MemoryStore()
    store.modes = ["APPROVE_SCOPE"]
    user = uuid4()
    registry = built_in_registry(store)
    registry.install(user, text_skill())
    store.paused = True
    with pytest.raises(PermissionError, match="paused"):
        registry.invoke(user, "text.summary", "text.count_words", {"text": "hello"})
    assert store.calls == []
