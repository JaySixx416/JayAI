# JayAI 0.24.2 database connection and upgrade

For the standalone launchers, install steps, and upgrade checklist, see [`docs/STANDALONE.md`](docs/STANDALONE.md). The launcher performs a connection check and applies pending migrations automatically.

Install the complete `JayAI-CrossDevice-0.24.2` folder beside your existing project. Do not copy only selected source files: the database migrations add approval history, tool-call limits, explicit learning records, and permission expiry. Keep your existing PostgreSQL database and its data.

## Windows PC — PowerShell

From the extracted project folder, set connection values for this PowerShell process and apply pending migrations. Type the password at the secure prompt; it is not printed. This uses separate PostgreSQL parameters, so URL encoding is not involved.

```powershell
$secret = Read-Host 'JayAI database password' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $env:JAYAI_DB_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $env:JAYAI_DB_HOST = '127.0.0.1'
    $env:JAYAI_DB_PORT = '5432'
    $env:JAYAI_DB_NAME = 'jayai'
    $env:JAYAI_DB_USER = 'jayai'
    .\.venv\Scripts\python.exe -m jayai db-check
    if ($LASTEXITCODE -ne 0) { throw 'Database connection failed.' }
    .\.venv\Scripts\python.exe -m jayai migrate
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    Remove-Item Env:JAYAI_DB_PASSWORD -ErrorAction SilentlyContinue
}
```

Expected: connection check says `JayAI PostgreSQL connection: OK`; migration applies 010–013 (or says none if already current). This does not reset the database or alter PostgreSQL roles. Run commands from the folder containing `pyproject.toml`.

## Chromebook — Linux terminal

From the extracted folder, use the Linux venv and enter the password privately:

```bash
read -s -p 'JayAI database password: ' JAYAI_DB_PASSWORD; echo
export JAYAI_DB_PASSWORD JAYAI_DB_HOST=127.0.0.1 JAYAI_DB_PORT=5432 JAYAI_DB_NAME=jayai JAYAI_DB_USER=jayai
.venv/bin/python -m jayai db-check && .venv/bin/python -m jayai migrate
unset JAYAI_DB_PASSWORD
```

The Linux commands target the PostgreSQL server reachable from the Linux development environment; they do not grant ChromeOS host access. See `docs/CHROMEBOOK.md` for the device-scope boundary.

Existing `JAYAI_DATABASE_URL` configuration remains supported when `JAYAI_DB_PASSWORD` is absent. When a separate password is supplied, it takes precedence and Psycopg builds a safe parameter connection string. Never print that string or include credentials in logs. The dashboard/API process must receive the same database environment when it starts.
