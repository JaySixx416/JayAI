from uuid import uuid4

from fastapi.testclient import TestClient

from jayai.main import app, repository, plan_digest


class ApprovalStore:
    def __init__(self, user):
        self.user = user
        self.job = uuid4()
        self.state = "WAITING_FOR_APPROVAL"
        self.paused = False
        self.plan = {"summary": "Review only", "steps": ["Inspect the local status"],
                     "action": "none", "expected_evidence": []}
        self.decision = None

    def get_job(self, user, job):
        return {"state": self.state} if user == self.user and job == self.job else None

    def get_plan(self, user, job):
        return self.plan if user == self.user and job == self.job else None

    def get_approval_decision(self, user, job):
        return self.decision if user == self.user and job == self.job else None

    def record_approval_decision(self, user, job, digest, decision, reason=""):
        assert self.get_job(user, job) and self.state == "WAITING_FOR_APPROVAL"
        assert digest == plan_digest(self.plan)
        if self.decision and self.decision["decision"] != decision:
            raise ValueError("A different decision is already recorded for this plan")
        self.decision = {"plan_sha256": digest, "decision": decision, "reason": reason}
        return self.decision

    def transition_job(self, user, job, target, reason):
        assert self.get_job(user, job)
        self.state = target.value

    def is_paused(self, user):
        return self.paused


def setup_api(monkeypatch, user):
    monkeypatch.setenv("JAYAI_ENV", "development")
    monkeypatch.setenv("JAYAI_DEV_API_KEY", "k" * 32)
    monkeypatch.setenv("JAYAI_DEV_USER_ID", str(user))
    return {"X-JayAI-Key": "k" * 32}


def test_reject_records_exact_plan_and_cancels_without_running_action(monkeypatch):
    user = uuid4()
    store = ApprovalStore(user)
    headers = setup_api(monkeypatch, user)
    app.dependency_overrides[repository] = lambda: store
    try:
        with TestClient(app) as client:
            response = client.post(f"/jobs/{store.job}/reject", headers=headers,
                                   json={"plan_sha256": plan_digest(store.plan), "reason": "Not needed"})
            assert response.status_code == 200
            assert response.json() == {"decision": "REJECTED", "state": "CANCELLED"}
            assert store.decision["decision"] == "REJECTED"
            assert store.decision["reason"] == "Not needed"
            assert store.state == "CANCELLED"
            assert client.get(f"/jobs/{store.job}/decision", headers=headers).json()["decision"]["decision"] == "REJECTED"
            approved = client.post(f"/jobs/{store.job}/run", headers=headers,
                                   json={"plan_sha256": plan_digest(store.plan)})
            assert approved.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_stale_plan_cannot_be_rejected_and_other_tenant_cannot_read_decision(monkeypatch):
    user = uuid4()
    store = ApprovalStore(user)
    headers = setup_api(monkeypatch, user)
    app.dependency_overrides[repository] = lambda: store
    try:
        with TestClient(app) as client:
            stale = client.post(f"/jobs/{store.job}/reject", headers=headers,
                               json={"plan_sha256": "0" * 64})
            assert stale.status_code == 409 and store.decision is None
            monkeypatch.setenv("JAYAI_DEV_USER_ID", str(uuid4()))
            assert client.get(f"/jobs/{store.job}/decision", headers=headers).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_pause_blocks_approval_before_decision(monkeypatch):
    user = uuid4()
    store = ApprovalStore(user)
    store.paused = True
    headers = setup_api(monkeypatch, user)
    app.dependency_overrides[repository] = lambda: store
    try:
        with TestClient(app) as client:
            response = client.post(f"/jobs/{store.job}/run", headers=headers,
                                   json={"plan_sha256": plan_digest(store.plan)})
            assert response.status_code == 409
            assert store.decision is None
            assert store.state == "WAITING_FOR_APPROVAL"
    finally:
        app.dependency_overrides.clear()
