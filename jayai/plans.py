"""Canonical helpers for immutable plan review and exact-digest approvals."""

import hashlib
import json


def plan_digest(plan: dict) -> str:
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def expected_evidence(action: str) -> list[str]:
    """Return server-defined evidence for the small read-only action allowlist."""
    evidence = {
        "pc_health": ["Environment scope", "Free storage percentage", "Read-only findings", "Update status when supported"],
        "pc_processes": ["Environment scope", "At most 30 process names and IDs", "Collection timestamp"],
        "windows_health": ["Windows laptop scope", "Free storage percentage", "Update/reboot status", "Startup names and recent error identifiers", "Available package update text"],
    }
    return evidence.get(action, [])


def verify_read_only_result(action: str, report: object) -> bool:
    """Validate the evidence needed before a read-only job may be completed."""
    if not isinstance(report, dict):
        return False
    checked_at = report.get("checked_at")
    if not isinstance(checked_at, str) or not checked_at or len(checked_at) > 80:
        return False
    findings = report.get("findings", [])
    if not isinstance(findings, list) or len(findings) > 50 or any(
        not isinstance(item, dict) or not isinstance(item.get("code"), str)
        or len(item["code"]) > 64 or not isinstance(item.get("message"), str)
        or len(item["message"]) > 500 for item in findings
    ):
        return False
    if action in ("pc_health", "windows_health"):
        scopes = ("Windows PC", "Linux environment") if action == "pc_health" else ("Windows laptop",)
        if report.get("scope") not in scopes or type(report.get("free_percent")) not in (int, float) or \
                not 0 <= report["free_percent"] <= 100:
            return False
        if action == "windows_health":
            return all(isinstance(report.get(key), list) and len(report[key]) <= 30
                       for key in ("startup", "recent_errors", "package_updates")) and \
                (report.get("updates") is None or isinstance(report.get("updates"), dict)) and \
                report.get("applied_changes") == []
        return True
    if action == "pc_processes":
        items = report.get("processes")
        return report.get("scope") in ("Windows PC", "Linux environment") and isinstance(items, list) and \
            len(items) <= 30 and all(isinstance(item, dict) and isinstance(item.get("name"), str)
                                     and len(item["name"]) <= 120 and type(item.get("id")) is int
                                     and item["id"] >= 0 for item in items)
    return False
