import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

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
