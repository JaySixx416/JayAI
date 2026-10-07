"""Windows bridge admits only authenticated, bounded diagnostic reports."""

import httpx
import os
import pytest
import threading
from http.server import ThreadingHTTPServer
from uuid import uuid4
from fastapi.testclient import TestClient

from jayai.windows_bridge import diagnostics
from jayai.windows_companion import collect, Handler
from jayai.main import app, repository, plan_digest


def test_bridge_auth_and_bounded_report(monkeypatch):
    key = "a" * 64
    monkeypatch.setenv("JAYAI_COMPANION_KEY", key)

    def handle(request):
        assert request.url.path == "/v1/diagnostics"
        assert request.headers["authorization"] == "Bearer " + key
        return httpx.Response(200, json={"scope": "Windows laptop", "free_percent": 47.5,
            "startup": [], "recent_errors": [], "package_updates": [], "findings": [],
            "applied_changes": []})

    assert diagnostics(httpx.MockTransport(handle))["free_percent"] == 47.5


def test_bridge_rejects_wrong_key_and_invalid_reports(monkeypatch):
    monkeypatch.setenv("JAYAI_COMPANION_KEY", "b" * 64)
    with pytest.raises(RuntimeError, match="does not match"):
        diagnostics(httpx.MockTransport(lambda _: httpx.Response(401)))
    with pytest.raises(ValueError, match="invalid"):
        diagnostics(httpx.MockTransport(lambda _: httpx.Response(200, json={"scope": "Linux environment"})))
    with pytest.raises(ValueError, match="invalid"):
        diagnostics(httpx.MockTransport(lambda _: httpx.Response(200, json={"scope": "Windows laptop",
            "free_percent": 44, "startup": [], "recent_errors": [], "package_updates": [],
            "findings": [], "applied_changes": ["changed"]})))


@pytest.mark.skipif(os.name == "nt", reason="Windows diagnostics are available on Windows")
def test_companion_is_windows_only():
    with pytest.raises(RuntimeError, match="only on Windows"):
        collect()
    assert Handler.do_POST is not None


def test_companion_rejects_unpaired_and_write_requests(monkeypatch):
    monkeypatch.setenv("JAYAI_COMPANION_KEY", "c" * 64)
    monkeypatch.setattr("jayai.windows_companion.collect", lambda: {"scope": "Windows laptop"})
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(timeout=3, trust_env=False) as client:
            url = f"http://127.0.0.1:{server.server_port}/v1/diagnostics"
            assert client.get(url).status_code == 401
            assert client.post(url, headers={"Authorization": "Bearer " + "c" * 64}).status_code == 405
            assert client.get(url, headers={"Authorization": "Bearer " + "c" * 64}).json() == {"scope": "Windows laptop"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_windows_inventory_is_read_only_and_bounded(monkeypatch):
    from types import SimpleNamespace
    import jayai.windows_companion as companion

    monkeypatch.setattr(companion, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(companion.shutil, "disk_usage", lambda _: SimpleNamespace(free=40, total=100))
    monkeypatch.setattr(companion, "windows_update_status", lambda: {"start_type": "Manual", "reboot_required": True})
    samples = iter([[{"Name": "Updater", "Location": "HKCU"}],
                    [{"Id": 42, "ProviderName": "System", "TimeCreated": "2026-09-28"}]])
    monkeypatch.setattr(companion, "_powershell", lambda _: next(samples))
    recorded = []

    def run(args, **kwargs):
        recorded.append(args)
        assert kwargs["timeout"] == 12
        return SimpleNamespace(returncode=0, stdout="Available updates\nApp.Name       App.Id       1.0    1.1\n")

    monkeypatch.setattr(companion.subprocess, "run", run)
    report = collect()
    assert report["scope"] == "Windows laptop" and report["free_percent"] == 40
    assert report["startup"] == [{"name": "Updater", "location": "HKCU"}]
    assert report["recent_errors"][0]["id"] == 42
    assert report["updates"]["reboot_required"] is True
    assert report["applied_changes"] == report["proposed_changes"] == []
    assert recorded == [["winget.exe", "upgrade", "--accept-source-agreements", "--disable-interactivity"]]


def test_windows_report_requires_exact_approval_and_is_saved(monkeypatch):
    user, job = uuid4(), uuid4()
    key = "d" * 64
    monkeypatch.setenv("JAYAI_ENV", "development")
    monkeypatch.setenv("JAYAI_DEV_USER_ID", str(user))
    monkeypatch.setenv("JAYAI_DEV_API_KEY", key)
    report = {"scope": "Windows laptop", "checked_at": "2026-09-27T00:00:00+00:00",
              "free_percent": 40, "findings": [],
              "startup": [], "recent_errors": [], "package_updates": [], "applied_changes": []}
    calls = []
    monkeypatch.setattr("jayai.windows_bridge.diagnostics", lambda: calls.append(1) or report)
    plan = {"summary": "Inspect Windows laptop", "steps": ["Read laptop diagnostics"], "action": "windows_health"}

    class Store:
        state = "WAITING_FOR_APPROVAL"
        result = None

        def get_job(self, owner, requested):
            assert owner == user and requested == job
            return {"state": self.state}

        def get_plan(self, owner, requested):
            return plan

        def is_paused(self, owner):
            return False

        def record_approval_decision(self, owner, requested, digest, decision, reason=""):
            return {"plan_sha256": digest, "decision": decision, "reason": reason}

        def transition_job(self, owner, requested, target, reason):
            self.state = target.value

        def save_result(self, owner, requested, result):
            assert self.state == "VERIFYING"
            self.result = result

    store = Store()
    app.dependency_overrides[repository] = lambda: store
    try:
        with TestClient(app) as client:
            bad = client.post(f"/jobs/{job}/run", json={"plan_sha256": "0" * 64},
                              headers={"X-JayAI-Key": key})
            assert bad.status_code == 409 and calls == []
            good = client.post(f"/jobs/{job}/run", json={"plan_sha256": plan_digest(plan)},
                               headers={"X-JayAI-Key": key})
            assert good.status_code == 200
            assert good.json() == store.result == {"kind": "windows_health", "report": report}
            assert store.state == "COMPLETED" and calls == [1]
    finally:
        app.dependency_overrides.clear()
