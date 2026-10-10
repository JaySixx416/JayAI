# Cloud authentication design

JayAI 0.25.0 still uses a single-user development dashboard key. That key is
acceptable only for local loopback development and must not be used as the
long-term login method for cloud access.

## Recommended design

Use an external OpenID Connect (OIDC) provider for identity and keep JayAI’s
session separate from provider tokens:

1. The browser starts a login with the configured OIDC provider.
2. JayAI validates the callback state, nonce, issuer, audience, and signature.
3. JayAI maps the provider subject to one JayAI user record.
4. JayAI creates a random opaque session token.
5. Only a hash of that token is stored in PostgreSQL.
6. The browser receives the token in a `Secure`, `HttpOnly`, `SameSite=Lax`
   cookie.
7. Each request checks that the session is unexpired, unrevoked, and scoped to
   the authenticated user.

Provider access tokens and refresh tokens must remain separate from login
sessions. A login session must not grant Google mail/calendar access by itself.

## Session policy

The eventual implementation should provide:

- Short-lived access sessions, for example 8–12 hours.
- Explicit logout that revokes the current session.
- “Sign out everywhere” by revoking all sessions for the user.
- Idle and absolute expiry.
- Session rotation after login and sensitive events.
- CSRF protection for cookie-authenticated state-changing requests.
- Audit events for login, logout, expiry, rejection, and revocation without
  logging tokens or authorization codes.

## Required database shape

Before applying a migration, review an isolated schema change containing:

- A provider subject mapping with a unique `(issuer, subject)` pair.
- Session rows containing a token hash, user ID, issued time, expiry, last-used
  time, revoked time, and optional device label.
- Indexes for active sessions by token hash and user ID.
- Cascading or explicit cleanup behavior when a user is removed.

Migration `014_oidc_sessions.sql` now describes this foundation, but it has
not been applied to the existing database. It must be reviewed and tested
against a clearly isolated database before any real upgrade.

## Current API wiring

The API now exposes `/auth/oidc/login`, `/auth/oidc/callback`, and
`/auth/logout`. Configure the issuer, authorization endpoint, token endpoint,
JWKS URL, client ID, client secret, and HTTPS redirect URI with the
`JAYAI_OIDC_*` environment variables. The callback validates state, nonce,
PKCE, issuer, audience, freshness, and the signed ID token before creating a
12-hour HttpOnly session cookie. Existing linked identities are required;
first-time linking is allowed only when the one-time deployment bootstrap
variable `JAYAI_OIDC_BOOTSTRAP_USER_ID` is explicitly set.

The browser never receives or stores the provider secret, access token,
refresh token, or JayAI session token in web storage. The session token is an
HttpOnly cookie and only its hash is persisted. Set
`JAYAI_OIDC_COOKIE_SECURE=true` for HTTPS deployments. The development API key
remains available only in `JAYAI_ENV=development` and is not a cloud login
mechanism.

## Development transition

Keep the current `JAYAI_DEV_API_KEY` flow available only when
`JAYAI_ENV=development`. A future production mode should fail closed unless
OIDC settings, trusted HTTPS origin settings, secure cookie settings, and the
session store are configured. It must not silently fall back to the development
key.

## Verification gates

Use an isolated PostgreSQL database and synthetic OIDC responses to test:

- Invalid state, nonce, issuer, audience, signature, and expiry.
- First login, returning login, disabled account, and unknown subject.
- Logout, expiry, revocation, and sign-out-everywhere.
- Concurrent callbacks and session rotation.
- CSRF rejection for state-changing requests.
- Cross-user job, result, file, learning, and OAuth ownership checks.

Do not use the existing user database for these tests, and do not log real
provider codes, tokens, keys, or personal data.
