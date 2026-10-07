# JayAI Chromebook development

## Scope and references

- Work from `/home/jaysixx/JayAI-CrossDevice-0.25.0/JayAI-CrossDevice-0.25.0`.
- This copy is release 0.25.0. The Windows PC is unavailable; do not assume
  Windows 0.25.3 changes, services, models, or verification exist here.
- Read `README.md`, `pyproject.toml`, `TODO.md`, `docs/STANDALONE.md`,
  `docs/CHROMEBOOK.md`, and `docs/AI.md`. Use their Linux instructions;
  Windows launchers, companion checks, and Windows SSH tunnels are not the
  Chromebook-only startup path. Historical TODO evidence is not a live check.
- Crostini diagnostics cover the Linux container, not the ChromeOS host.

## Preserve existing state

- Preserve PostgreSQL, all existing data, credentials, and
  `~/.local/state/JayAI`. Never reset, drop, truncate, or recreate the database.
- Do not delete, rename, overwrite, or regenerate an existing user profile.
  Linux paths are case-sensitive: the 0.25.0 launcher uses
  `${XDG_STATE_HOME:-$HOME/.local/state}/jayai/development-user-id`, whereas
  the existing directory is `~/.local/state/JayAI`. Resolve existing-account
  continuity before launch; supply the verified existing `JAYAI_DEV_USER_ID`
  privately rather than allowing creation of a new account view.
- Keep passwords, connection strings, dashboard keys, and provider keys out
  of output, source, logs, and shell history. Do not dump environment values
  or credential files. JayAI does not automatically load `.env` files.
- Documentation/inspection work must not install dependencies, connect to
  PostgreSQL, run migrations, or start JayAI. The launcher performs database
  writes; use it only in an explicitly requested runtime task, after reviewing
  its migration and user-profile behavior against the existing setup.

## Existing environment and startup

- Reuse `.venv/bin/python`; do not recreate the venv. Inspection on 2026-10-06
  found Python 3.13.5 (supported range: 3.11–3.13), JayAI 0.25.0, all pinned
  runtime/test dependencies, and a clean `.venv/bin/python -m pip check`.
  `setuptools` is absent from the venv (a build requirement, not a missing
  runtime dependency); Playwright is optional and absent.
- `bash`, `python3`, `psql`, `pg_isready`, `curl`, and `git` are available on
  PATH; `ollama` and `redis-server` are not. This extracted project root is
  not a Git repository. TODO's claim that pinned dependencies are absent is
  stale for this venv; its historical test results are not current evidence.
- Supported startup is the foreground shell launcher. It currently lacks
  execute permission, so invoke `bash scripts/start-jayai.sh` from this root
  when runtime work is authorized. Do not run it merely to inspect it.
- It checks PostgreSQL, applies pending migrations, reuses or creates a user
  UUID, generates a dashboard key if none is supplied, and runs Uvicorn on
  `127.0.0.1:8000`. Keep loopback binding; stop with Ctrl+C. ChromeOS Chrome
  uses `http://localhost:8000/` (or the configured `JAYAI_PORT`).
- PostgreSQL configuration uses `JAYAI_DATABASE_URL` or `JAYAI_DB_*` variables;
  a supplied `JAYAI_DB_PASSWORD` takes precedence. The launcher privately
  prompts for a password if neither URL nor password is supplied. Existing
  server/database availability and credentials remain unverified.
- Local planning requires Ollama on `127.0.0.1:11434` with the exact model
  `qwen2.5:0.5b`; the launcher selects it via `JAYAI_LOCAL_MODEL`. A manual
  API launch otherwise defaults to the larger `qwen2.5:3b`.
- Ollama was not found on PATH or in the standard binary/model locations.
  The inspected container has 2.7 GiB RAM (about 903 MiB available), no swap,
  and 2.1 GiB free disk;
  check capacity before any later installation or model download.
- Redis service, Google OAuth, and Song Studio's `JAYAI_MUSIC_API_KEY` are
  optional for a local health task. The installed Redis Python package does
  not establish that a Redis service exists.

## Verification

- Safe preparation checks: `bash -n scripts/start-jayai.sh`, package metadata,
  and `.venv/bin/python -m pip check`. Do not infer live readiness from them.
- For code changes, inspect test fixtures before running
  `.venv/bin/python -m pytest -q`; avoid live database/service tests unless
  explicitly in scope. No tests or device acceptance checks were run during
  this documentation-only preparation.
- The next runtime milestone is one Chromebook standalone smoke test: resolve
  local Ollama and existing user continuity, verify the existing database and
  review pending migrations, launch locally, create a Linux-container health
  request, review and approve its exact plan, and verify harmless read-only
  completion. Record actual device evidence; never mark Windows checks done.
