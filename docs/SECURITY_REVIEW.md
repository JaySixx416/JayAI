# Credential and OAuth review — 0.24.1

## Scope and result

Reviewed `jayai/google.py`, OAuth API routes, connection schema, launcher key handling, and learning deletion/audit behavior. This is an initial source review with automated regression tests. It does not establish production readiness or live Google/PostgreSQL correctness.

## Controls present

- OAuth state is random; only its hash is stored. PKCE verifier and access/refresh tokens are Fernet encrypted with `JAYAI_TOKEN_KEY` before database storage.
- OAuth attempts are user-scoped, expire after ten minutes, and are consumed before token exchange. Expired attempts are cleaned when another authorization starts.
- Configured redirect must be HTTP on literal `127.0.0.1` with an explicit valid port, without credentials or a fragment. The parsed hostname is checked, preventing a misleading loopback prefix followed by a remote authority.
- Initial consent must return exactly the requested Gmail/calendar read scopes and an offline refresh token. No write scopes are requested.
- Refresh checks the required read scope and rejects scopes outside the read allowlist. An omitted scope preserves the previously recorded scopes. A supplied replacement refresh token is encrypted and saved; otherwise the existing encrypted refresh token is retained.
- Refresh writes compare the original encrypted access token, preventing an older request from overwriting a changed connection. If the connection changed or was deleted, the request stops before reading provider data; retry against the current connection.
- API connection operations use authenticated user IDs. Returned collections are limited to ten items and selected metadata. Credentials are not returned.
- The foreground Linux launcher binds loopback and disables Uvicorn request access logging. The dashboard key is held only in the current browser tab, never browser storage; the launcher rejects a symlinked key path and atomically replaces the existing key file. The stable profile directory contains the user UUID and dashboard key file.

## Remaining production gates

| Area | Current behavior | Required next evidence/work |
| --- | --- | --- |
| Encryption key custody | One environment-supplied Fernet key; no managed rotation | Define protected deployment storage, backup custody, staged rotation/re-encryption, recovery and rotation tests |
| Disconnect | Deletes the user's local connection; does not revoke at Google | Add reviewed provider revocation semantics and failure handling; currently revoke consent separately in the Google account |
| Retention | Ten-minute OAuth validity; expired attempts cleaned on new start; jobs/audits persist | Define retention periods, scheduled cleanup, account purge and backup expiry; verify erasure across retained copies |
| Refresh concurrency | Conditional update stops stale writes | Run concurrent refresh/disconnect tests against real PostgreSQL; mocks verify intent only |
| Provider lifecycle | Mocked token exchange/read checks | Verify real consent, partial grants, expiry, refresh rotation, invalid grants and reconnect without logging credentials |
| Deployment auth | Development shared dashboard key | Establish production identity/session handling before remote or multi-user deployment |
| Dashboard/browser logging | Dashboard keys are not persisted by the browser; the standalone launcher disables Uvicorn access logs so OAuth callback query values are not written by request logging | Keep callback values out of application logs and add session-based, revocable auth before broader access |
| Untrusted content | Connector metadata is separate from planning | Keep email/web/document/tool content out of planning until isolation tests and structured action policy are implemented |

## Operator notes

Keep the existing token encryption key when upgrading: replacing it without re-encrypting stored ciphertext makes existing connections unreadable. Keep that key separate from database backups, and do not paste it into logs or reports. Reconnect accounts if the original key has been lost.

Local disconnect removes stored tokens, but prior backups can still contain encrypted token rows. No claim of provider revocation or backup erasure is made by the disconnect endpoint.

## Test evidence

Full Python 3.12 suite: **99 passed, 1 warning** (existing Starlette/AnyIO deprecation). New tests cover deceptive redirect authorities, refresh-token rotation/preservation, removed/broadened scopes, missing access tokens, and connection changes before persistence. Live services and production gates above remain unverified.
