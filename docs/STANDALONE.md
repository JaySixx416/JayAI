# JayAI standalone setup and operations

This guide is the single install/run reference for release 0.25.0.

## What “standalone” means

JayAI is self-hosted: its API and dashboard run on your PC or Chromebook Linux container, and planning uses Ollama on a local machine. No ChatGPT sign-in, OpenAI API key, or paid model API is required.

It is not a single executable that contains its services. The runtime needs Python 3.11–3.13, PostgreSQL, and Ollama with a supported model. Redis is optional and only needed for the queue worker. Google account access is optional and requires a separately configured OAuth client. The app currently executes only approved, read-only PC checks; connectors are not yet part of task execution.

## Windows 11 PC install

### Prerequisites

Install Python 3.12, PostgreSQL, Ollama for Windows, and PowerShell 7. Keep PostgreSQL local. JayAI's dashboard and API listen only on `127.0.0.1`.

For this machine, the smaller `qwen2.5:0.5b` model was confirmed to produce a valid plan after `qwen2.5:3b` timed out. Install it once in PowerShell:

```powershell
ollama pull qwen2.5:0.5b
ollama list
```

### Extract and install

Extract the complete ZIP into a new folder, for example `F:\Projects\JayAI\JayAI-CrossDevice-0.24.2`. Do not extract over 0.23.0. In PowerShell 7:

```powershell
Set-Location 'F:\Projects\JayAI\JayAI-CrossDevice-0.24.2'
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m pytest -q
```

Keep your existing `jayai` PostgreSQL database. Migrations are ordered, idempotent, and additive. The launcher checks the connection and applies only migrations that are not already recorded.

### First database setup and existing account continuity

Skip database creation if your existing `jayai` database already works. For a new installation, open PostgreSQL SQL Shell (psql) as its administrator and run the following SQL/psql commands. `\password` prompts privately; do not put passwords in command history:

```sql
CREATE ROLE jayai LOGIN;
\password jayai
CREATE DATABASE jayai OWNER jayai;
```

On Chromebook Linux, open that administrator shell with `sudo -u postgres psql`, run the same commands, then enter `\q`. Start the local PostgreSQL service if needed with `sudo service postgresql start`. The launchers default to TCP `127.0.0.1:5432`, database/user `jayai`; enter the password you assigned to that role. See [FIX_DATABASE.md](../FIX_DATABASE.md) for connection diagnosis.

To retain an existing application account when upgrading, set its existing UUID before the first launch:

```powershell
$env:JAYAI_DEV_USER_ID = 'YOUR-EXISTING-USER-UUID'
.\scripts\Start-JayAI.ps1
```

Replace the placeholder with your actual previous development user ID. Keep supplying that value on subsequent starts, or save that UUID in the launcher profile file described below. A new launcher profile creates a new account view even when using the same database.

### Start, use, stop

From the project folder:

```powershell
.\scripts\Start-JayAI.ps1
```

The script prompts for the PostgreSQL password without echoing it, checks the database, applies pending migrations, then starts the API in the foreground on `127.0.0.1:8000`. It stores only the development user UUID (not a password or API key) under your Windows user profile. The dashboard key is generated for the current run and printed once in that terminal. Open `http://127.0.0.1:8000/` on the Windows PC and enter that key. Keep the terminal open; press Ctrl+C there to stop JayAI.

The default local model is `qwen2.5:0.5b`. To choose another supported model for this session, set it before starting:

```powershell
$env:JAYAI_LOCAL_MODEL = 'qwen2.5:1.5b'
.\scripts\Start-JayAI.ps1
```

Use only a model already installed by Ollama. Clear a session override with `Remove-Item Env:JAYAI_LOCAL_MODEL`.

The development user UUID is stored at `%LOCALAPPDATA%\JayAI\development-user-id.txt`. Removing that file causes the next start to create a new application user; existing database rows are not deleted, but will no longer appear under the new user. Do not delete it unless you intend to create a separate empty user view.

## Chromebook Linux install

This is for running JayAI inside Crostini. It does not grant ChromeOS host access. The app's `pc_health` and `pc_processes` actions inspect the Linux container only.

In Chromebook Linux Terminal, install Python tooling and PostgreSQL if not already present, extract the ZIP into Linux files, and install the environment:

```bash
sudo apt update
sudo apt install python3-venv python3-pip postgresql unzip
cd ~/JayAI-CrossDevice-0.25.0
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
```

Alternatively, run `bash scripts/setup-chromebook.sh`. It creates the virtual
environment when needed, installs JayAI's pinned dependencies, and verifies
the PostgreSQL tools, Ollama, and recommended `qwen2.5:0.5b` model before you
start the app.

Install and start Ollama using its official Linux instructions. On a constrained Chromebook, use only `qwen2.5:0.5b`; do not install a larger model without checking available memory and disk space.

Run the launcher:

```bash
./scripts/start-jayai.sh
```

If no `JAYAI_DATABASE_URL` or `JAYAI_DB_PASSWORD` is set and the PostgreSQL
server tools are installed, the Chromebook launcher automatically initializes
and starts a real user-owned PostgreSQL cluster under
`~/.local/state/JayAI/postgres`, using a private Unix socket and port 55432.
This avoids requiring `sudo` or a system service. Set `JAYAI_DATABASE_URL`
explicitly to use an existing PostgreSQL server instead.

It prompts privately for a PostgreSQL password if no database environment is already configured, checks and migrates the database, stores only a user UUID under `~/.local/state/JayAI`, generates a new temporary dashboard key for the run, and starts on `127.0.0.1:8000`. Open `http://localhost:8000/` in ChromeOS Chrome. Keep the Linux Terminal open and stop with Ctrl+C.

Song Studio is available at `http://localhost:8000/music` and from the dashboard rail. It is optional and requires an OpenAI API key set as `JAYAI_MUSIC_API_KEY` in the launch terminal; see [Song Studio](MUSIC.md). The key is not stored in the database. Only the submitted song brief and lyrics are sent to the provider when you click **Run studio review**.

For a custom port, set `JAYAI_PORT` before starting. For example:

```bash
JAYAI_PORT=8001 ./scripts/start-jayai.sh
```

The shell launcher can use either `JAYAI_DATABASE_URL` or the separate `JAYAI_DB_*` variables. The password is not written by the launcher.

## Open the Windows-hosted dashboard from Chromebook Chrome

Keep the Windows API bound to `127.0.0.1:8000`; do not expose it to the Wi-Fi network. Ensure the Windows JayAI process and Windows OpenSSH Server (`sshd`) are running. On Windows, check the current Wi-Fi IPv4 with PowerShell:

```powershell
Get-NetIPConfiguration |
    Where-Object { $_.IPv4DefaultGateway } |
    Select-Object InterfaceAlias, @{Name='IPv4';Expression={$_.IPv4Address.IPAddress}}
```

The Windows host reported `192.168.229.77` during the 0.24.2 setup. Replace that address below if Windows reports a different one. The SSH authorized key must permit forwarding to `127.0.0.1:8000` in addition to the existing Ollama (`11434`) and companion (`8765`) destinations. For this setup the key uses restricted forwarding options in `C:\ProgramData\ssh\administrators_authorized_keys`; add `permitopen="127.0.0.1:8000"` to that key's existing options and retain `restrict`, `command="cmd /c exit"`, `port-forwarding`, and existing `permitopen` entries. Do not loosen the key to unrestricted forwarding.

In Chromebook Linux Terminal, run the full command:

```bash
ssh -N -i ~/.ssh/jayai_ollama \
  -o IdentitiesOnly=yes \
  -o BatchMode=yes \
  -o ConnectTimeout=10 \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -L 127.0.0.1:8000:127.0.0.1:8000 \
  jayta@192.168.229.77
```

A successful `-N` tunnel stays in the terminal without a shell prompt. Leave it open, then visit `http://localhost:8000/` in Chrome and enter the key shown by the Windows launcher. If the Chromebook reports `Address already in use`, stop the earlier SSH tunnel using Ctrl+C before retrying. If SSH reports `administratively prohibited`, the key's restricted forwarding allowlist still needs the port 8000 entry. If the browser says connection refused, check that the tunnel and Windows API are both running.

## Database configuration and upgrade

The launchers support `JAYAI_DATABASE_URL` or separate `JAYAI_DB_HOST`, `JAYAI_DB_PORT`, `JAYAI_DB_NAME`, `JAYAI_DB_USER`, and `JAYAI_DB_PASSWORD` variables. Prefer the secure interactive password prompt. The application does not automatically load `.env` files.

Before upgrading, stop JayAI and back up PostgreSQL. Extract the new release into a new folder, create a fresh virtual environment, install the pinned dependencies, run the tests, then start the launcher. It runs `db-check` and idempotent migrations without dropping existing data. Keep the previous folder until the new release passes your device smoke checks.

If `pg_dump` is installed, PostgreSQL's custom backup format is recommended. Windows PowerShell example (it prompts for a PostgreSQL password only if your PostgreSQL client configuration requires one):

```powershell
pg_dump --format=custom --file (Join-Path $env:USERPROFILE 'jayai-backup.dump') --dbname 'host=127.0.0.1 port=5432 dbname=jayai user=jayai'
```

Chromebook Linux example:

```bash
pg_dump --format=custom --file "$HOME/jayai-backup.dump" --dbname 'host=127.0.0.1 port=5432 dbname=jayai user=jayai'
```

Keep backups private. Never paste connection strings containing passwords into chat or source files.

## Optional Redis worker

The dashboard prototype works without Redis. The optional worker requires a running Redis service and `JAYAI_REDIS_URL` in its environment. It only advances delivered jobs to the plan-review state; it does not execute tools or bypass approval. Start it in a separate terminal using `.venv\Scripts\python.exe -m jayai worker` on Windows or `.venv/bin/python -m jayai worker` on Linux. Stop it with Ctrl+C.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| PostgreSQL connection failed | Confirm PostgreSQL is running, database `jayai` and role `jayai` exist, and the password is correct. Run `python -m jayai db-check` from the project venv. |
| Migration failed | Keep the full error private if it includes connection details; verify database access and rerun after fixing the cause. Migrations are idempotent. |
| `Local model unavailable` | Start Ollama on the same machine as the JayAI API. |
| `Local model missing` | Run `ollama list`; install the selected model with `ollama pull <model-id>`. |
| Model request times out | Use `qwen2.5:0.5b`, check CPU/RAM availability, and retry a short goal. |
| Chromebook dashboard is unreachable | Confirm Windows JayAI answers `http://127.0.0.1:8000/`, `sshd` is running, the tunnel stays open, and the key allows `permitopen="127.0.0.1:8000"`. |
| `Address already in use` in SSH | Stop an older tunnel bound to local port 8000, then reconnect. |
| `administratively prohibited` in SSH | Windows accepted the key but its forwarding policy denied the destination. Add only the loopback port 8000 `permitopen` entry and preserve the existing restrictions. |
| Dashboard key rejected | Use the current run's key from the launcher terminal. It is intentionally regenerated after a restart. |

## Verification limits

The release test suite is mocked and cannot prove that a specific Windows PC, Chromebook, PostgreSQL service, Redis service, Google OAuth client, or installed Ollama model works. Check those integrations on the target device before relying on them. See `TODO.md` for the outstanding live checks and disabled capabilities.

## Device acceptance check

Run these steps on Windows, then on Chromebook Linux. Record the version, device, time, and observed result beside the corresponding unchecked TODO entry.

1. Start with the launcher; confirm database checks/migrations succeed and the dashboard returns HTTP 200.
2. Enter the current dashboard key. Create a request for a **local PC health check** and inspect the model plan and expected evidence.
3. Reject that plan; confirm it is recorded as rejected and cannot run. Create a second request, approve its exact plan, and run it once.
4. Confirm the result labels Windows or Linux container scope correctly. Confirm a duplicate execution does not create a second tool action.
5. Inspect Learning, export JSON, verify the file contains your account's records, and remove a temporary explicit preference.
6. Stop with Ctrl+C, restart, and confirm the same user UUID retains previous jobs. A newly generated dashboard key must replace the prior key.
7. For the Chromebook-to-Windows path, keep the tunnel open, request the dashboard through port 8000, and confirm the SSH terminal reports no forwarding denial. Test the companion separately before marking its TODO complete.

Redis queue acceptance requires a real Redis server plus PostgreSQL: create a queued task, run the documented worker, confirm `WAITING_FOR_APPROVAL`, and exercise expired pending entries and restart recovery. Automated unit tests do not establish those live results.
