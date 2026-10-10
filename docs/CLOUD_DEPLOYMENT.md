# Cloud deployment preparation

JayAI 0.25.0 is a local Linux prototype. This guide describes the work needed
before accessing it from a laptop or phone. It does not mean cloud deployment
is currently supported, and it does not authorize exposing the development API
to the internet.

## Render staging preparation

The repository includes a reviewable [`render.yaml`](../render.yaml) for a
new staging environment. It defines one HTTPS web service and one managed
PostgreSQL database in the same region. It does not contain credentials and it
does not deploy by itself.

Before creating the Render services:

1. Create or select a Render workspace and review the service/database plan.
2. Import the repository and inspect the blueprint instead of deploying
   immediately.
3. Set the `JAYAI_OIDC_*` values as Render secrets. The redirect URI must be
   the final Render HTTPS URL plus `/auth/oidc/callback`.
4. Leave `JAYAI_OIDC_BOOTSTRAP_USER_ID` unset until the staging database has
   been created and its first JayAI user has been deliberately identified.
5. Deploy only after confirming that the database is the new staging database,
   not the local or existing user database.

The Render start command binds Uvicorn to `0.0.0.0:$PORT` as required by the
platform, disables request access logging, and runs migrations against the
blueprinted staging database. It must never be copied into the Chromebook
launcher or used with the existing local database URL. The dashboard remains
disabled outside development mode until a production dashboard rollout is
explicitly reviewed; staging API checks should use the OIDC endpoints.

## Recommended path: private access first

Keep JayAI on a Linux machine or private VPS and put it behind a private VPN
such as Tailscale or WireGuard. Use a reverse proxy bound to the private
interface, with HTTPS if the VPN does not already provide trusted transport.

Do not expose these directly:

- PostgreSQL
- Ollama
- Redis
- the development dashboard key
- port 8000 on a public network interface

The current launcher remains loopback-bound. A future VPN deployment should
use an explicitly reviewed binding or reverse proxy configuration rather than
changing the default casually.

## Before public access

The following production gates must be completed first:

- Replace the shared development dashboard key with real user accounts,
  expiring sessions, logout, revocation, and recovery.
- Follow the [authentication design](AUTHENTICATION.md) before choosing an
  identity provider or applying a session migration.
- Add CSRF protection and secure cookie settings if browser sessions are used.
- Store database, model, OAuth, and provider secrets in a managed secret store.
- Add HTTPS, rate limiting, request-size limits, and structured security logs
  that never contain keys or OAuth query values.
- Define account deletion, retention, backup expiry, and encrypted-backup
  procedures.
- Run concurrency tests against an isolated PostgreSQL database and Redis
  instance.
- Decide where model inference runs. Ollama on a small cloud CPU may be slow;
  a private GPU host or approved managed provider needs separate review.
- Add health checks, restart supervision, alerts, and a tested restore path.

## Suggested cloud shape

```text
Laptop / phone
        |
   HTTPS or private VPN
        |
 reverse proxy
        |
 JayAI API + worker ---- Ollama or approved model host
        |
 managed PostgreSQL ---- private Redis (optional)
```

Keep the database and Redis on private network addresses. Permit only the API
and worker security groups to reach them. Keep Ollama private as well.

The current Render blueprint does not provision Ollama or Redis. Model
inference must remain on an approved private host, or be added as a separately
reviewed private service. Do not put Ollama on the public web service.

## Staged rollout

1. Run the current local Linux setup and complete the harmless health-check
   smoke test.
2. Deploy a disposable copy using an isolated database and test credentials.
3. Verify login, logout, expiry, approval, pause, cancellation, restart
   recovery, backups, and audit records from both laptop and mobile browsers.
4. Put the disposable copy behind a private VPN and test from a second device.
5. Only after the production gates close, consider a public HTTPS deployment.

Never copy the existing development dashboard key or profile secrets into a
cloud host. Treat cloud deployment as a new environment with new credentials.
