from datetime import datetime, timezone
from uuid import uuid4

import pytest

from jayai.db import MIGRATIONS, Repository
from jayai.plans import expected_evidence, plan_digest


class Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class Connection:
    def __init__(self, plan, existing=None, state="WAITING_FOR_APPROVAL"):
        self.plan = plan
        self.existing = existing
        self.state = state
        self.sql = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, _params=()):
        self.sql.append(statement)
        if "FROM user_controls" in statement:
            return Result({"paused": False})
        if "JOIN job_plans" in statement:
            return Result({"state": self.state, "plan": self.plan})
        if "FROM approval_decisions" in statement:
            return Result(self.existing)
        return Result(None)


def test_decision_storage_binds_user_job_and_digest_and_audits(monkeypatch):
    user, job = uuid4(), uuid4()
    plan = {"summary": "Inspect", "steps": ["Check"], "action": "pc_health"}
    fake = Connection(plan)
    monkeypatch.setattr("jayai.db.psycopg.connect", lambda *_args, **_kwargs: fake)
    saved = Repository("postgresql://unused").record_approval_decision(
        user, job, plan_digest(plan), "APPROVED")
    assert saved["decision"] == "APPROVED"
    assert any("WHERE j.id=%s AND j.user_id=%s FOR UPDATE OF j" in sql for sql in fake.sql)
    assert any("INSERT INTO approval_decisions" in sql for sql in fake.sql)
    assert any("INSERT INTO audit_events" in sql for sql in fake.sql)


def test_stale_digest_and_changed_decision_never_write(monkeypatch):
    plan = {"summary": "Inspect", "steps": ["Check"], "action": "pc_health"}
    fake = Connection(plan)
    monkeypatch.setattr("jayai.db.psycopg.connect", lambda *_args, **_kwargs: fake)
    with pytest.raises(ValueError, match="Plan digest"):
        Repository("postgresql://unused").record_approval_decision(uuid4(), uuid4(), "0" * 64, "APPROVED")
    assert not any("INSERT INTO approval_decisions" in sql for sql in fake.sql)

    existing = {"id": uuid4(), "decision": "APPROVED", "reason": "", "decided_at": datetime.now(timezone.utc)}
    fake = Connection(plan, existing=existing)
    monkeypatch.setattr("jayai.db.psycopg.connect", lambda *_args, **_kwargs: fake)
    with pytest.raises(ValueError, match="different decision"):
        Repository("postgresql://unused").record_approval_decision(
            uuid4(), uuid4(), plan_digest(plan), "REJECTED")
    assert not any("INSERT INTO approval_decisions" in sql for sql in fake.sql)


def test_plan_evidence_is_server_defined_for_only_read_only_actions():
    assert "Update status when supported" in expected_evidence("pc_health")
    assert expected_evidence("none") == []


def test_approval_migration_records_one_decision_per_immutable_plan():
    sql = (MIGRATIONS / "010_approval_decisions.sql").read_text(encoding="utf-8")
    assert "UNIQUE (job_id, plan_sha256)" in sql
    assert "CHECK (decision IN ('APPROVED', 'REJECTED'))" in sql
