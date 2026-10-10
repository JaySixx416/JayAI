from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from jayai.main import app, repository


class FakeRepository:
    def __init__(self) -> None:
        self.jobs: dict[UUID, tuple[UUID, dict]] = {}

    def create_job(self, user_id, goal, limits):
        job_id = uuid4()
        self.jobs[job_id] = (user_id, {"id": job_id, "goal": goal, "state": "RECEIVED", "limits": limits.model_dump()})
        return job_id

    def get_job(self, user_id, job_id):
        record = self.jobs.get(job_id)
        return record[1] if record and record[0] == user_id else None


def test_job_round_trip_requires_key_and_tenant_scope(monkeypatch):
    user_id = uuid4()
    key = "k" * 32
    monkeypatch.setenv("JAYAI_ENV", "development")
    monkeypatch.setenv("JAYAI_DEV_API_KEY", key)
    monkeypatch.setenv("JAYAI_DEV_USER_ID", str(user_id))
    fake = FakeRepository()
    app.dependency_overrides[repository] = lambda: fake
    try:
        with TestClient(app) as client:
            assert client.post("/jobs", json={"goal": "Check report"}).status_code == 401
            assert client.post("/jobs", headers={"X-JayAI-Key": key}, json={"goal": "  "}).status_code == 422
            created = client.post("/jobs", headers={"X-JayAI-Key": key}, json={"goal": "Check report"})
            assert created.status_code == 201
            job_id = UUID(created.json()["id"])
            assert created.json()["state"] == "RECEIVED"
            assert client.get(f"/jobs/{job_id}", headers={"X-JayAI-Key": key}).json()["goal"] == "Check report"
            monkeypatch.setenv("JAYAI_DEV_USER_ID", str(uuid4()))
            assert client.get(f"/jobs/{job_id}", headers={"X-JayAI-Key": key}).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_development_api_disabled_by_default(monkeypatch):
    monkeypatch.delenv("JAYAI_ENV", raising=False)
    assert TestClient(app).post("/jobs", json={"goal": "Anything"}).status_code == 503
