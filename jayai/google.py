"""Google authorization-code connector. Credentials are encrypted before storage."""

import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit
from uuid import UUID

import httpx
import psycopg
from cryptography.fernet import Fernet

from jayai.db import Repository

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
)


def settings() -> tuple[str, str, str, Fernet]:
    client_id = os.environ.get("JAYAI_GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("JAYAI_GOOGLE_CLIENT_SECRET", "")
    redirect = os.environ.get("JAYAI_GOOGLE_REDIRECT_URI", "")
    key = os.environ.get("JAYAI_TOKEN_KEY", "")
    try:
        parsed = urlsplit(redirect)
        valid_redirect = (parsed.scheme == "http" and parsed.hostname == "127.0.0.1"
                          and parsed.port is not None and 1 <= parsed.port <= 65535
                          and parsed.username is None and parsed.password is None
                          and not parsed.fragment)
    except ValueError:
        valid_redirect = False
    if not client_id or not client_secret or not valid_redirect or not key:
        raise RuntimeError("Google OAuth client, localhost redirect, and token encryption key required")
    return client_id, client_secret, redirect, Fernet(key.encode("ascii"))


def start(db: Repository, user_id: UUID) -> str:
    client_id, _, redirect, cipher = settings()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    with psycopg.connect(db.url) as conn:
        conn.execute("DELETE FROM oauth_attempts WHERE created_at < now() - interval '10 minutes'")
        conn.execute("INSERT INTO oauth_attempts (state_hash, user_id, verifier_ciphertext, scopes) VALUES (%s,%s,%s,%s)",
                     (hashlib.sha256(state.encode()).hexdigest(), user_id, cipher.encrypt(verifier.encode()), " ".join(SCOPES)))
    params = dict(client_id=client_id, redirect_uri=redirect, response_type="code", scope=" ".join(SCOPES),
                  access_type="offline", prompt="consent", state=state, code_challenge=challenge,
                  code_challenge_method="S256")
    return AUTH_URL + "?" + urlencode(params)


def complete(db: Repository, user_id: UUID, state: str, code: str, http: httpx.Client | None = None) -> None:
    client_id, client_secret, redirect, cipher = settings()
    if not state or not code:
        raise ValueError("Missing OAuth state or code")
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    # Consume state before the network call; failure requires a fresh authorization attempt.
    with psycopg.connect(db.url) as conn:
        row = conn.execute("DELETE FROM oauth_attempts WHERE state_hash = %s AND user_id = %s "
                           "AND created_at > now() - interval '10 minutes' RETURNING verifier_ciphertext, scopes",
                           (state_hash, user_id)).fetchone()
    if row is None:
        raise ValueError("Invalid or expired OAuth state")
    verifier = cipher.decrypt(bytes(row[0])).decode()
    payload = dict(client_id=client_id, client_secret=client_secret, code=code, code_verifier=verifier,
                   redirect_uri=redirect, grant_type="authorization_code")
    if http is None:
        with httpx.Client(timeout=10) as client:
            response = client.post(TOKEN_URL, data=payload)
    else:
        response = http.post(TOKEN_URL, data=payload)
    response.raise_for_status()
    tokens = response.json()
    granted = set(tokens.get("scope", "").split())
    if granted != set(SCOPES) or not tokens.get("refresh_token") or not tokens.get("access_token"):
        raise ValueError("Required scopes or offline refresh token missing")
    expires = datetime.now(timezone.utc) + timedelta(seconds=int(tokens.get("expires_in", 3600)))
    with psycopg.connect(db.url) as conn:
        conn.execute("INSERT INTO oauth_connections (user_id, provider, access_ciphertext, refresh_ciphertext, scopes, expires_at) "
                     "VALUES (%s,'google',%s,%s,%s,%s) ON CONFLICT (user_id, provider) DO UPDATE SET "
                     "access_ciphertext=EXCLUDED.access_ciphertext, refresh_ciphertext=EXCLUDED.refresh_ciphertext, "
                     "scopes=EXCLUDED.scopes, expires_at=EXCLUDED.expires_at, updated_at=now()",
                     (user_id, cipher.encrypt(tokens["access_token"].encode()),
                      cipher.encrypt(tokens["refresh_token"].encode()), " ".join(sorted(granted)), expires))
    db.audit(user_id, "oauth.google.connected", {"scopes": sorted(granted)})


def disconnect(db: Repository, user_id: UUID) -> bool:
    with psycopg.connect(db.url) as conn:
        removed = conn.execute("DELETE FROM oauth_connections WHERE user_id=%s AND provider='google' RETURNING user_id",
                               (user_id,)).fetchone() is not None
    if removed:
        db.audit(user_id, "oauth.google.disconnected", {})
    return removed


def read_items(db: Repository, user_id: UUID, kind: str, http: httpx.Client | None = None) -> dict:
    if kind not in ("mail", "calendar"):
        raise ValueError("Invalid collection")
    _, _, _, cipher = settings()
    with psycopg.connect(db.url) as conn:
        row = conn.execute("SELECT access_ciphertext, refresh_ciphertext, scopes, expires_at FROM oauth_connections "
                           "WHERE user_id=%s AND provider='google'", (user_id,)).fetchone()
    if row is None:
        raise LookupError("Google account not connected")
    required = SCOPES[0 if kind == "mail" else 1]
    if required not in row[2].split():
        raise PermissionError("Required read scope not granted")
    token = cipher.decrypt(bytes(row[0])).decode()
    def run(client: httpx.Client) -> dict:
        nonlocal token
        if row[3] is None or row[3] <= datetime.now(timezone.utc) + timedelta(seconds=60):
            if row[1] is None:
                raise PermissionError("Refresh token missing; reconnect account")
            client_id, client_secret, _, _ = settings()
            response = client.post(TOKEN_URL, data={"client_id": client_id, "client_secret": client_secret,
                "refresh_token": cipher.decrypt(bytes(row[1])).decode(), "grant_type": "refresh_token"})
            response.raise_for_status()
            refreshed = response.json()
            granted = set(refreshed.get("scope", row[2]).split())
            if required not in granted or not granted.issubset(set(SCOPES)):
                raise PermissionError("Refreshed read scope invalid; reconnect account")
            token = refreshed.get("access_token")
            if not isinstance(token, str) or not token:
                raise ValueError("Refreshed access token missing")
            rotated = refreshed.get("refresh_token")
            if rotated is not None and (not isinstance(rotated, str) or not rotated):
                raise ValueError("Refreshed refresh token invalid")
            refresh_ciphertext = cipher.encrypt(rotated.encode()) if rotated else bytes(row[1])
            lifetime = int(refreshed.get("expires_in", 3600))
            if lifetime <= 0:
                raise ValueError("Refreshed token expiry invalid")
            expires = datetime.now(timezone.utc) + timedelta(seconds=lifetime)
            with psycopg.connect(db.url) as conn:
                updated = conn.execute("UPDATE oauth_connections SET access_ciphertext=%s, refresh_ciphertext=%s, scopes=%s, "
                             "expires_at=%s, updated_at=now() WHERE user_id=%s AND provider='google' "
                             "AND access_ciphertext=%s RETURNING user_id",
                             (cipher.encrypt(token.encode()), refresh_ciphertext, " ".join(sorted(granted)),
                              expires, user_id, bytes(row[0]))).fetchone()
                if updated is None:
                    raise PermissionError("Google connection changed; retry with the current connection")
        url = ("https://gmail.googleapis.com/gmail/v1/users/me/messages" if kind == "mail" else
               "https://www.googleapis.com/calendar/v3/calendars/primary/events")
        params = {"maxResults": 10} if kind == "mail" else {"maxResults": 10, "singleEvents": "true", "orderBy": "startTime", "timeMin": datetime.now(timezone.utc).isoformat()}
        result = client.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
        result.raise_for_status()
        data = result.json()
        # Return limited metadata only; never return credentials or arbitrary provider payload.
        if kind == "mail":
            return {"messages": [{"id": x["id"], "threadId": x.get("threadId")} for x in data.get("messages", [])[:10]]}
        return {"events": [{"id": x["id"], "summary": x.get("summary", ""), "start": x.get("start", {})} for x in data.get("items", [])[:10]]}
    if http is None:
        with httpx.Client(timeout=10) as client:
            return run(client)
    return run(http)
