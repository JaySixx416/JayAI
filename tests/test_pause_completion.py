from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from jayai.main import Approval, run_approved_job
from jayai.plans import plan_digest


class PauseStore:
    def __init__(self):
        self.user = uuid4()
        self.job = uuid4()
        self.state = "WAITING_FOR_APPROVAL"
        self.paused = False
        self.plan = {"summary": "List processes", "steps": ["Read process inventory"],
                     "action": "pc_processes"}
        self.result = None

    def get_job(self, user, job):
        return {"state": self.state} if (user, job) == (self.user, self.job) else None

    def get_plan(self, user, job):
        return self.plan if (user, job) == (self.user, self.job) else None

    def is_paused(self, user):
        return self.paused

    def admit_approved_plan(self, user, job, digest):
        assert (user, job, digest) == (self.user, self.job, plan_digest(self.plan))
        assert not self.paused
        self.state = "EXECUTING"

    def transition_job(self, user, job, target, _reason):
        assert (user, job) == (self.user, self.job)
        if self.paused and target.value not in ("OBSERVING", "VERIFYING", "COMPLETED"):
            raise RuntimeError("User actions paused")
        self.state = target.value

    def save_result(self, user, job, result):
        assert self.state == "VERIFYING"
        self.result = result


def test_pause_after_admission_allows_completion_but_blocks_new_admission(monkeypatch):
    db = PauseStore()
    report = {"scope": "Linux environment", "checked_at": datetime.now(timezone.utc).isoformat(),
              "processes": [{"name": "worker", "id": 1}]}

    def check_after_admission():
        db.paused = True
        return report

    monkeypatch.setattr("jayai.maintenance.running_processes", check_after_admission)
    result = run_approved_job(db.job, Approval(plan_sha256=plan_digest(db.plan)), db.user, db)

    assert result["report"] == report
    assert db.result == result
    assert db.state == "COMPLETED"

    db.state = "WAITING_FOR_APPROVAL"
    with pytest.raises(HTTPException, match="User actions paused"):
        run_approved_job(db.job, Approval(plan_sha256=plan_digest(db.plan)), db.user, db)
