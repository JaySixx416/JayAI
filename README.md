# JayAI CrossDevice 0.25.0

JayAI is a **self-hosted local task dashboard** for Linux. It does not depend on ChatGPT or a paid model API. The user reviews a local model's plan and explicitly approves the currently supported read-only Linux checks.

“Standalone” means the application and dashboard run on your own devices. This is not a single-file executable: Python, PostgreSQL, and a local Ollama model are runtime dependencies. Redis is optional for the queue prototype. Google OAuth is optional and requires your own Google OAuth application.

## Current capabilities

- Local Ollama planning with schema validation and a bounded read-only action allowlist.
- Per-user PostgreSQL jobs, immutable plans, approval/rejection history, limits, audit records, expiring permissions, and explicit learning notes.
- Exact-plan approval before read-only health or process checks.
- Loopback-only dashboard and authenticated development API.
- Chromebook Linux diagnostics report Linux container scope. They do not inspect ChromeOS itself.
- Learning export and review-only routine suggestions based on repeated verified categories. Suggestions have no scope, schedule, or executable action and never run automatically.
- Chromebook-ready Song Studio for structured lyric review and Suno prompt packaging. The optional OpenAI API integration is only called when you submit a song; Suno creation remains a manual step.

File, browser, and Google read connectors are not connected to job execution. Repairs, arbitrary shell commands, installations, deletion, account changes, message sending, purchases, and public posting remain disabled.

## Start here

New to JayAI? Start with the friendly [Quick start guide](QUICKSTART.md).
Read [Standalone setup and operations](docs/STANDALONE.md) for Linux setup, credentials, migrations, startup, backups, and troubleshooting.

Other references:

- [Chromebook scope and setup](docs/CHROMEBOOK.md)
- [Local AI and Ollama](docs/AI.md)
- [Quick start guide](QUICKSTART.md)
- [Song Studio and Suno export](docs/MUSIC.md)
- [Database setup and migration](FIX_DATABASE.md)
- [Cloud deployment preparation](docs/CLOUD_DEPLOYMENT.md)
- [Cloud authentication design](docs/AUTHENTICATION.md)
- [Open work and verification status](TODO.md)

## Quick start

Install the project dependencies and create a virtual environment as documented in `docs/STANDALONE.md`. Then:

**Linux terminal:**

```bash
./scripts/start-jayai.sh
```

The launcher checks PostgreSQL, applies pending idempotent migrations, retains a non-secret development user ID in the OS user profile, generates a fresh development dashboard key for that run, and starts Uvicorn bound to `127.0.0.1`. Keep the terminal open. Stop with Ctrl+C. Enter the displayed key in the local dashboard.

Run tests from the project root:

```text
python -m pytest -q
```

## Security and current maturity

This remains a development prototype. The API key is temporary local development authentication, not production identity management. Keep JayAI bound to loopback and never publish port 8000 to the LAN or internet. Secrets must not be placed in source files, prompts, logs, or chat.

See `TODO.md` for the exact distinction between implemented code and checks that still require live devices, Redis, security review, or a user-selected business workflow.

See [credential and OAuth review](docs/SECURITY_REVIEW.md) for the current controls, fixes, and remaining production gates.

See [untrusted data boundary](docs/UNTRUSTED_DATA.md) for supported planning inputs and connector integration gates.

Future addon ideas and their safety boundaries are listed in the [Quick start guide](QUICKSTART.md). They are not enabled features in 0.25.0.
