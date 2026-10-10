import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

def test_monitor_history_is_bounded_and_contains_only_safe_summaries(tmp_path, monkeypatch):
    from jayai.maintenance import monitor_history, observe
    path = tmp_path / "state.json"
    monkeypatch.setattr("jayai.maintenance.state_path", lambda: path)
    for index in range(60):
        observe(path, {"checked_at": f"2026-01-01T00:{index:02}:00Z", "scope": "Linux environment",
                       "free_percent": 80, "findings": [], "updates": {"start_type": "Manual",
                       "reboot_required": False}, "private_filename": "must-not-be-recorded"})
    result = monitor_history(50)
    assert result["scope"] == "Linux environment"
    assert len(result["checks"]) == 50
    assert [item["checked_at"] for item in result["checks"]] == [
        f"2026-01-01T00:{index:02}:00Z" for index in range(10, 60)
    ]
    assert result["checks"][-1]["scope"] == "Linux environment"
    assert "private_filename" not in str(result)
    assert "must-not-be-recorded" not in path.read_text(encoding="utf-8")


def test_monitor_history_discards_malformed_entries_before_retaining_recent_history(tmp_path, monkeypatch):
    from jayai.maintenance import monitor_history, observe
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"history": [
        {"checked_at": "seed"},
        {"checked_at": 42},
        "malformed",
    ]}), encoding="utf-8")
    monkeypatch.setattr("jayai.maintenance.state_path", lambda: path)
    for index in range(60):
        observe(path, {"checked_at": f"check-{index}", "scope": "Linux environment",
                       "free_percent": 80, "findings": []})

    result = monitor_history(50)
    assert [item["checked_at"] for item in result["checks"]] == [
        f"check-{index}" for index in range(10, 60)
    ]
