#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python="$project_root/.venv/bin/python"
if [[ ! -x "$python" ]]; then
  printf 'JayAI Python environment not found at %s. Follow docs/STANDALONE.md first.\n' "$python" >&2
  exit 1
fi

pg_bindir="$(pg_config --bindir 2>/dev/null || true)"
initdb_bin="${pg_bindir:+$pg_bindir/initdb}"
pg_ctl_bin="${pg_bindir:+$pg_bindir/pg_ctl}"
pg_isready_bin="${pg_bindir:+$pg_bindir/pg_isready}"
[[ -x "$initdb_bin" ]] || initdb_bin="$(command -v initdb || true)"
[[ -x "$pg_ctl_bin" ]] || pg_ctl_bin="$(command -v pg_ctl || true)"
[[ -x "$pg_isready_bin" ]] || pg_isready_bin="$(command -v pg_isready || true)"

if [[ -z "${JAYAI_DATABASE_URL:-}" && -z "${JAYAI_DB_PASSWORD:-}" ]]; then
  # Chromebook containers often have PostgreSQL tools but no system service.
  # Use a real user-owned cluster in that case; no sudo or mock backend.
  local_pg_state="${JAYAI_LOCAL_PGDATA:-${XDG_STATE_HOME:-$HOME/.local/state}/JayAI/postgres}"
  local_pg_socket="${JAYAI_LOCAL_PGSOCKET:-${XDG_STATE_HOME:-$HOME/.local/state}/JayAI/postgres-socket}"
  local_pg_port="${JAYAI_LOCAL_PGPORT:-55432}"
  if [[ -x "$initdb_bin" && -x "$pg_ctl_bin" && -x "$pg_isready_bin" ]] &&
     command -v psql >/dev/null 2>&1 &&
     command -v createdb >/dev/null 2>&1; then
    umask 077
    mkdir -p "$local_pg_socket"
    if [[ ! -f "$local_pg_state/PG_VERSION" ]]; then
      mkdir -p "$local_pg_state"
      "$initdb_bin" -D "$local_pg_state" --auth-local=trust --auth-host=reject --username="${USER:-$(id -un)}" \
        >"${local_pg_state}.init.log"
    fi
    if ! "$pg_isready_bin" -h "$local_pg_socket" -p "$local_pg_port" >/dev/null 2>&1; then
      "$pg_ctl_bin" -D "$local_pg_state" -o "-p $local_pg_port -k $local_pg_socket -h ''" \
        -l "${local_pg_state}.log" start >/dev/null
    fi
    if ! "$pg_isready_bin" -h "$local_pg_socket" -p "$local_pg_port" >/dev/null 2>&1; then
      printf 'JayAI local PostgreSQL did not become ready. See %s.log\n' "$local_pg_state" >&2
      exit 1
    fi
    if ! database_exists="$(psql -X -h "$local_pg_socket" -p "$local_pg_port" \
        -d postgres -U "${USER:-$(id -un)}" -v ON_ERROR_STOP=1 \
        -Atc "SELECT 1 FROM pg_database WHERE datname='jayai'")"; then
      printf 'Could not inspect existing PostgreSQL databases; startup stopped without creating a database.\n' >&2
      exit 1
    fi
    if [[ -z "$database_exists" ]]; then
      createdb -h "$local_pg_socket" -p "$local_pg_port" -U "${USER:-$(id -un)}" jayai
    elif [[ "$database_exists" != "1" ]]; then
      printf 'Unexpected PostgreSQL inspection result; startup stopped without creating a database.\n' >&2
      exit 1
    fi
    export JAYAI_DB_HOST="$local_pg_socket"
    export JAYAI_DB_PORT="$local_pg_port"
    export JAYAI_DB_NAME="jayai"
    export JAYAI_DB_USER="${USER:-$(id -un)}"
  else
    read -r -s -p 'JayAI PostgreSQL password: ' JAYAI_DB_PASSWORD
    printf '\n'
    export JAYAI_DB_PASSWORD
    export JAYAI_DB_HOST="${JAYAI_DB_HOST:-127.0.0.1}"
    export JAYAI_DB_PORT="${JAYAI_DB_PORT:-5432}"
    export JAYAI_DB_NAME="${JAYAI_DB_NAME:-jayai}"
    export JAYAI_DB_USER="${JAYAI_DB_USER:-jayai}"
  fi
fi

port="${JAYAI_PORT:-8000}"
if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 1024 || port > 65535 )); then
  printf 'JAYAI_PORT must be an integer from 1024 to 65535.\n' >&2
  exit 2
fi

"$python" -m jayai db-check
"$python" -m jayai migrate

if [[ -z "${JAYAI_DEV_USER_ID:-}" ]]; then
  state_root="${XDG_STATE_HOME:-$HOME/.local/state}/JayAI"
  umask 077
  mkdir -p "$state_root"
  user_file="$state_root/development-user-id"
  if [[ -f "$user_file" ]]; then
    JAYAI_DEV_USER_ID="$(<"$user_file")"
    if [[ ! "$JAYAI_DEV_USER_ID" =~ ^[0-9a-fA-F-]{36}$ ]]; then
      printf 'Stored JayAI development user ID is invalid: %s\n' "$user_file" >&2
      exit 1
    fi
  else
    created="$("$python" -m jayai create-dev-user)"
    JAYAI_DEV_USER_ID="${created#Development user ID: }"
    if [[ ! "$JAYAI_DEV_USER_ID" =~ ^[0-9a-fA-F-]{36}$ ]]; then
      printf 'JayAI did not return a valid development user ID.\n' >&2
      exit 1
    fi
    printf '%s' "$JAYAI_DEV_USER_ID" > "$user_file"
    chmod 600 "$user_file"
  fi
  export JAYAI_DEV_USER_ID
fi

key_dir="${XDG_STATE_HOME:-$HOME/.local/state}/JayAI"
key_file="$key_dir/dashboard-key"
umask 077
mkdir -p "$key_dir"

if [[ -L "$key_file" ]]; then
  printf 'Dashboard key path must not be a symlink: %s\n' "$key_file" >&2
  exit 1
fi
if [[ -f "$key_file" ]]; then
  JAYAI_DEV_API_KEY="$(<"$key_file")"
elif [[ -z "${JAYAI_DEV_API_KEY:-}" ]]; then
  JAYAI_DEV_API_KEY="$("$python" -c 'import secrets; print(secrets.token_hex(32))')"
fi

if [[ ! "$JAYAI_DEV_API_KEY" =~ ^[0-9a-f]{64}$ ]]; then
  printf 'Invalid dashboard key; expected 64 lowercase hexadecimal characters.\n' >&2
  exit 1
fi

key_tmp="$(mktemp "$key_dir/.dashboard-key.XXXXXX")"
trap 'rm -f -- "$key_tmp"' EXIT
printf '%s' "$JAYAI_DEV_API_KEY" > "$key_tmp"
chmod 600 "$key_tmp"
mv -f -- "$key_tmp" "$key_file"
trap - EXIT
export JAYAI_DEV_API_KEY
printf 'Dashboard key saved at: %s\n' "$key_file"

export JAYAI_ENV=development
export JAYAI_LOCAL_MODEL="${JAYAI_LOCAL_MODEL:-qwen2.5:0.5b}"
printf 'JayAI is starting on http://127.0.0.1:%s/\n' "$port"
printf 'Keep this terminal open. Stop JayAI with Ctrl+C.\n'
exec "$python" -m uvicorn jayai.main:app --host 127.0.0.1 --port "$port" --no-access-log
