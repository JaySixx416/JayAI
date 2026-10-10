import json

import httpx
import pytest
from fastapi.testclient import TestClient

from jayai.main import app
from jayai.music import SongRequest, api_status, prepare_song


def response_package():
    return {
        "title": "Ride When It's Ugly", "alternate_titles": ["Show Me Forever", "When the Room Goes Quiet"],
        "song_truth": "A test of love through difficult circumstances.",
        "strongest_material": ["A strong central question."], "audit_findings": ["Replace vague detail with a specific image."],
        "line_audit": [{"section": "Verse 1", "original_line": "Weak line", "assessment": "Vague image.", "replacement": "Sharper line"}],
        "final_lyrics": "[Verse 1]\nA test lyric.", "what_changed": ["Tightened the verse."],
        "best_lines": [{"line": f"Strong line {n}", "reason": "Clear image and natural cadence."} for n in range(5)],
        "performance_map": ["Pull back in the verse; open the final hook."],
        "suno_style": "Gritty rap/R&B crossover, intimate male lead and restrained female harmonies.",
        "suno_exclude": "Overly bright pop production",
        "revision_level_used": 3, "original_lyrics_retained_percent": 70,
        "biggest_upgrade": "The hook now carries the emotional question.",
    }


def test_song_request_requires_concept_or_lyrics():
    with pytest.raises(ValueError, match="Add a song concept"):
        prepare_song(SongRequest())


def test_song_request_bounds_revision_level():
    with pytest.raises(ValueError):
        SongRequest(revision_level=6)


def test_prepare_song_uses_key_and_returns_validated_package(monkeypatch):
    monkeypatch.setenv("JAYAI_MUSIC_API_KEY", "secret-test-key")
    monkeypatch.setenv("JAYAI_MUSIC_MODEL", "test-model")
    captured = {}

    def handler(request):
        captured["auth"] = request.headers["authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(response_package())}}]})

    package = prepare_song(SongRequest(brief="A new song concept", revision_level=3), httpx.MockTransport(handler))
    assert package.title == "Ride When It's Ugly"
    assert len(package.suno_style) <= 750
    assert captured["auth"] == "Bearer secret-test-key"
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["response_format"]["type"] == "json_schema"
    assert "3" in captured["body"]["messages"][1]["content"]


def test_prepare_song_rejects_too_long_suno_style(monkeypatch):
    monkeypatch.setenv("JAYAI_MUSIC_API_KEY", "secret-test-key")
    result = response_package()
    result["suno_style"] = "x" * 751

    def handler(_request):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(result)}}]})

    with pytest.raises(RuntimeError, match="750-character"):
        prepare_song(SongRequest(lyrics="draft"), httpx.MockTransport(handler))


def test_provider_error_does_not_echo_provider_body(monkeypatch):
    monkeypatch.setenv("JAYAI_MUSIC_API_KEY", "secret-test-key")

    def handler(_request):
        return httpx.Response(401, text="do not leak secret details")

    with pytest.raises(RuntimeError) as error:
        prepare_song(SongRequest(lyrics="draft"), httpx.MockTransport(handler))
    assert "do not leak" not in str(error.value)


def test_music_endpoints_require_dashboard_auth_and_serve_chromebook_page(monkeypatch):
    monkeypatch.setenv("JAYAI_ENV", "development")
    monkeypatch.setenv("JAYAI_DEV_API_KEY", "k" * 32)
    monkeypatch.setenv("JAYAI_DEV_USER_ID", "7c8a14e5-093b-445f-91c0-9d57e8c12345")
    monkeypatch.delenv("JAYAI_MUSIC_API_KEY", raising=False)
    with TestClient(app) as client:
        assert "Song Studio" in client.get("/music").text
        assert client.get("/api/music/status").status_code == 401
        status = client.get("/api/music/status", headers={"X-JayAI-Key": "k" * 32})
        assert status.status_code == 200 and status.json()["configured"] is False
        no_input = client.post("/api/music/prepare", headers={"X-JayAI-Key": "k" * 32}, json={})
        assert no_input.status_code == 422
        assert api_status()["configured"] is False
