#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHAT_BACKEND_ENV_FILE="${XIAMIMATE_CHAT_BACKEND_ENV_FILE:-$ROOT_DIR/.env}"

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