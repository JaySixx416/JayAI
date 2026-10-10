from datetime import datetime, timedelta, timezone

import pytest

from jayai.plans import verify_read_only_result


def report(action="pc_health", **overrides):
    value = {
        "scope": "Linux environment",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "free_percent": 50,
        "findings": [],
        "updates": None,
    }
    if action == "pc_processes":
        value = {
            "scope": "Linux environment",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "processes": [{"name": "worker", "id": 1}],
            "findings": [],
        }
    value.update(overrides)
    return value


def test_evidence_requires_parseable_fresh_timezone_timestamp():
    assert not verify_read_only_result("pc_health", report(checked_at="invalid"))
    old = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
    assert not verify_read_only_result("pc_health", report(checked_at=old))
    assert verify_read_only_result("pc_health", report())


def test_linux_evidence_rejects_malformed_update_status():
    assert not verify_read_only_result("pc_health", report(updates={"start_type": "Manual", "reboot_required": "false"}))
