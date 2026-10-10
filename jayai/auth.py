"""Cloud authentication primitives; the development key remains separate."""

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

SESSION_TTL = timedelta(hours=12)
MAX_ID_TOKEN_AGE = timedelta(minutes=10)


def new_session_token() -> str:
    """Create an opaque bearer value; callers must store only its hash."""
    return secrets.token_urlsafe(32)


def session_token_hash(token: str) -> str:
    if not isinstance(token, str) or not token:
        raise ValueError("Session token is required")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("Session time must be timezone-aware")
    return current.astimezone(timezone.utc) + SESSION_TTL


def authorization_url(endpoint: str, client_id: str, redirect_uri: str, state: str,
                      nonce: str, code_challenge: str) -> str:
    if not endpoint.startswith("https://") or not all(
            isinstance(value, str) and value for value in
            (client_id, redirect_uri, state, nonce, code_challenge)):
        raise ValueError("Invalid OIDC authorization configuration")
    return endpoint + "?" + urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri,
        "response_type": "code", "scope": "openid profile email",
        "state": state, "nonce": nonce, "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })


def exchange_code(token_endpoint: str, client_id: str, client_secret: str,
                 redirect_uri: str, code: str, verifier: str,
                 http: httpx.Client | None = None) -> dict:
    if not token_endpoint.startswith("https://") or not code or not verifier:
        raise ValueError("Invalid OIDC token exchange request")
    payload = {"grant_type": "authorization_code", "client_id": client_id,
               "client_secret": client_secret, "redirect_uri": redirect_uri,
               "code": code, "code_verifier": verifier}

    def send(client: httpx.Client) -> dict:
        try:
            response = client.post(token_endpoint, data=payload)
            response.raise_for_status()
            value = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError("OIDC token exchange failed") from exc
        if not isinstance(value, dict) or not isinstance(value.get("id_token"), str):
            raise RuntimeError("OIDC token response is invalid")
        return value

    if http is not None:
        return send(http)
    with httpx.Client(timeout=10, trust_env=False) as client:
        return send(client)


def _decode_part(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def validate_id_token(token: str, jwks: dict, issuer: str, client_id: str,
                      nonce: str, now: datetime | None = None) -> dict:
    """Validate a compact RS256 OIDC ID token without logging its contents."""
    try:
        encoded_header, encoded_claims, encoded_signature = token.split(".")
        header = json.loads(_decode_part(encoded_header))
        claims = json.loads(_decode_part(encoded_claims))
        signature = _decode_part(encoded_signature)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("OIDC ID token is malformed") from exc
    if not isinstance(header, dict) or header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise ValueError("OIDC ID token algorithm is not allowed")
    if not isinstance(claims, dict) or claims.get("iss") != issuer or claims.get("nonce") != nonce:
        raise ValueError("OIDC ID token claims are invalid")
    audience = claims.get("aud")
    if audience != client_id and not (isinstance(audience, list) and client_id in audience):
        raise ValueError("OIDC ID token audience is invalid")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not 1 <= len(subject) <= 512:
        raise ValueError("OIDC subject is invalid")
    current = now or datetime.now(timezone.utc)
    try:
        expiry = float(claims["exp"])
        issued = float(claims["iat"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("OIDC ID token timestamps are invalid") from exc
    current_seconds = current.timestamp()
    if expiry <= current_seconds or issued > current_seconds + 60 or \
            current_seconds - issued > MAX_ID_TOKEN_AGE.total_seconds():
        raise ValueError("OIDC ID token is expired or stale")
    keys = jwks.get("keys") if isinstance(jwks, dict) else None
    key = next((item for item in keys or [] if isinstance(item, dict) and
                item.get("kid") == header["kid"] and item.get("kty") == "RSA" and
                item.get("n") and item.get("e")), None)
    if key is None:
        raise ValueError("OIDC signing key is unavailable")
    try:
        public_key = rsa.RSAPublicNumbers(
            int.from_bytes(_decode_part(key["e"]), "big"),
            int.from_bytes(_decode_part(key["n"]), "big"),
        ).public_key()
        public_key.verify(signature, f"{encoded_header}.{encoded_claims}".encode("ascii"),
                           padding.PKCS1v15(), hashes.SHA256())
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise ValueError("OIDC ID token signature is invalid") from exc
    return {"issuer": issuer, "subject": subject}
