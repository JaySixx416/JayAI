# Cloud deployment preparation

JayAI 0.25.0 is a local Linux prototype. This guide describes the work needed
before accessing it from a laptop or phone. It does not mean cloud deployment
is currently supported, and it does not authorize exposing the development API
to the internet.

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
