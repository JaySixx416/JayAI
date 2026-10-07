"""Loopback-only Windows diagnostics for JayAI. No command endpoint or mutation API."""

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from jayai.maintenance import windows_update_status


def _powershell(script: str) -> object:
    output = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=8, check=True,
    )
    return json.loads(output.stdout)


def collect() -> dict:
    """Return bounded, read-only observations without names of private files."""
    if os.name != "nt":
        raise RuntimeError("Windows companion runs only on Windows")
    disk = shutil.disk_usage(Path.home().anchor)
    free = round(100 * disk.free / disk.total, 1)
    findings = []
    if free < 15:
        findings.append({"code": "low_disk_space", "message": "System drive is under 15% free; review storage before removing files."})
    try:
        updates = windows_update_status()
    except (OSError, ValueError, subprocess.SubprocessError):
        updates = None
        findings.append({"code": "update_status_unavailable", "message": "Windows Update status could not be read."})
    if updates and updates["reboot_required"]:
        findings.append({"code": "restart_pending", "message": "Windows Update reports a pending restart. Save work before restarting."})
    if updates and updates["start_type"] == "Disabled":
        findings.append({"code": "updates_disabled", "message": "Windows Update service is disabled; review its settings."})
    startup = []
    errors = []
    try:
        items = _powershell("$ErrorActionPreference='Stop'; $items=@(Get-CimInstance Win32_StartupCommand | Select-Object -First 30 Name,Location); ConvertTo-Json -InputObject $items -Compress")
        startup = [{"name": str(i["Name"])[:120], "location": str(i["Location"])[:120]}
                   for i in items if isinstance(i, dict) and i.get("Name")]
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        findings.append({"code": "startup_unavailable", "message": "Startup entries could not be read."})
    try:
        items = _powershell("$items=@(Get-WinEvent -FilterHashtable @{LogName='System';Level=2;StartTime=(Get-Date).AddDays(-7)} -MaxEvents 10 -ErrorAction SilentlyContinue | Select-Object Id,ProviderName,TimeCreated); ConvertTo-Json -InputObject $items -Compress")
        errors = [{"id": int(i["Id"]), "source": str(i["ProviderName"])[:120],
                   "time": str(i["TimeCreated"])[:80]} for i in items if isinstance(i, dict) and i.get("Id") is not None]
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        findings.append({"code": "event_log_unavailable", "message": "Recent system errors could not be read."})
    packages = []
    try:
        output = subprocess.run(["winget.exe", "upgrade", "--accept-source-agreements", "--disable-interactivity"],
                                capture_output=True, text=True, timeout=12, check=False)
        # Winget output varies by locale. Keep its lines as evidence; never parse these as executable IDs.
        packages = [re.sub(r"[\x00-\x1f\x7f-\x9f]", "", line)[:220]
                    for line in output.stdout.splitlines() if line.strip()][:30]
        if output.returncode not in (0, 1):
            packages = []
            findings.append({"code": "package_updates_unavailable", "message": "Package update list could not be read."})
    except (OSError, subprocess.SubprocessError):
        findings.append({"code": "package_updates_unavailable", "message": "Package update list could not be read."})
    return {"scope": "Windows laptop", "checked_at": datetime.now(timezone.utc).isoformat(),
            "free_percent": free, "updates": updates, "startup": startup,
            "recent_errors": errors, "package_updates": packages, "findings": findings,
            "proposed_changes": [], "applied_changes": []}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        secret = os.environ["JAYAI_COMPANION_KEY"]
        supplied = self.headers.get("Authorization", "")
        if not compare_digest(supplied, "Bearer " + secret):
            self.send_error(401)
            return
        if self.path != "/v1/diagnostics":
            self.send_error(404)
            return
        try:
            payload = json.dumps(collect()).encode("utf-8")
            if len(payload) > 65536:
                raise ValueError("Diagnostics exceeded response limit")
        except Exception:
            self.send_error(503, "Diagnostics unavailable")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        self.send_error(405)

    def log_message(self, format: str, *args: object) -> None:
        # Do not put credentials, query strings, or diagnostic output in logs.
        pass


def main() -> None:
    if os.name != "nt":
        raise RuntimeError("Windows companion runs only on Windows")
    secret = os.environ.get("JAYAI_COMPANION_KEY", "")
    if len(secret) < 32:
        raise RuntimeError("JAYAI_COMPANION_KEY must be at least 32 characters")
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("JayAI Windows companion listening on 127.0.0.1:8765", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
