from uuid import uuid4

from fastapi.testclient import TestClient

from jayai.main import app, plan_digest, repository


class RunStore:
    def __init__(self, user):
        self.user = user
        self.job = uuid4()
        self.state = "WAITING_FOR_APPROVAL"
        self.plan = {"summary": "Inspect PC", "steps": ["Read system status"], "action": "pc_health"}
        self.result = None
        self.paused = False

    def get_job(self, owner, job):
        return {"state": self.state} if owner == self.user and job == self.job else None

    def get_plan(self, owner, job):
        return self.plan if owner == self.user and job == self.job else None

    def get_result(self, owner, job):
        return self.result if owner == self.user and job == self.job else None

    def is_paused(self, owner):
        return self.paused

    def record_approval_decision(self, owner, job, digest, decision, reason=""):
        assert owner == self.user and job == self.job
        return {"plan_sha256": digest, "decision": decision, "reason": reason}

    def transition_job(self, owner, job, target, reason):
        assert owner == self.user and job == self.job
        self.state = target.value

    def save_result(self, owner, job, result):
        assert self.state == "VERIFYING"
        self.result = result


def test_approved_read_only_pc_check_verifies_and_is_tenant_scoped(monkeypatch):
    user = uuid4()
    key = "k" * 32
    db = RunStore(user)
    monkeypatch.setenv("JAYAI_ENV", "development")
    monkeypatch.setenv("JAYAI_DEV_API_KEY", key)
    monkeypatch.setenv("JAYAI_DEV_USER_ID", str(user))
    monkeypatch.setattr("jayai.maintenance.check", lambda: {
        "scope": "Linux environment", "checked_at": "2026-09-27T00:00:00+00:00",
        "free_percent": 80, "findings": []})
    app.dependency_overrides[repository] = lambda: db
    try:
        with TestClient(app) as client:
            headers = {"X-JayAI-Key": key}
            path = f"/jobs/{db.job}/run"
            assert client.post(path, json={"plan_sha256": "0" * 64}, headers=headers).status_code == 409
            assert db.state == "WAITING_FOR_APPROVAL"
            db.paused = True
            approved = {"plan_sha256": plan_digest(db.plan)}
            assert client.post(path, json=approved, headers=headers).status_code == 409
            db.paused = False
            result = client.post(path, json=approved, headers=headers)
            assert result.status_code == 200
            assert result.json()["report"]["free_percent"] == 80
            assert db.state == "COMPLETED"
            assert client.post(path, json=approved, headers=headers).status_code == 409
            assert client.get(f"/jobs/{db.job}/result", headers=headers).json() == result.json()
            monkeypatch.setenv("JAYAI_DEV_USER_ID", str(uuid4()))
            assert client.get(f"/jobs/{db.job}/result", headers=headers).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_approved_process_list_is_read_only_and_saved(monkeypatch):
    user = uuid4()
    key = "k" * 32
    db = RunStore(user)
    db.plan = {"summary": "List running apps", "steps": ["Read process inventory"], "action": "pc_processes"}
    monkeypatch.setenv("JAYAI_ENV", "development")
    monkeypatch.setenv("JAYAI_DEV_API_KEY", key)
    monkeypatch.setenv("JAYAI_DEV_USER_ID", str(user))
    monkeypatch.setattr("jayai.maintenance.running_processes", lambda: {
        "scope": "Linux environment", "checked_at": "2026-09-27T00:00:00+00:00",
        "processes": [{"name": "Explorer", "id": 42}]})
    app.dependency_overrides[repository] = lambda: db
    try:
        with TestClient(app) as client:
            result = client.post(f"/jobs/{db.job}/run", headers={"X-JayAI-Key": key},
                                 json={"plan_sha256": plan_digest(db.plan)})
            assert result.status_code == 200
            assert result.json()["kind"] == "pc_processes"
            assert db.state == "COMPLETED"
    finally:
        app.dependency_overrides.clear()
