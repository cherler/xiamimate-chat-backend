#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=scripts/load_chat_backend_env.sh
source "$PROJECT_ROOT/scripts/load_chat_backend_env.sh"

PROJECT_PYTHON="${XIAMIMATE_PYTHON_BIN:-$PROJECT_ROOT/.venv/bin/python}"
API_BASE_URL="${CHAT_BACKEND_BASE_URL:-http://127.0.0.1:${CHAT_BACKEND_PORT:-8200}}"
QUERY="${ONEBOUND_1688_SMOKE_QUERY:-portable blender}"
MARKETPLACE="${ONEBOUND_1688_SMOKE_MARKETPLACE:-US}"
MODE="direct"
EXPECTATION="auto"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/smoke_test_onebound_1688_sourcing.sh [--no-key|--live] [--http]

Examples:
  bash scripts/smoke_test_onebound_1688_sourcing.sh --no-key
  ONEBOUND_API_KEY=xxx ONEBOUND_API_SECRET=yyy bash scripts/smoke_test_onebound_1688_sourcing.sh --live
  CHAT_BACKEND_SERVICE_SECRET=dev-secret bash scripts/smoke_test_onebound_1688_sourcing.sh --http

Options:
  --no-key  Clear Onebound credentials in this process and expect missing_credentials.
  --live    Require ONEBOUND_API_KEY and ONEBOUND_API_SECRET and call Onebound in direct mode.
  --http    Call the running chat-backend internal route instead of importing the service directly.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-key)
      EXPECTATION="missing_credentials"
      export ONEBOUND_API_KEY=""
      export ONEBOUND_API_SECRET=""
      ;;
    --live)
      EXPECTATION="live"
      ;;
    --http)
      MODE="http"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ ! -x "$PROJECT_PYTHON" ]]; then
  echo "python not found: $PROJECT_PYTHON" >&2
  exit 1
fi

if [[ "$EXPECTATION" == "live" && ( -z "${ONEBOUND_API_KEY:-}" || -z "${ONEBOUND_API_SECRET:-}" ) ]]; then
  echo "--live requires ONEBOUND_API_KEY and ONEBOUND_API_SECRET" >&2
  exit 2
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/request.json" <<EOF
{
  "query": "$QUERY",
  "marketplace": "$MARKETPLACE",
  "supplier_queries": ["便携式榨汁机"],
  "limit": 5,
  "seller_scope": "cross_border_sme_v1",
  "force_refresh": true,
  "allow_realtime": true,
  "cost_assumptions": {
    "fx_cny_usd": 7.25,
    "international_shipping_usd_per_unit": 2.0
  }
}
EOF

run_direct() {
  "$PROJECT_PYTHON" - "$TMP_DIR/request.json" > "$TMP_DIR/response.json" <<'PY'
import json
import sys

from data_platform.chat_backend.domains.onebound_1688_sourcing.service import run_onebound_1688_supplier_discovery

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)

result = run_onebound_1688_supplier_discovery(payload)
print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
PY
}

run_http() {
  if [[ -z "${CHAT_BACKEND_SERVICE_SECRET:-}" ]]; then
    echo "--http requires CHAT_BACKEND_SERVICE_SECRET in this shell and in the running chat-backend process" >&2
    exit 2
  fi
  curl -sS -X POST "$API_BASE_URL/internal/provider/sourcing/1688/supplier-discovery" \
    -H 'Content-Type: application/json' \
    -H "X-Internal-Service-Secret: $CHAT_BACKEND_SERVICE_SECRET" \
    -H 'X-Internal-Service-Name: onebound-1688-smoke-test' \
    --data @"$TMP_DIR/request.json" \
    > "$TMP_DIR/http-response.json"

  "$PROJECT_PYTHON" - "$TMP_DIR/http-response.json" > "$TMP_DIR/response.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)
if payload.get("success") is not True:
    raise SystemExit(f"chat-backend response is not successful: {payload}")
print(json.dumps(payload.get("data") or {}, ensure_ascii=False, indent=2, sort_keys=True))
PY
}

if [[ "$MODE" == "http" ]]; then
  run_http
else
  run_direct
fi

"$PROJECT_PYTHON" - "$TMP_DIR/response.json" "$EXPECTATION" <<'PY'
import json
import sys

path, expectation = sys.argv[1:3]
with open(path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)

if payload.get("capability") != "onebound_1688_supplier_discovery":
    raise SystemExit(f"unexpected capability: {payload.get('capability')}")
status = ((payload.get("degradation") or {}).get("status") or "").strip()
if expectation == "missing_credentials" and status != "missing_credentials":
    raise SystemExit(f"expected missing_credentials, got {status}: {payload}")
if expectation == "live" and status in {"missing_credentials", "disabled", "skipped"}:
    raise SystemExit(f"expected live request path, got {status}: {payload}")
if not payload.get("result_text"):
    raise SystemExit("missing result_text")
print(f"status={status or 'unknown'} endpoints={((payload.get('source_meta') or {}).get('endpoint_count'))}")
PY

"$PROJECT_PYTHON" -m json.tool "$TMP_DIR/response.json"