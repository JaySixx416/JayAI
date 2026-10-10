import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from jayai.main import app, repository
from jayai.planner import LOCAL_ENDPOINT, LOCAL_MODEL, ProposedPlan, propose, validate_endpoint
from jayai.db import Repository
from jayai.contracts import JobState, Limits


def test_planner_uses_only_local_model_and_validates_output(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-sent")
    def respond(request):
        body = json.loads(request.content)
        assert str(request.url) == LOCAL_ENDPOINT
        assert request.headers.get("Authorization") is None
        assert "must-not-be-sent" not in request.content.decode()
        assert body["model"] == LOCAL_MODEL
        assert body["stream"] is False
        assert body["format"]["additionalProperties"] is False
        assert body["messages"][1]["content"] == "Count words"
        return httpx.Response(200, json={"done": True, "message": {"content":
            json.dumps({"summary": "Review the text", "steps": ["Count words"], "action": "none"})}})

    plan = propose("Count words", transport=httpx.MockTransport(respond))
    assert plan.steps == ["Count words"]
    assert "must-not-be-sent" not in str(plan)


@pytest.mark.parametrize("endpoint", [
    "https://example.invalid/api/chat",
    "http://192.0.2.10:11434/api/chat",
    "http://127.0.0.1:9000/api/chat",
    "http://127.0.0.1:11434/api/chat?forwarded=1",
    "http://user:secret@127.0.0.1:11434/api/chat",
])
def test_planner_rejects_unmanaged_or_remote_endpoint(monkeypatch, endpoint):
    monkeypatch.setenv("JAYAI_OLLAMA_ENDPOINT", endpoint)
    with pytest.raises(RuntimeError, match="local loopback API"):
        propose("Count words", transport=httpx.MockTransport(
            lambda _request: pytest.fail("remote endpoint must not be contacted")))


def test_planner_accepts_only_managed_loopback_endpoint():
    assert validate_endpoint(LOCAL_ENDPOINT) == LOCAL_ENDPOINT
    assert validate_endpoint("http://localhost:11434/api/chat") == "http://localhost:11434/api/chat"


def test_planner_rejects_empty_steps():
    def respond(_request):
        return httpx.Response(200, json={"done": True, "message": {"content":
            json.dumps({"summary": "A plan", "steps": [" "], "action": "none"})}})
    with pytest.raises(ValueError):
        propose("Count words", transport=httpx.MockTransport(respond))


@pytest.mark.parametrize("payload", [
    [],
    {"done": True, "message": None},
    {"done": True, "message": {"content": None}},
])
def test_planner_rejects_malformed_response_shapes_without_leaking_body(payload):
    secret = "provider-private-response"
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    with pytest.raises(RuntimeError) as error:
        propose("Count words", transport=transport)
    assert str(error.value) == "Local model returned an invalid response shape"
    assert secret not in str(error.value)


@pytest.mark.parametrize("failure", [
    RuntimeError("Local model returned HTTP 500"),
    RuntimeError("Local model request failed or returned invalid data"),
])
def test_plan_endpoint_marks_provider_failures_retryable(monkeypatch, failure):
    user, job = uuid4(), uuid4()
    outcomes = []

    class Store:
        def get_job(self, owner, target):
            return {"goal": "Count words", "state": "RECEIVED"} if (owner, target) == (user, job) else None
        def is_paused(self, owner):
            return False
        def get_plan(self, owner, target):
            return None
        def reserve_plan_request(self, owner, target):
            assert (owner, target) == (user, job)
        def finish_plan_request(self, owner, target, success):
            assert (owner, target) == (user, job)
            outcomes.append(success)

    monkeypatch.setattr("jayai.planner.propose", lambda _goal: (_ for _ in ()).throw(failure))
    with pytest.raises(Exception) as error:
        from jayai.main import plan_job
        plan_job(job, user, Store())
    assert getattr(error.value, "status_code", None) == 503
    assert outcomes == [False]


def test_unrelated_laptop_request_still_needs_model():
    transport = httpx.MockTransport(lambda _request: httpx.Response(500))
    with pytest.raises(RuntimeError, match="Local model returned HTTP 500"):
        propose("Check my laptop email", transport=transport)


def test_laptop_request_is_not_rewritten_to_an_unsupported_action():
    def respond(_request):
        return httpx.Response(200, json={"done": True, "message": {"content":
            json.dumps({"summary": "Review email", "steps": ["Read email"], "action": "none"})}})
    assert propose("Check my laptop email", transport=httpx.MockTransport(respond)).action == "none"


def test_planner_rejects_repeated_steps():
    with pytest.raises(ValueError, match="distinct"):
        ProposedPlan(summary="A plan", steps=["Inspect", "inspect "], action="none")


def test_planner_reports_local_failure_without_untrusted_body():
    transport = httpx.MockTransport(lambda _request: httpx.Response(500, text="private data"))
    with pytest.raises(RuntimeError, match=r"Local model returned HTTP 500") as error:
        propose("Check this PC", transport=transport)
    assert "private data" not in str(error.value)


def test_planner_sanitizes_timeout():
    def timeout(_request):
        raise httpx.ReadTimeout("provider-private-timeout")

    with pytest.raises(RuntimeError, match="Local model request failed or returned invalid data") as error:
        propose("Check this PC", transport=httpx.MockTransport(timeout))
    assert "provider-private-timeout" not in str(error.value)


def test_planner_guides_when_local_model_missing():
    transport = httpx.MockTransport(lambda _request: httpx.Response(404))
    with pytest.raises(RuntimeError, match=r"ollama pull qwen2.5:3b"):
        propose("Check this PC", transport=transport)


@pytest.mark.parametrize("model", ["qwen2.5:1.5b", "qwen2.5:0.5b"])
def test_planner_allows_smaller_local_model_but_rejects_cloud(monkeypatch, model):
    monkeypatch.setenv("JAYAI_LOCAL_MODEL", model)
    def respond(request):
        assert json.loads(request.content)["model"] == model
        return httpx.Response(200, json={"done": True, "message": {"content":
            json.dumps({"summary": "Local check", "steps": ["Inspect"], "action": "pc_health"})}})
    assert propose("Check my PC", transport=httpx.MockTransport(respond)).action == "pc_health"
    monkeypatch.setenv("JAYAI_LOCAL_MODEL", "cloud-model")
    with pytest.raises(RuntimeError, match="Unsupported local model"):
        propose("Check my PC", transport=httpx.MockTransport(respond))


def test_plan_reservation_checks_pause_before_network(monkeypatch):
    queries = []

    class Result:
        def __init__(self, value):
            self.value = value
        def fetchone(self):
            return self.value

    class Connection:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def execute(self, sql, _params):
            queries.append(sql)
            if "FROM user_controls" in sql:
                return Result((True, False))
            raise AssertionError("Paused job must not start planning")

    monkeypatch.setattr("jayai.db.psycopg.connect", lambda *_args: Connection())
    with pytest.raises(PermissionError, match="paused"):
        Repository("postgresql://unused").reserve_plan_request(uuid4(), uuid4())
    assert "FOR UPDATE" in queries[0]


def test_plan_reservation_stops_after_daily_limit(monkeypatch):
    queries = []

    class Result:
        def __init__(self, value):
            self.value = value
        def fetchone(self):
            return self.value

    class Connection:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def execute(self, sql, _params):
            queries.append(sql)
            if "FROM user_controls" in sql:
                return Result((False, False))
            if "FROM jobs WHERE" in sql:
                return Result(("WAITING_FOR_APPROVAL", {}, None))
            if "EXTRACT(EPOCH" in sql:
                return Result((False,))
            if "FROM job_plans" in sql or "FROM plan_requests WHERE job_id" in sql:
                return Result(None)
            if "sum(attempts)" in sql:
                return Result((10,))
            raise AssertionError("Daily cap must block the reservation insert")

    monkeypatch.setattr("jayai.db.psycopg.connect", lambda *_args: Connection())
    with pytest.raises(PermissionError, match="Daily planning request limit"):
        Repository("postgresql://unused").reserve_plan_request(uuid4(), uuid4())
    assert not any("INSERT INTO plan_requests" in query for query in queries)


def test_unlimited_user_can_retry_expired_job_but_still_checks_pause(monkeypatch):
    queries = []

    class Result:
        def __init__(self, row):
            self.row = row
        def fetchone(self):
            return self.row

    class Connection:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def execute(self, sql, _params):
            queries.append(sql)
            if "FROM user_controls" in sql:
                return Result((False, True))
            if "FROM jobs WHERE" in sql:
                return Result(("RECEIVED", {}, None))
            if "FROM job_plans" in sql:
                return Result(None)
            if "FROM plan_requests WHERE job_id" in sql:
                return Result((100, "FAILED", None))
            if "INSERT INTO plan_requests" in sql:
                return Result(None)
            raise AssertionError("Unlimited user should bypass planning caps")

    monkeypatch.setattr("jayai.db.psycopg.connect", lambda *_args: Connection())
    Repository("postgresql://unused").reserve_plan_request(uuid4(), uuid4())
    assert any("INSERT INTO plan_requests" in sql for sql in queries)
    assert not any("sum(attempts)" in sql or "EXTRACT(EPOCH" in sql for sql in queries)


def test_unlimited_user_transition_skips_runtime_and_step_caps(monkeypatch):
    statements = []

    class Result:
        def __init__(self, value):
            self.value = value
        def fetchone(self):
            return self.value

    class Connection:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def execute(self, sql, _params):
            statements.append(sql)
            if "FROM user_controls" in sql:
                return Result({"paused": False, "unlimited_limits": True})
            if "FROM jobs WHERE" in sql:
                return Result({"state": "RECEIVED", "limits": {"max_steps": 1}, "created_at": None})
            if "FROM job_steps" in sql:
                return Result({"n": 999})
            if "EXTRACT(EPOCH" in sql:
                raise AssertionError("Unlimited user should bypass runtime check")
            return Result(None)

    monkeypatch.setattr("jayai.db.psycopg.connect", lambda *_args, **_kwargs: Connection())
    from jayai.contracts import JobState
    assert Repository("postgresql://unused").transition_job(uuid4(), uuid4(), JobState.PLANNING, "test") == JobState.PLANNING
    assert any("INSERT INTO audit_events" in sql for sql in statements)


def test_waiting_approval_uses_job_creation_time_for_runtime_budget(monkeypatch):
    statements = []

    class Result:
        def __init__(self, value):
            self.value = value
        def fetchone(self):
            return self.value

    class Connection:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def execute(self, sql, _params):
            statements.append(sql)
            if "FROM user_controls" in sql:
                return Result((False, False))
            if "FROM jobs WHERE" in sql:
                return Result(("WAITING_FOR_APPROVAL", Limits().model_dump(), None))
            if "EXTRACT(EPOCH" in sql:
                return Result((True,))
            raise AssertionError("Expired approval must stop before other planning writes")

    monkeypatch.setattr("jayai.db.psycopg.connect", lambda *_args: Connection())
    with pytest.raises(ValueError, match="runtime limit"):
        Repository("postgresql://unused").reserve_plan_request(uuid4(), uuid4())
    assert not any("INSERT INTO plan_requests" in sql for sql in statements)


def test_transition_rejects_insufficient_remaining_step_budget(monkeypatch):
    statements = []

    class Result:
        def __init__(self, value):
            self.value = value
        def fetchone(self):
            return self.value

    class Connection:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def execute(self, sql, _params):
            statements.append(sql)
            if "FROM user_controls" in sql:
                return Result({"paused": False, "unlimited_limits": False})
            if "FROM jobs WHERE" in sql:
                return Result({"state": "WAITING_FOR_APPROVAL",
                                "limits": Limits(max_steps=1).model_dump(), "created_at": None})
            if "FROM job_steps" in sql:
                return Result({"n": 1})
            raise AssertionError("Step budget must stop before transition writes")

    monkeypatch.setattr("jayai.db.psycopg.connect", lambda *_args, **_kwargs: Connection())
    with pytest.raises(RuntimeError, match="step limit"):
        Repository("postgresql://unused").transition_job(
            uuid4(), uuid4(), JobState.EXECUTING, "approve reviewed plan")
    assert not any("UPDATE jobs" in sql for sql in statements)


def test_plan_api_is_user_scoped_and_review_only(monkeypatch):
    user, other = uuid4(), uuid4()
    job = uuid4()
    key = "k" * 32
    monkeypatch.setenv("JAYAI_ENV", "development")
    monkeypatch.setenv("JAYAI_DEV_API_KEY", key)
    monkeypatch.setenv("JAYAI_DEV_USER_ID", str(user))

    class Store:
        saved = None
        state = "WAITING_FOR_APPROVAL"
        def reserve_plan_request(self, owner, target):
            assert owner == user and target == job
        def finish_plan_request(self, owner, target, success):
            assert owner == user and target == job and success
        def get_job(self, owner, target):
            return {"goal": "Count words", "state": self.state} if owner == user and target == job else None
        def is_paused(self, owner):
            return False
        def get_plan(self, owner, target):
            return self.saved if owner == user and target == job else None
        def save_plan(self, owner, target, plan):
            assert owner == user and target == job
            self.saved = plan

    store = Store()
    monkeypatch.setattr("jayai.planner.propose", lambda goal: ProposedPlan(summary="Count", steps=["Read text"], action="none"))
    app.dependency_overrides[repository] = lambda: store
    try:
        with TestClient(app) as client:
            headers = {"X-JayAI-Key": key}
            assert client.post(f"/jobs/{job}/plan").status_code == 401
            assert client.post(f"/jobs/{job}/plan", headers=headers).json()["summary"] == "Count"
            assert client.post(f"/jobs/{job}/plan", headers=headers).json()["summary"] == "Count"
            assert client.get(f"/jobs/{job}/plan", headers=headers).json()["steps"] == ["Read text"]
            monkeypatch.setenv("JAYAI_DEV_USER_ID", str(other))
            assert client.get(f"/jobs/{job}/plan", headers=headers).status_code == 404
    finally:
        app.dependency_overrides.clear()
