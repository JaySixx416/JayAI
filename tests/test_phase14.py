from uuid import uuid4

from fastapi.testclient import TestClient

from jayai.main import app, repository
from jayai.planner import ProposedPlan


def test_dashboard_only_in_development_and_job_list_is_scoped(monkeypatch):
    user = uuid4()
    key = "k" * 32
    monkeypatch.delenv("JAYAI_ENV", raising=False)
    with TestClient(app) as client:
        assert client.get("/").status_code == 503
    monkeypatch.setenv("JAYAI_ENV", "development")
    monkeypatch.setenv("JAYAI_DEV_API_KEY", key)
    monkeypatch.setenv("JAYAI_DEV_USER_ID", str(user))

    class Store:
        def list_jobs(self, owner):
            assert owner == user
            return [{"id": uuid4(), "goal": "Check PC", "state": "RECEIVED", "limits": {}}]

    app.dependency_overrides[repository] = Store
    try:
        with TestClient(app) as client:
            assert "JayAI" in client.get("/").text
            assert client.get("/jobs").status_code == 401
            assert client.get("/jobs", headers={"X-JayAI-Key": key}).json()[0]["goal"] == "Check PC"
    finally:
        app.dependency_overrides.clear()


def test_dashboard_task_flow_from_goal_to_verified_pc_result(monkeypatch):
    user = uuid4()
    key = "k" * 32
    monkeypatch.setenv("JAYAI_ENV", "development")
    monkeypatch.setenv("JAYAI_DEV_API_KEY", key)
    monkeypatch.setenv("JAYAI_DEV_USER_ID", str(user))
    monkeypatch.setattr("jayai.planner.propose", lambda _goal: ProposedPlan(
        summary="Inspect PC health", steps=["Read disk and update status"], action="pc_health"))
    monkeypatch.setattr("jayai.maintenance.check", lambda: {"scope": "Linux environment",
                                                               "checked_at": "2026-09-27T00:00:00+00:00",
                                                               "free_percent": 90, "findings": [],
                                                               "updates": {"start_type": "Manual", "reboot_required": False}})

    class Store:
        jobs = {}
        plans = {}
        results = {}

        def create_job(self, owner, goal, limits):
            job = uuid4()
            self.jobs[job] = {"id": job, "user_id": owner, "goal": goal,
                              "state": "RECEIVED", "limits": limits.model_dump()}
            return job

        def get_job(self, owner, job):
            row = self.jobs.get(job)
            return row if row and row["user_id"] == owner else None

        def list_jobs(self, owner):
            return [row for row in self.jobs.values() if row["user_id"] == owner]

        def is_paused(self, owner):
            return False

        def get_plan(self, owner, job):
            return self.plans.get(job) if self.get_job(owner, job) else None

        def save_plan(self, owner, job, plan):
            assert self.get_job(owner, job)
            self.plans[job] = plan

        def record_approval_decision(self, owner, job, digest, decision, reason=""):
            assert self.get_job(owner, job)
            return {"plan_sha256": digest, "decision": decision, "reason": reason}

        def get_approval_decision(self, owner, job):
            return None

        def reserve_plan_request(self, owner, job):
            assert self.get_job(owner, job)

        def finish_plan_request(self, owner, job, success):
            assert self.get_job(owner, job) and success

        def transition_job(self, owner, job, target, reason):
            assert self.get_job(owner, job)
            self.jobs[job]["state"] = target.value

        def get_result(self, owner, job):
            return self.results.get(job) if self.get_job(owner, job) else None

        def save_result(self, owner, job, result):
            assert self.get_job(owner, job)["state"] == "VERIFYING"
            self.results[job] = result

    store = Store()
    app.dependency_overrides[repository] = lambda: store
    try:
        with TestClient(app) as client:
            headers = {"X-JayAI-Key": key}
            created = client.post("/jobs", json={"goal": "Check my PC health"}, headers=headers)
            assert created.status_code == 201
            job = created.json()["id"]
            planned = client.post(f"/jobs/{job}/plan", headers=headers)
            assert planned.status_code == 200
            assert client.get(f"/jobs/{job}", headers=headers).json()["state"] == "WAITING_FOR_APPROVAL"
            approved = client.post(f"/jobs/{job}/run", headers=headers,
                                   json={"plan_sha256": planned.json()["sha256"]})
            assert approved.status_code == 200
            assert approved.json()["report"]["free_percent"] == 90
            assert client.get(f"/jobs/{job}/result", headers=headers).json() == approved.json()
            assert client.get(f"/jobs/{job}", headers=headers).json()["state"] == "COMPLETED"
    finally:
        app.dependency_overrides.clear()
