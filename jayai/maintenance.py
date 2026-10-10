"""Local Linux health checks; observations never change files or settings."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


def running_processes() -> dict:
    """Inspect at most 30 Linux processes, without changes."""
    if sys.platform.startswith("linux"):
        result = subprocess.run(["ps", "-eo", "pid=,comm="], capture_output=True, text=True,
                                timeout=20, check=True)
        processes = []
        for line in result.stdout.splitlines():
            fields = line.strip().split(maxsplit=1)
            if len(fields) != 2 or not fields[0].isdigit() or not 0 < len(fields[1]) <= 120:
                raise ValueError("Unexpected process inventory entry")
            processes.append({"name": fields[1], "id": int(fields[0])})
        processes = sorted(processes, key=lambda item: (item["name"].casefold(), item["id"]))[:30]
    else:
        raise RuntimeError("Process inventory requires Linux")
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "processes": processes,
            "scope": "Linux environment"}


def state_path() -> Path:
    if sys.platform.startswith("linux"):
        return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "JayAI" / "maintenance.json"
    raise RuntimeError("PC monitoring requires Linux")


def check(home: Path | None = None, now: datetime | None = None) -> dict:
    home = home or Path.home()
    now = now or datetime.now(timezone.utc)
    disk = shutil.disk_usage(home)
    free_percent = round(100 * disk.free / disk.total, 1) if disk.total else 0
    downloads = home / "Downloads"
    old_count = 0
    old_bytes = 0
    if downloads.is_dir():
        for entry in downloads.iterdir():
            try:
                if entry.is_file() and not entry.is_symlink():
                    stat = entry.stat()
                    if stat.st_mtime < (now - timedelta(days=30)).timestamp():
                        old_count += 1
                        old_bytes += stat.st_size
            except OSError:
                continue
    findings = []
    if free_percent < 15:
        findings.append({"code": "low_disk_space", "message": "Linux environment storage has under 15% free space. Review storage before removing anything."})
    if old_count:
        findings.append({"code": "old_downloads", "message": f"{old_count} Downloads files are over 30 days old ({old_bytes} bytes). Review them before deleting."})
    return {"checked_at": now.isoformat(), "scope": "Linux environment",
            "free_percent": free_percent,
            "old_downloads_count": old_count, "old_downloads_bytes": old_bytes,
            "updates": None, "update_error": None, "findings": findings}


@contextmanager
def _exclusive_lock(path: Path):
    """Hold a cross-process advisory lock for one state-file update."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as lock:
        import fcntl
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def observe(path: Path, report: dict) -> dict:
    """Count repeated findings; write a bounded local record without file names."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _exclusive_lock(path.with_name(path.name + ".lock")):
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(previous, dict):
                previous = {}
        except (FileNotFoundError, ValueError, OSError):
            previous = {}
        counts = previous.get("counts", {})
        if not isinstance(counts, dict):
            counts = {}
        active = {item["code"] for item in report["findings"]}
        codes = ("low_disk_space", "old_downloads", "updates_disabled", "update_reboot")
        counts = {code: min((counts.get(code, 0) if type(counts.get(code, 0)) is int else 0) + 1, 1000000)
                  for code in codes if code in active}
        report["repeat_counts"] = counts
        suggestions = {"low_disk_space": "Consider a recurring storage review.",
                       "old_downloads": "Consider a recurring Downloads review.",
                       }
        report["suggested_routines"] = [suggestions[code] for code, count in counts.items() if count >= 3]
        history = previous.get("history", [])
        if not isinstance(history, list):
            history = []
        updates = report.get("updates") if isinstance(report.get("updates"), dict) else {}
        summary = {
            "checked_at": str(report.get("checked_at", ""))[:80],
            "scope": str(report.get("scope", ""))[:40],
            "free_percent": report.get("free_percent") if type(report.get("free_percent")) in (int, float) else None,
            "finding_codes": [item["code"] for item in report.get("findings", [])
                              if isinstance(item, dict) and item.get("code") in codes][:10],
            "update_start_type": updates.get("start_type") if updates.get("start_type") in ("Automatic", "Manual", "Disabled") else None,
            "reboot_required": updates.get("reboot_required") if type(updates.get("reboot_required")) is bool else None,
        }
        history = [item for item in history if isinstance(item, dict) and
                   isinstance(item.get("checked_at"), str)][-49:]
        history.append(summary)
        temporary_fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                                                        dir=path.parent)
        try:
            with os.fdopen(temporary_fd, "w", encoding="utf-8") as temporary:
                temporary.write(json.dumps({"counts": counts, "last_check": report["checked_at"],
                                            "history": history}))
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, path)
        finally:
            Path(temporary_name).unlink(missing_ok=True)
    return report


def monitor_history(limit: int = 20) -> dict:
    """Return bounded observation summaries only; never include file names or contents."""
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    try:
        state = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, RuntimeError):
        return {"scope": "Linux environment", "checks": []}
    raw = state.get("history", []) if isinstance(state, dict) else []
    allowed_codes = {"low_disk_space", "old_downloads", "updates_disabled", "update_reboot"}
    checks = []
    if isinstance(raw, list):
        for item in raw[-limit:]:
            if not isinstance(item, dict) or not isinstance(item.get("checked_at"), str):
                continue
            percent = item.get("free_percent")
            raw_codes = item.get("finding_codes", [])
            if not isinstance(raw_codes, list):
                raw_codes = []
            checks.append({
                "checked_at": item["checked_at"][:80],
                "scope": item.get("scope") if item.get("scope") == "Linux environment" else "Unknown scope",
                "free_percent": percent if type(percent) in (int, float) and 0 <= percent <= 100 else None,
                "finding_codes": [code for code in raw_codes
                                  if isinstance(code, str) and code in allowed_codes][:10],
                "update_start_type": item.get("update_start_type") if item.get("update_start_type") in ("Automatic", "Manual", "Disabled") else None,
                "reboot_required": item.get("reboot_required") if type(item.get("reboot_required")) is bool else None,
            })
    return {"scope": "Linux environment", "checks": checks}


def monitor(interval: int, once: bool = False) -> None:
    if not once and not 60 <= interval <= 86400:
        raise ValueError("interval must be between 60 and 86400 seconds")
    while True:
        print(json.dumps(observe(state_path(), check())), flush=True)
        if once:
            return
        time.sleep(interval)
