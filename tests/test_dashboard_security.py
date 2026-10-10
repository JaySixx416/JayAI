from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_does_not_persist_master_key_in_browser_storage():
    source = (ROOT / "jayai" / "dashboard.html").read_text(encoding="utf-8")
    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "not saved in browser storage" in source


def test_dashboard_sanitizes_non_json_api_errors():
    source = (ROOT / "jayai" / "dashboard.html").read_text(encoding="utf-8")
    assert "await response.text()" in source
    assert "JSON.parse(raw)" in source


def test_launcher_disables_access_logging_and_hardens_key_replacement():
    source = (ROOT / "scripts" / "start-jayai.sh").read_text(encoding="utf-8")
    assert "--host 127.0.0.1" in source
    assert "--no-access-log" in source
    assert '[[ -L "$key_file" ]]' in source
    assert 'mktemp "$key_dir/.dashboard-key.XXXXXX"' in source
    assert 'mv -f -- "$key_tmp" "$key_file"' in source
