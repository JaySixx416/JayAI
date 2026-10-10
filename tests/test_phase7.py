import base64
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from jayai import google
from jayai.main import app


def test_oauth_requires_configuration(monkeypatch):
    monkeypatch.delenv("JAYAI_TOKEN_KEY", raising=False)
    with pytest.raises(RuntimeError):
        google.settings()


def test_oauth_rejects_remote_redirect(monkeypatch):
    monkeypatch.setenv("JAYAI_GOOGLE_CLIENT_ID", "example")
    monkeypatch.setenv("JAYAI_GOOGLE_CLIENT_SECRET", "example")
    monkeypatch.setenv("JAYAI_GOOGLE_REDIRECT_URI", "https://example.com/callback")
    monkeypatch.setenv("JAYAI_TOKEN_KEY", Fernet.generate_key().decode())
    with pytest.raises(RuntimeError):
        google.settings()


def test_connector_endpoints_require_auth(monkeypatch):
    monkeypatch.setenv("JAYAI_ENV", "development")
    monkeypatch.setenv("JAYAI_DEV_USER_ID", str(uuid4()))
    monkeypatch.setenv("JAYAI_DEV_API_KEY", "a" * 32)
    client = TestClient(app)
    for method, url in [("post", "/connections/google/start"), ("post", "/connections/google/complete"),
                        ("get", "/connections/google/mail"), ("get", "/connections/google/calendar"),
                        ("delete", "/connections/google")]:
        response = client.request(method.upper(), url, json={"state": "x", "code": "x"} if method == "post" else None)
        assert response.status_code == 401


def test_scopes_read_only():
    assert all("readonly" in scope for scope in google.SCOPES)
