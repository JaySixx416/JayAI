from datetime import datetime, timezone
from uuid import uuid4

import pytest

from jayai.contracts import Limits
from jayai.db import Repository


class Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class Connection:
    def __init__(self, responses):
        self.responses = responses
        self.sql = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, _params=()):
        self.sql.append(statement)
        for fragment, result in self.responses:
            if fragment in statement:
                return Result(result)
        if statement.startswith("INSERT INTO tool_calls"):
            return Result(None)
        raise AssertionError(f"Unexpected query: {statement}")


def test_job_bound_tool_requires_idempotency_key_before_database_access():
    class ForbiddenStore:
        def start_tool_call(self, *_args, **_kwargs):
            raise AssertionError("Invalid calls must be rejected before insertion")

    with pytest.raises(ValueError, match="idempotency key"):
        Repository("postgresql://unused").start_tool_call(uuid4(), "s", "t", uuid4())


def test_tool_call_budget_is_checked_before_insert(monkeypatch):
    user, job = uuid4(), uuid4()
    fake = Connection([
        ("FROM user_controls", (False,)),
        ("FROM jobs", (Limits(max_tool_calls=1).model_dump(), datetime.now(timezone.utc), "WAITING_FOR_APPROVAL")),
        ("count(*) FROM tool_calls", (1,)),
    ])
    monkeypatch.setattr("jayai.db.psycopg.connect", lambda *_args, **_kwargs: fake)
    with pytest.raises(PermissionError, match="tool-call limit"):
        Repository("postgresql://unused").start_tool_call(user, "s", "t", job, "step-1")
    assert not any(sql.startswith("INSERT INTO tool_calls") for sql in fake.sql)


def test_duplicate_call_key_is_blocked_before_side_effect_admission(monkeypatch):
    user, job = uuid4(), uuid4()
    fake = Connection([
        ("FROM user_controls", (False,)),
        ("FROM jobs", (Limits().model_dump(), datetime.now(timezone.utc), "WAITING_FOR_APPROVAL")),
        ("count(*) FROM tool_calls", (0,)),
        ("EXTRACT(EPOCH", (False,)),
        ("idempotency_key=%s", (uuid4(),)),
    ])
    monkeypatch.setattr("jayai.db.psycopg.connect", lambda *_args, **_kwargs: fake)
    with pytest.raises(PermissionError, match="Duplicate tool call"):
        Repository("postgresql://unused").start_tool_call(user, "s", "t", job, "step-1")
    assert not any(sql.startswith("INSERT INTO tool_calls") for sql in fake.sql)


def test_tool_call_migration_has_unique_job_idempotency_constraint():
    from jayai.db import MIGRATIONS
    sql = (MIGRATIONS / "011_tool_call_limits.sql").read_text(encoding="utf-8")
    assert "UNIQUE INDEX tool_calls_job_idempotency" in sql
    assert "REFERENCES jobs(id)" in sql
