#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

printf 'JayAI Chromebook setup\n\n'

if ! command -v python3 >/dev/null 2>&1; then
  printf 'Missing Python 3. Install it with: sudo apt update && sudo apt install python3 python3-venv python3-pip\n' >&2
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  printf 'Creating .venv...\n'
  python3 -m venv .venv
fi

printf 'Installing JayAI dependencies...\n'
.venv/bin/python -m pip install -e '.[test]'

if ! command -v pg_config >/dev/null 2>&1 || ! command -v psql >/dev/null 2>&1; then
  printf '\nMissing PostgreSQL tools. Install them with:\n  sudo apt update && sudo apt install postgresql postgresql-client\n' >&2
  exit 1
fi

if ! command -v ollama >/dev/null 2>&1; then
  printf '\nMissing Ollama. Install it using the official Linux instructions, then run:\n  ollama pull qwen2.5:0.5b\n' >&2
  exit 1
fi

if ! ollama list 2>/dev/null | awk 'NR > 1 {print $1}' | grep -qx 'qwen2.5:0.5b'; then
  printf '\nOllama is installed, but qwen2.5:0.5b is missing. Run:\n  ollama pull qwen2.5:0.5b\n' >&2
  exit 1
fi

printf '\nSetup checks passed. Start JayAI with:\n  bash scripts/start-jayai.sh\n'
