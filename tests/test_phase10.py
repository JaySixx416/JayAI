import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from jayai.maintenance import check, windows_update_status


def test_windows_update_probe_uses_fixed_read_only_commands():
    with patch("jayai.maintenance.subprocess.run", return_value=SimpleNamespace(
            stdout=json.dumps({"start_type": "Manual", "reboot_required": True}))) as run:
        assert windows_update_status() == {"start_type": "Manual", "reboot_required": True}
    argv = run.call_args.args[0]
    assert argv[:3] == ["powershell.exe", "-NoProfile", "-NonInteractive"]
    assert "Get-Service" in argv[-1] and "Test-Path" in argv[-1]
    assert "Set-Service" not in argv[-1] and "Restart-Computer" not in argv[-1]


def test_windows_update_findings_and_probe_failure(tmp_path):
    with patch("jayai.maintenance.os.name", "nt"), patch(
            "jayai.maintenance.shutil.disk_usage", return_value=SimpleNamespace(total=100, free=90)), patch(
            "jayai.maintenance.windows_update_status", return_value={"start_type": "Disabled", "reboot_required": True}):
        report = check(tmp_path)
    assert {item["code"] for item in report["findings"]} == {"updates_disabled", "update_reboot"}
    with patch("jayai.maintenance.os.name", "nt"), patch(
            "jayai.maintenance.shutil.disk_usage", return_value=SimpleNamespace(total=100, free=90)), patch(
            "jayai.maintenance.windows_update_status", side_effect=TimeoutError):
        report = check(tmp_path)
    assert report["update_error"] == "TimeoutError"
    assert report["findings"] == []


def test_monitor_history_is_bounded_and_contains_only_safe_summaries(tmp_path, monkeypatch):
    from jayai.maintenance import monitor_history, observe
    path = tmp_path / "state.json"
    monkeypatch.setattr("jayai.maintenance.state_path", lambda: path)
    for index in range(60):
        observe(path, {"checked_at": f"2026-01-01T00:{index:02}:00Z", "scope": "Windows PC",
                       "free_percent": 80, "findings": [], "updates": {"start_type": "Manual",
                       "reboot_required": False}, "private_filename": "must-not-be-recorded"})
    result = monitor_history(50)
    expected_scope = "Windows PC" if os.name == "nt" else "Linux environment"
    assert result["scope"] == expected_scope
    assert len(result["checks"]) == 50
    assert result["checks"][-1]["scope"] == "Windows PC"
    assert "private_filename" not in str(result)
    assert "must-not-be-recorded" not in path.read_text(encoding="utf-8")
