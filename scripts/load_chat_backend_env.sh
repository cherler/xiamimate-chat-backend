#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHAT_BACKEND_ENV_FILE="${XIAMIMATE_CHAT_BACKEND_ENV_FILE:-$ROOT_DIR/.env}"

CHAT_BACKEND_ENV_OVERRIDE_NAMES=(
    XIAMIMATE_PYTHON_BIN
    PG_HOST
    PG_PORT
    PG_DB
    PG_USER
    PG_PASSWORD
    PGPASSWORD
    CHAT_BACKEND_HOST
    CHAT_BACKEND_PORT
    XIAMIMATE_THEME_API_BASE_URL
)
CHAT_BACKEND_ENV_OVERRIDE_PRESENT=()
CHAT_BACKEND_ENV_OVERRIDE_VALUES=()

for chat_backend_env_var_name in "${CHAT_BACKEND_ENV_OVERRIDE_NAMES[@]}"; do
    if [[ -n "${!chat_backend_env_var_name+x}" ]]; then
        CHAT_BACKEND_ENV_OVERRIDE_PRESENT+=(1)
        CHAT_BACKEND_ENV_OVERRIDE_VALUES+=("${!chat_backend_env_var_name}")
    else
        CHAT_BACKEND_ENV_OVERRIDE_PRESENT+=(0)
        CHAT_BACKEND_ENV_OVERRIDE_VALUES+=("")
    fi
done

set_default_if_missing() {
    local var_name="$1"
    local candidate="$2"

    if [[ -n "${!var_name:-}" ]]; then
        return 0
    fi
    if [[ -z "$candidate" ]]; then
        return 0
    fi

    printf -v "$var_name" '%s' "$candidate"
    export "$var_name"
}

if [[ -f "$CHAT_BACKEND_ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$CHAT_BACKEND_ENV_FILE"
    set +a
fi

for chat_backend_env_var_index in "${!CHAT_BACKEND_ENV_OVERRIDE_NAMES[@]}"; do
    if [[ "${CHAT_BACKEND_ENV_OVERRIDE_PRESENT[$chat_backend_env_var_index]}" == "1" ]]; then
        printf -v "${CHAT_BACKEND_ENV_OVERRIDE_NAMES[$chat_backend_env_var_index]}" '%s' "${CHAT_BACKEND_ENV_OVERRIDE_VALUES[$chat_backend_env_var_index]}"
        export "${CHAT_BACKEND_ENV_OVERRIDE_NAMES[$chat_backend_env_var_index]}"
    fi
done

unset chat_backend_env_var_index chat_backend_env_var_name
unset CHAT_BACKEND_ENV_OVERRIDE_NAMES CHAT_BACKEND_ENV_OVERRIDE_PRESENT CHAT_BACKEND_ENV_OVERRIDE_VALUES

if [[ -z "${PG_PASSWORD:-}" && -n "${PGPASSWORD:-}" ]]; then
    PG_PASSWORD="$PGPASSWORD"
fi

if [[ -z "${PGPASSWORD:-}" && -n "${PG_PASSWORD:-}" ]]; then
    PGPASSWORD="$PG_PASSWORD"
fi

if [[ -z "${XIAMIMATE_RUNTIME_ROOT:-}" ]]; then
    default_runtime_root="$(cd "$ROOT_DIR/../xiamimate-runtime" 2>/dev/null && pwd || true)"
    if [[ -n "$default_runtime_root" && -d "$default_runtime_root" ]]; then
        XIAMIMATE_RUNTIME_ROOT="$default_runtime_root"
    fi
fi

if [[ -n "${XIAMIMATE_RUNTIME_ROOT:-}" ]]; then
    set_default_if_missing "XIAMIMATE_PYTHON_BIN" "$XIAMIMATE_RUNTIME_ROOT/python/.venv/bin/python"
fi

if [[ -z "${XIAMIMATE_BASELINE_ROOT:-}" ]]; then
    default_baseline_root="$(cd "$ROOT_DIR/../xiamimate" 2>/dev/null && pwd || true)"
    if [[ -n "$default_baseline_root" && -d "$default_baseline_root" ]]; then
        XIAMIMATE_BASELINE_ROOT="$default_baseline_root"
    fi
fi

if [[ -n "${XIAMIMATE_BASELINE_ROOT:-}" ]]; then
    set_default_if_missing "XIAMIMATE_PYTHON_BIN" "$XIAMIMATE_BASELINE_ROOT/.venv/bin/python"
fi

set_default_if_missing "XIAMIMATE_THEME_API_BASE_URL" "http://127.0.0.1:18100"

export XIAMIMATE_RUNTIME_ROOT
export XIAMIMATE_BASELINE_ROOT
export PG_HOST
export PG_PORT
export PG_DB
export PG_USER
export PG_PASSWORD
export PGPASSWORD