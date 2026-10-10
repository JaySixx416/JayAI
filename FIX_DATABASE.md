# JayAI database setup and upgrade

JayAI is Linux-only in 0.25.0. For the everyday setup, use
[Quick start](QUICKSTART.md). The foreground launcher checks the configured
database and applies pending migrations automatically.

## Important safety note

These commands connect to PostgreSQL and may apply forward-only migrations.
They do not reset, drop, truncate, or recreate the database. Back up existing
data first and review a migration before applying it to an important account.

Do not put passwords in shell history, source files, goals, or reports. The
launcher can privately prompt when a password is needed.

## Chromebook/Linux terminal

From the project folder, configure the connection for this shell only:

```bash
read -s -p 'JayAI database password: ' JAYAI_DB_PASSWORD; echo
export JAYAI_DB_PASSWORD
export JAYAI_DB_HOST=127.0.0.1
export JAYAI_DB_PORT=5432
export JAYAI_DB_NAME=jayai
export JAYAI_DB_USER=jayai
```

Check the connection and apply pending migrations:

```bash
.venv/bin/python -m jayai db-check
.venv/bin/python -m jayai migrate
```

Remove the password from this shell when finished:

```bash
unset JAYAI_DB_PASSWORD
```

The same database settings must be present when starting JayAI. Prefer the
launcher’s normal configuration path and do not use a different database for
the API than the one you checked.

## Using a database URL

`JAYAI_DATABASE_URL` is also supported. If `JAYAI_DB_PASSWORD` is supplied,
the separate settings take precedence. Never print the resulting connection
string because it can contain credentials.

## If the check fails

Confirm that PostgreSQL is running inside or reachable from Linux, then check
the host, port, database name, user, and password. Do not respond to a failed
connection by deleting the data directory or recreating the database. Ask the
database administrator to resolve credentials or availability first.
