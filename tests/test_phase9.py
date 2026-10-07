import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from jayai.maintenance import check, observe, state_path


def test_check_counts_old_downloads_without_following_links(tmp_path, monkeypatch):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    old = downloads / "old.txt"
    old.write_bytes(b"test")
    current = datetime.now(timezone.utc)
    stamp = (current - timedelta(days=31)).timestamp()
    os.utime(old, (stamp, stamp))
    (downloads / "recent.txt").write_bytes(b"new")
    monkeypatch.setattr("jayai.maintenance.shutil.disk_usage", lambda drive: SimpleNamespace(total=100, free=10))
    report = check(tmp_path, now=current)
    assert report["old_downloads_count"] == 1
    assert report["old_downloads_bytes"] == 4
    assert {finding["code"] for finding in report["findings"]} == {"low_disk_space", "old_downloads"}


def test_repeated_findings_are_recorded_without_file_names(tmp_path):
    path = tmp_path / "JayAI" / "maintenance.json"
    report = {"checked_at": "today", "findings": [{"code": "old_downloads"}]}
    assert observe(path, report)["repeat_counts"] == {"old_downloads": 1}
    assert observe(path, report)["repeat_counts"] == {"old_downloads": 2}
    assert observe(path, report)["suggested_routines"] == ["Consider a recurring Downloads review."]
    assert json.loads(path.read_text())["counts"] == {"old_downloads": 3}
    report["findings"] = []
    assert observe(path, report)["repeat_counts"] == {}


def test_linux_check_reports_container_scope_and_uses_xdg_state(tmp_path, monkeypatch):
    if os.name != "posix":
        return
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert state_path() == tmp_path / "state" / "JayAI" / "maintenance.json"
    monkeypatch.setattr("jayai.maintenance.shutil.disk_usage", lambda path: SimpleNamespace(total=100, free=50))
    report = check(tmp_path)
    assert report["scope"] == "Linux environment"
    assert report["updates"] is None
