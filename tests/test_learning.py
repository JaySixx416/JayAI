from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from jayai.learning import LearningInput, routine_suggestions
from jayai.main import app, repository


@pytest.mark.parametrize("observation", [
    "password: don't-store-this", "api_key=sk-abcdefghijklmnopqrstuvwxyz",
    "Bearer abcdefghijklmnopqrstuvwxyz",
])
def test_learning_rejects_secret_like_values(observation):
    with pytest.raises(ValidationError, match="secret-like"):
        LearningInput(kind="workflow", source="USER_STATED", observation=observation)


def test_learning_api_is_user_scoped_editable_and_erasable(monkeypatch):
    user = uuid4()
    key = "k" * 32
    monkeypatch.setenv("JAYAI_ENV", "development")
    monkeypatch.setenv("JAYAI_DEV_API_KEY", key)
    monkeypatch.setenv("JAYAI_DEV_USER_ID", str(user))

    class Store:
        def __init__(self):
            self.records = {}
            self.episodes = [
                {"task_kind": "pc_health", "outcome": "VERIFIED", "duration_seconds": 2.5,
                 "created_at": datetime(2026, 9, 29, 10, tzinfo=timezone.utc)},
                {"task_kind": "pc_health", "outcome": "VERIFIED", "duration_seconds": 3.0,
                 "created_at": "2026-09-30T10:00:00+00:00"},
            ]

        def list_learning(self, owner):
            assert owner == user
            patterns = [{"task_kind": "pc_health", "verified_count": 2}] if self.episodes else []
            return {"records": list(self.records.values()), "episodes": list(self.episodes),
                    "repeat_patterns": patterns}

        def save_learning(self, owner, record_key, body):
            assert owner == user
            record = {"record_key": record_key, **body, "explicit": True}
            self.records[record_key] = record
            return record

        def delete_learning(self, owner, record_key=None):
            assert owner == user
            if record_key is None:
                count = len(self.records) + len(self.episodes)
                self.records.clear()
                self.episodes.clear()
                return count
            return int(self.records.pop(record_key, None) is not None)

    store = Store()
    app.dependency_overrides[repository] = lambda: store
    headers = {"X-JayAI-Key": key}
    try:
        with TestClient(app) as client:
            assert client.get("/learning").status_code == 401
            assert client.get("/learning/export").status_code == 401
            saved = client.put("/learning/answer_style", headers=headers,
                               json={"kind": "format", "source": "USER_STATED",
                                     "observation": "Label commands for the device I'm using."})
            assert saved.status_code == 200 and saved.json()["explicit"] is True
            corrected = client.put("/learning/answer_style", headers=headers,
                                   json={"kind": "format", "source": "USER_CORRECTION",
                                         "observation": "Label commands Windows PC or Chromebook."})
            assert corrected.status_code == 200
            view = client.get("/learning", headers=headers).json()
            assert view["records"][0]["observation"] == "Label commands Windows PC or Chromebook."
            assert view["repeat_patterns"] == [{"task_kind": "pc_health", "verified_count": 2}]
            assert len(view["routine_suggestions"]) == 1
            suggestion = view["routine_suggestions"][0]
            assert suggestion["automatic_execution"] is False
            assert suggestion["scope"] is None and suggestion["schedule"] is None and suggestion["actions"] == []
            exported = client.get("/learning/export", headers=headers)
            assert exported.status_code == 200
            assert exported.headers["content-disposition"].endswith('filename="jayai-learning-export.json"')
            payload = exported.json()
            assert payload["schema_version"] == 1
            assert payload["episodes"][0]["created_at"] == "2026-09-29T10:00:00+00:00"
            assert payload["routine_suggestions"] == view["routine_suggestions"]
            assert payload["records"][0]["record_key"] == "answer_style"
            assert client.delete("/learning/answer_style", headers=headers).json() == {"deleted": True}
            assert client.put("/learning/new_note", headers=headers,
                              json={"kind": "workflow", "source": "USER_CORRECTION",
                                    "observation": "This cannot be inferred."}).status_code == 404
            assert client.delete("/learning", headers=headers).json() == {"deleted": 2}
    finally:
        app.dependency_overrides.clear()


def test_routine_suggestions_need_two_verified_examples():
    patterns = [{"task_kind": "pc_health", "verified_count": 2}]
    one_verified = [{"task_kind": "pc_health", "outcome": "VERIFIED"}]
    failed_only = [
        {"task_kind": "pc_health", "outcome": "FAILED"},
        {"task_kind": "pc_health", "outcome": "FAILED"},
    ]
    assert routine_suggestions(patterns, one_verified) == []
    assert routine_suggestions(patterns, failed_only) == []
