# Chromebook Linux scope

JayAI runs inside the Chromebook Linux development environment (Crostini). It
does not inspect the ChromeOS host and does not provide a Windows companion.

Install the Linux dependencies described in `STANDALONE.md`, start Ollama on
the Linux container, and follow [Quick start](../QUICKSTART.md). To launch
from the project root:

```bash
bash scripts/start-jayai.sh
```

Open `http://localhost:8000/` in Chrome. Keep the launcher terminal open and
stop it with Ctrl+C. The API remains bound to loopback.
