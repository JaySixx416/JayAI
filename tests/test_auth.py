import base64
import hashlib
import json
from http.cookies import SimpleCookie
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from uuid import uuid4
from starlette.requests import Request
from fastapi import HTTPException

from jayai import main
from jayai.auth import (authorization_url, exchange_code, new_session_token,
                        session_expiry, session_token_hash, validate_id_token)


def compact(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def signed_token(private_key, claims):
    header = compact(json.dumps({"alg": "RS256", "kid": "key-1"}, separators=(",", ":")).encode())
    payload = compact(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode()
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{compact(signature)}"


def jwk(private_key):
    public = private_key.public_key().public_numbers()
    return {"keys": [{"kty": "RSA", "kid": "key-1", "n": compact(public.n.to_bytes((public.n.bit_length() + 7) // 8, "big")),
                       "e": compact(public.e.to_bytes((public.e.bit_length() + 7) // 8, "big"))}]}


def test_session_tokens_are_opaque_hashed_and_expire_in_utc():
    token = new_session_token()
    assert len(token) >= 40
    assert session_token_hash(token) == hashlib.sha256(token.encode()).hexdigest()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert session_expiry(now) == now + timedelta(hours=12)
    with pytest.raises(ValueError):
        session_expiry(datetime(2026, 1, 1))


def test_oidc_authorization_url_uses_nonce_and_pkce():
    url = authorization_url("https://issuer.example/authorize", "client", "https://app.example/callback",
                            "state", "nonce", "challenge")
    assert "response_type=code" in url and "nonce=nonce" in url
    assert "code_challenge=challenge" in url and "scope=openid+profile+email" in url


def test_oidc_id_token_requires_signature_claims_and_freshness():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    claims = {"iss": "https://issuer.example", "sub": "subject-1", "aud": "client",
              "nonce": "nonce", "iat": now.timestamp(), "exp": (now + timedelta(minutes=5)).timestamp()}
    token = signed_token(private, claims)
    assert validate_id_token(token, jwk(private), "https://issuer.example", "client", "nonce", now)["subject"] == "subject-1"
    altered = token.split(".")
    altered[2] = ("A" if altered[2][0] != "A" else "B") + altered[2][1:]
    with pytest.raises(ValueError, match="signature"):
        validate_id_token(".".join(altered), jwk(private), "https://issuer.example", "client", "nonce", now)
    with pytest.raises(ValueError, match="expired or stale"):
        validate_id_token(signed_token(private, {**claims, "iat": (now - timedelta(minutes=11)).timestamp()}),
                          jwk(private), "https://issuer.example", "client", "nonce", now)


def test_oidc_exchange_sanitizes_provider_errors():
    transport = httpx.MockTransport(lambda _request: httpx.Response(500, text="private provider response"))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(RuntimeError, match="token exchange failed") as error:
            exchange_code("https://issuer.example/token", "client", "secret", "https://app/callback", "code", "verifier", client)
    assert "private provider response" not in str(error.value)


class AuthStore:
    def __init__(self, user_id):
        self.user_id = user_id
        self.sessions = {}

    def find_oidc_identity(self, issuer, subject):
        return self.user_id

    def create_auth_session(self, user_id, token_hash, expires_at):
        self.sessions[token_hash] = user_id

    def revoke_auth_session(self, token_hash):
        return self.sessions.pop(token_hash, None) is not None


def test_oidc_login_callback_creates_session_and_logout_revokes_it(monkeypatch):
    user_id = uuid4()
    store = AuthStore(user_id)
    monkeypatch.setenv("JAYAI_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("JAYAI_OIDC_AUTHORIZATION_ENDPOINT", "https://issuer.example/authorize")
    monkeypatch.setenv("JAYAI_OIDC_TOKEN_ENDPOINT", "https://issuer.example/token")
    monkeypatch.setenv("JAYAI_OIDC_JWKS_URL", "https://issuer.example/jwks")
    monkeypatch.setenv("JAYAI_OIDC_CLIENT_ID", "client")
    monkeypatch.setenv("JAYAI_OIDC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("JAYAI_OIDC_REDIRECT_URI", "https://app.example/auth/oidc/callback")
    monkeypatch.setenv("JAYAI_OIDC_COOKIE_SECURE", "false")
    monkeypatch.setattr(main, "exchange_code", lambda *args: {"id_token": "synthetic"})
    monkeypatch.setattr(main, "fetch_jwks", lambda *args: {"keys": []})
    monkeypatch.setattr(main, "validate_id_token", lambda *args: {
        "issuer": "https://issuer.example", "subject": "subject"
    })
    started = main.oidc_login()
    assert started.status_code == 200
    assert "code_challenge" in started.body.decode()
    cookies = SimpleCookie()
    for value in started.headers.getlist("set-cookie"):
        cookies.load(value)
    state = cookies["jayai_oidc_state"].value
    cookie_header = "; ".join(f"{key}={morsel.value}" for key, morsel in cookies.items())
    request = Request({"type": "http", "headers": [(b"cookie", cookie_header.encode())]})
    callback = main.oidc_callback(request, code="synthetic", state=state, db=store)
    assert callback.status_code == 200
    assert len(store.sessions) == 1
    session_cookies = SimpleCookie()
    for value in callback.headers.getlist("set-cookie"):
        session_cookies.load(value)
    csrf = session_cookies["jayai_csrf"].value
    logout_request = Request({
        "type": "http",
        "headers": [
            (b"cookie", f"jayai_session={session_cookies['jayai_session'].value}; jayai_csrf={csrf}".encode()),
            (b"x-jayai-csrf", csrf.encode()),
        ],
    })
    assert main.logout(logout_request, store).body == b'{"authenticated":false}'
    assert not store.sessions


def test_session_write_requires_matching_csrf_cookie_and_header(monkeypatch):
    user_id = uuid4()
    token = new_session_token()
    csrf = new_session_token()

    class Store:
        def get_auth_session(self, token_hash):
            assert token_hash == session_token_hash(token)
            return {"user_id": user_id}

        def touch_auth_session(self, token_hash):
            return True

    monkeypatch.setenv("JAYAI_ENV", "production")
    monkeypatch.setenv("JAYAI_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setattr(main, "repository", lambda: Store())

    def request(headers):
        return Request({
            "type": "http", "method": "POST",
            "headers": [(key.encode(), value.encode()) for key, value in headers.items()],
        })

    with pytest.raises(HTTPException) as error:
        main.development_user(request({"cookie": f"jayai_session={token}; jayai_csrf={csrf}"}))
    assert error.value.detail == "CSRF validation failed"
    assert main.development_user(request({
        "cookie": f"jayai_session={token}; jayai_csrf={csrf}",
        "x-jayai-csrf": csrf,
    })) == user_id
