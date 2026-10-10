# Standalone Linux setup and operations

JayAI is a Linux-only local prototype. It requires Python 3.11–3.13,
PostgreSQL, and a local Ollama model. Redis is optional for the queue worker;
Google OAuth and Song Studio are optional.

## Install

Create the virtual environment and install the pinned project dependencies in
the normal Linux way. From the project root, run the launcher in the
foreground:

```bash
bash scripts/start-jayai.sh
```

The launcher checks PostgreSQL, applies pending idempotent migrations, retains
the development user UUID, generates a fresh dashboard key, and starts the API
on `127.0.0.1:8000`. Enter the displayed key at `http://localhost:8000/`.
Stop with Ctrl+C. Keep the key out of shell history and logs.

Set `JAYAI_DEV_USER_ID` to an existing account UUID before launch when
continuing an existing profile. Do not delete or recreate that profile.

## Local model

Install Ollama for Linux and pull the recommended model:

```bash
ollama pull qwen2.5:0.5b
ollama list
```

The planner uses the loopback Ollama endpoint. The supported actions are
read-only Linux health and process checks; host state outside the container is
not inspected.

## Database and backups

The launcher uses `JAYAI_DATABASE_URL` or the `JAYAI_DB_*` variables and never
writes the database password. Back up PostgreSQL before upgrades. Migrations
are forward-only and must be reviewed before applying them to an existing
database.

## Optional Redis worker

The dashboard works without Redis. If configured, start the worker in another
Linux terminal:

```bash
.venv/bin/python -m jayai worker
```

It advances delivered jobs to plan review and never bypasses approval.

## Troubleshooting and verification

Check `ollama list`, PostgreSQL availability, and the launcher output. Keep
the API loopback-bound. Automated tests are mocked and do not prove live
PostgreSQL, Redis, OAuth, or Ollama readiness; record real device evidence
separately.
