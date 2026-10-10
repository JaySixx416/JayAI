"""Canonical helpers for immutable plan review and exact-digest approvals."""

import hashlib
import json
from datetime import datetime, timedelta, timezone


MAX_EVIDENCE_AGE = timedelta(minutes=5)
MAX_FUTURE_SKEW = timedelta(seconds=30)


def plan_digest(plan: dict) -> str:
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def expected_evidence(action: str) -> list[str]:
    """Return server-defined evidence for the small read-only action allowlist."""
    evidence = {
        "pc_health": ["Environment scope", "Free storage percentage", "Read-only findings", "Update status when supported"],
        "pc_processes": ["Environment scope", "At most 30 process names and IDs", "Collection timestamp"],
    }
    return evidence.get(action, [])


def verify_read_only_result(action: str, report: object) -> bool:
    """Validate the evidence needed before a read-only job may be completed."""
    if not isinstance(report, dict):
        return False
    checked_at = report.get("checked_at")
    if not isinstance(checked_at, str) or not checked_at or len(checked_at) > 80:
        return False
    try:
        checked = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if checked.tzinfo is None:
        return False
    age = datetime.now(timezone.utc) - checked.astimezone(timezone.utc)
    if age < -MAX_FUTURE_SKEW or age > MAX_EVIDENCE_AGE:
        return False
    findings = report.get("findings", [])
    if not isinstance(findings, list) or len(findings) > 50 or any(
        not isinstance(item, dict) or not isinstance(item.get("code"), str)
        or not item["code"].strip() or len(item["code"]) > 64 or not isinstance(item.get("message"), str)
        or not item["message"].strip()
        or len(item["message"]) > 500 for item in findings
    ):
        return False
    if action == "pc_health":
        if report.get("scope") != "Linux environment" or type(report.get("free_percent")) not in (int, float) or \
                not 0 <= report["free_percent"] <= 100:
            return False
        updates = report.get("updates")
        if updates is not None and not _valid_update_status(updates):
            return False
        return True
    if action == "pc_processes":
        items = report.get("processes")
        return report.get("scope") == "Linux environment" and isinstance(items, list) and \
            len(items) <= 30 and all(isinstance(item, dict) and isinstance(item.get("name"), str)
                                     and bool(item["name"].strip())
                                     and len(item["name"]) <= 120 and type(item.get("id")) is int
                                     and item["id"] >= 0 for item in items)
    return False


def _valid_update_status(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return value.get("start_type") in ("Automatic", "Manual", "Disabled") and \
        type(value.get("reboot_required")) is bool and \
        (value.get("update_error") is None or
         isinstance(value.get("update_error"), str) and len(value["update_error"]) <= 64)
