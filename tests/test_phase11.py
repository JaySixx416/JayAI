from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from jayai.contracts import JobState, Limits
from jayai.db import Repository
from jayai.main import app, repository


class ControlsStore:
    def __init__(self, user):
        self.user = user
        self.job = uuid4()
        self.state = JobState.RECEIVED
        self.paused = False

    def get_job(self, user, job):
        if user != self.user or job != self.job:
            return None
        return {"id": job, "goal": "Check files", "state": self.state.value,
                "limits": Limits().model_dump()}

    def transition_job(self, user, job, target, reason):
        assert self.get_job(user, job)
        if self.state == JobState.CANCELLED:
            raise ValueError("Already cancelled")
        self.state = target

    def set_paused(self, user, paused):
        assert user == self.user
        self.paused = paused


def test_stop_controls_require_auth_and_tenant(monkeypatch):
    user = uuid4()
    key = "k" * 32
    db = ControlsStore(user)
    monkeypatch.setenv("JAYAI_ENV", "development")
    monkeypatch.setenv("JAYAI_DEV_API_KEY", key)
    monkeypatch.setenv("JAYAI_DEV_USER_ID", str(user))
    app.dependency_overrides[repository] = lambda: db
    try:
        with TestClient(app) as client:
            headers = {"X-JayAI-Key": key}
            assert client.post("/control/pause").status_code == 401
            assert client.post("/control/pause", headers=headers).json() == {"paused": True}
            assert db.paused
            assert client.post(f"/jobs/{db.job}/cancel", headers=headers).json()["state"] == "CANCELLED"
            assert client.post(f"/jobs/{db.job}/cancel", headers=headers).status_code == 409
            assert client.post("/control/resume", headers=headers).json() == {"paused": False}
            monkeypatch.setenv("JAYAI_DEV_USER_ID", str(uuid4()))
            assert client.post(f"/jobs/{db.job}/cancel", headers=headers).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_tool_start_rechecks_pause_inside_database_transaction(monkeypatch):
    statements = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params):
            statements.append(sql)
            return self

        def fetchone(self):
            return (True,)

    monkeypatch.setattr("jayai.db.psycopg.connect", lambda *_args: Connection())
    with pytest.raises(PermissionError, match="paused"):
        Repository("postgresql://unused").start_tool_call(uuid4(), "skill", "tool")
    assert len(statements) == 1
    assert "FOR UPDATE" in statements[0]
