import json
from types import SimpleNamespace

import pytest

from jayai import maintenance


def test_windows_process_inventory_has_fixed_command_and_bounded_output(monkeypatch):
    monkeypatch.setattr(maintenance, "os", SimpleNamespace(name="nt"))

    def run(args, **kwargs):
        assert args[:3] == ["powershell.exe", "-NoProfile", "-NonInteractive"]
        assert "Get-Process" in args[4]
        assert "Stop-Process" not in args[4]
        assert kwargs["timeout"] == 20
        return SimpleNamespace(stdout=json.dumps([{"ProcessName": "Explorer", "Id": 42, "CPU": 1.2}]))

    monkeypatch.setattr(maintenance.subprocess, "run", run)
    assert maintenance.running_processes()["processes"] == [{"name": "Explorer", "id": 42}]


def test_process_inventory_rejects_unexpected_output(monkeypatch):
    monkeypatch.setattr(maintenance, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(maintenance.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(
        stdout=json.dumps([{"ProcessName": "Explorer", "Id": True}])))
    with pytest.raises(ValueError, match="Unexpected process inventory entry"):
        maintenance.running_processes()


def test_linux_process_inventory_uses_container_processes_only(monkeypatch):
    monkeypatch.setattr(maintenance, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(maintenance, "sys", SimpleNamespace(platform="linux"))

    def run(args, **kwargs):
        assert args == ["ps", "-eo", "pid=,comm="]
        assert kwargs["timeout"] == 20
        return SimpleNamespace(stdout=" 42 Explorer\n 1 init\n")

    monkeypatch.setattr(maintenance.subprocess, "run", run)
    report = maintenance.running_processes()
    assert report["scope"] == "Linux environment"
    assert report["processes"] == [{"name": "Explorer", "id": 42}, {"name": "init", "id": 1}]
