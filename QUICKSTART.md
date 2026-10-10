# JayAI quick start

This is the friendly, everyday-person version of the setup. JayAI runs inside
Linux (including Chromebook Linux/Crostini), opens a dashboard in your browser,
and asks you to approve a plan before it performs one of its small,
read-only checks.

## Before you begin

You need:

- Linux with Python 3.11, 3.12, or 3.13.
- PostgreSQL running locally or reachable through the database settings.
- Ollama running on the same Linux machine.
- The small `qwen2.5:0.5b` model. It is the best choice for a modest Chromebook.
- This project folder and its existing `.venv` environment.

Redis is optional. You do not need it for the normal dashboard workflow.

JayAI is intentionally Linux-only in this release. Chromebook Linux can see
the Linux container, not the ChromeOS host.

## First-time setup

Open Linux Terminal and move into the project folder:

```bash
cd /path/to/JayAI-CrossDevice-0.25.0
```

Use the project’s existing virtual environment. Do not create a second one if
`.venv` is already present:

```bash
.venv/bin/python -m pip check
```

Install and start Ollama using its normal Linux instructions, then download the
recommended model:

```bash
ollama pull qwen2.5:0.5b
ollama list
```

Before the first real launch, make sure your PostgreSQL connection is already
configured. JayAI accepts either `JAYAI_DATABASE_URL` or the separate
`JAYAI_DB_*` variables. Never paste a password into this document, a goal, or
the dashboard.

If you are continuing an existing JayAI account, set its UUID in
`JAYAI_DEV_USER_ID` before launch. Do not delete or recreate the profile.

## Start JayAI

From the project folder:

```bash
bash scripts/start-jayai.sh
```

Keep this terminal open. The launcher checks the database, applies any
pending migrations, reuses the development profile, creates a temporary local
dashboard key, and starts JayAI on:

```text
http://127.0.0.1:8000/
```

Open that address in Chrome or another browser. The launcher prints the
dashboard key once. Paste it into the dashboard’s key box. The browser keeps
the key only in the current tab; it is not saved in browser storage.

The API is bound to your own machine only. Do not publish port 8000 to Wi-Fi,
the internet, or a public tunnel.

## Use the dashboard

1. Enter the current dashboard key and choose **Connect**.
2. Describe a simple check, such as “Check my Linux health” or “List running
   processes.”
3. Choose **Create task**.
4. Select the task and choose **Create plan**.
5. Read the proposed action and expected evidence carefully.
6. Choose **Approve & run check** only if the plan is exactly what you want.
7. Review the result and its Linux-environment scope.

JayAI does not run arbitrary shell commands, install software, delete files,
send messages, make purchases, or change system settings through this flow.
Pause blocks new actions. A check already admitted may finish. Cancel is
available for a task that has not completed.

## Stop and start again

Press `Ctrl+C` in the launcher terminal to stop JayAI. Start it again with the
same command. The profile UUID and database data remain; the dashboard key is
handled for the current run and must be entered again after a restart.

## Song Studio (optional)

Song Studio is separate from local health checks. It needs an OpenAI API key
in the launcher’s process environment and sends submitted song material to
OpenAI for processing. Do not use it for material you do not want sent to that
provider. Suno creation remains a manual step.

## If something goes wrong

- **Dashboard will not open:** confirm the launcher is still running and use
  `http://localhost:8000/`.
- **Invalid dashboard key:** use the key printed by the current launcher run;
  an old key is not expected to work.
- **Local model unavailable:** start Ollama and check `ollama list`.
- **Model missing:** run `ollama pull qwen2.5:0.5b`.
- **Database check failed:** verify PostgreSQL is running and the `JAYAI_DB_*`
  or `JAYAI_DATABASE_URL` settings are correct. Do not reset the database.
- **Low memory or disk:** check `free -h` and `df -h ~`; use the 0.5b model and
  avoid downloading larger models on a constrained Chromebook.

For the longer operational notes, see [Standalone setup](docs/STANDALONE.md),
[local AI](docs/AI.md), and [Chromebook scope](docs/CHROMEBOOK.md).

## Possible future addons

These are ideas and planned work, not features you can rely on in 0.25.0:

- **More read-only connectors:** carefully scoped email, browser, calendar, or
  document summaries with clear source labels.
- **Background queue support:** a supervised Redis worker for jobs that should
  wait safely in the background.
- **Better sign-in:** expiring, revocable sessions instead of the temporary
  development dashboard key.
- **Reviewable routines:** user-approved recurring suggestions that show their
  scope, schedule, and exact actions before anything can run.
- **Safe change recipes:** dry runs, exact target confirmation, rollback, and
  post-change checks for a small number of non-destructive operations.
- **Smarter learning:** optional use of saved preferences to improve plans,
  always keeping permissions and approval separate.

JayAI will not silently gain arbitrary shell commands, automatic purchases,
public posting, account changes, or unsupervised deletion. Any future feature
that could change something will need its own review and safety controls.
