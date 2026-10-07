# Chromebook Linux scope and setup

JayAI can run inside the Chromebook Linux development environment (Crostini), or Chrome can display the Windows-hosted dashboard through the restricted SSH tunnel described below. These are two different setups.

## Linux container scope

A JayAI instance running in Crostini sees Linux-container storage, `~/Downloads`, and Linux processes. It cannot inspect ChromeOS updates, the ChromeOS host, or files that were not explicitly shared with Linux. ChromeOS shared folders are accessible to Linux applications after the user shares them. No feature in this build grants itself host permissions.

When running JayAI inside Linux, the browser URL is `http://localhost:8000/`. ChromeOS forwards Linux localhost ports to Chrome. The local model should be `qwen2.5:0.5b` on a constrained Chromebook; check free memory and disk before installing other models. Full setup and launch commands are in `STANDALONE.md`.

## Viewing Windows-hosted JayAI in Chrome

Keep the Windows API bound to `127.0.0.1:8000`. Start Windows OpenSSH Server, add `permitopen="127.0.0.1:8000"` to the Chromebook key's existing restricted destination list, and retain its other restrictions and loopback destinations. A missing allowlist entry produces `channel open failed: administratively prohibited` even when SSH authentication succeeds.

Use the actual current Windows IPv4 address in this Chromebook Linux Terminal command. The Windows PC reported `192.168.229.77` during the 0.24.2 setup:

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

Keep the SSH terminal open. In Chrome, open `http://localhost:8000/` and use the dashboard key printed by the Windows launcher. Do not publish port 8000 on the Wi-Fi network. If port 8000 is already bound in Linux, stop the older tunnel before retrying. See the troubleshooting table in `STANDALONE.md`.
