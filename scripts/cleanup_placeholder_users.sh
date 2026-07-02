#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/load_chat_backend_env.sh
source "$ROOT_DIR/scripts/load_chat_backend_env.sh"

exec "$XIAMIMATE_PYTHON_BIN" "$ROOT_DIR/scripts/cleanup_placeholder_users.py" "$@"