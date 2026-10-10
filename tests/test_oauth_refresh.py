from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet

from jayai import google


@pytest.mark.parametrize('redirect', [
    'http://127.0.0.1:8000@evil.example/callback',
    'http://127.0.0.1:bad/callback',
    'http://127.0.0.1:8000/callback#fragment',
])
def test_redirect_cannot_escape_loopback(monkeypatch, redirect):
    monkeypatch.setenv('JAYAI_GOOGLE_CLIENT_ID', 'client')
    monkeypatch.setenv('JAYAI_GOOGLE_CLIENT_SECRET', 'secret')
    monkeypatch.setenv('JAYAI_TOKEN_KEY', Fernet.generate_key().decode())
    monkeypatch.setenv('JAYAI_GOOGLE_REDIRECT_URI', redirect)
    with pytest.raises(RuntimeError):
        google.settings()


@pytest.mark.parametrize('case', ['rotate', 'preserve', 'lost_scope', 'broad_scope', 'missing_access', 'disconnected'])
def test_refresh_validates_and_persists_before_read(monkeypatch, case):
    cipher = Fernet(Fernet.generate_key())
    owner = uuid4()
    row = (cipher.encrypt(b'old-access'), cipher.encrypt(b'old-refresh'),
           ' '.join(google.SCOPES), datetime.now(timezone.utc) - timedelta(seconds=5))
    updates = []
    reads = []

    class Connection:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, sql, params):
            if sql.startswith('SELECT'):
                assert params == (owner,)
                return SimpleNamespace(fetchone=lambda: row)
            updates.append((sql, params))
            return SimpleNamespace(fetchone=lambda: None if case == 'disconnected' else (owner,))

    monkeypatch.setattr(google.psycopg, 'connect', lambda url: Connection())
    monkeypatch.setattr(google, 'settings', lambda: ('client', 'secret', 'http://127.0.0.1:8000/callback', cipher))

    def handle(request):
        if request.method == 'POST':
            assert request.url == google.TOKEN_URL
            payload = {'access_token': 'new-access', 'expires_in': 3600}
            if case == 'rotate':
                payload['refresh_token'] = 'new-refresh'
            if case == 'lost_scope':
                payload['scope'] = google.SCOPES[1]
            if case == 'broad_scope':
                payload['scope'] = ' '.join(google.SCOPES) + ' arbitrary-write'
            if case == 'missing_access':
                payload.pop('access_token')
            return httpx.Response(200, json=payload)
        reads.append(request)
        assert request.headers['Authorization'] == 'Bearer new-access'
        return httpx.Response(200, json={'messages': [{'id': 'one', 'threadId': 'thread'}]})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        if case in ('lost_scope', 'broad_scope', 'missing_access', 'disconnected'):
            with pytest.raises((PermissionError, ValueError)):
                google.read_items(SimpleNamespace(url='unused'), owner, 'mail', client)
            assert not reads
            if case != 'disconnected':
                assert not updates
        else:
            assert google.read_items(SimpleNamespace(url='unused'), owner, 'mail', client)['messages'][0]['id'] == 'one'
            sql, params = updates[0]
            assert cipher.decrypt(params[0]) == b'new-access'
            assert cipher.decrypt(params[1]) == (b'new-refresh' if case == 'rotate' else b'old-refresh')
            assert params[4] == owner and params[5] == row[0]
            assert 'AND access_ciphertext=%s' in sql
