#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=scripts/load_chat_backend_env.sh
source "$PROJECT_ROOT/scripts/load_chat_backend_env.sh"
PROJECT_PYTHON="${XIAMIMATE_PYTHON_BIN:-$PROJECT_ROOT/.venv/bin/python}"
API_BASE_URL="${CHAT_BACKEND_BASE_URL:-http://127.0.0.1:${CHAT_BACKEND_PORT:-8200}}"
USER_ID="${CHAT_BACKEND_USER_ID:-demo-user}"
USER_EMAIL="${CHAT_BACKEND_USER_EMAIL:-demo-user@local}"
USER_NAME="${CHAT_BACKEND_USER_NAME:-Demo User}"
RESPONSE_SCHEMA="xiamimate_chat_backend_v1"

if [[ ! -x "$PROJECT_PYTHON" ]]; then
  echo "python not found: $PROJECT_PYTHON"
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

curl_json() {
  local method="$1"
  local url="$2"
  local payload_file="$3"
  local output_file="$4"

  if [[ -n "$payload_file" ]]; then
    curl -sS -X "$method" "$url" \
      -H 'Content-Type: application/json' \
      -H "X-User-Id: $USER_ID" \
      -H "X-User-Email: $USER_EMAIL" \
      -H "X-User-Name: $USER_NAME" \
      --data @"$payload_file" \
      > "$output_file"
  else
    curl -sS -X "$method" "$url" \
      -H "X-User-Id: $USER_ID" \
      -H "X-User-Email: $USER_EMAIL" \
      -H "X-User-Name: $USER_NAME" \
      > "$output_file"
  fi
}

pretty_print() {
  local label="$1"
  local json_file="$2"
  echo "===== $label ====="
  "$PROJECT_PYTHON" -m json.tool "$json_file"
  echo
}

validate_response() {
  local label="$1"
  local json_file="$2"
  local endpoint="$3"

  "$PROJECT_PYTHON" - "$label" "$json_file" "$endpoint" "$RESPONSE_SCHEMA" <<'PY'
import json
import sys

label, path, endpoint, schema = sys.argv[1:5]
with open(path, 'r', encoding='utf-8') as handle:
    payload = json.load(handle)

if payload.get('success') is not True:
    raise SystemExit(f'{label}: success=false -> {payload}')
if payload.get('code') != 'OK':
    raise SystemExit(f'{label}: unexpected code -> {payload.get("code")}')
meta = payload.get('meta') or {}
if meta.get('endpoint') != endpoint:
    raise SystemExit(f'{label}: unexpected endpoint -> {meta.get("endpoint")}')
if meta.get('response_schema') != schema:
    raise SystemExit(f'{label}: unexpected response_schema -> {meta.get("response_schema")}')
PY
}

cat > "$TMP_DIR/create-session.json" <<EOF
{
  "title": "Demo Theme Chat",
  "target_platform": "tiktok",
  "target_market": "US",
  "validation_marketplace": "US"
}
EOF

curl_json GET "$API_BASE_URL/health" "" "$TMP_DIR/health.out.json"
curl_json POST "$API_BASE_URL/v1/chat/sessions" "$TMP_DIR/create-session.json" "$TMP_DIR/create-session.out.json"

SESSION_ID="$($PROJECT_PYTHON - "$TMP_DIR/create-session.out.json" <<'PY'
import json
import sys
with open(sys.argv[1], 'r', encoding='utf-8') as handle:
    payload = json.load(handle)
print(payload['data']['session']['session_id'])
PY
)"

cat > "$TMP_DIR/message.json" <<EOF
{
  "content": "请分析 digital photo frame 在 TikTok US 的机会。",
  "role": "user",
  "message_type": "theme_query",
  "metadata": {
    "source": "smoke_test"
  }
}
EOF

curl_json POST "$API_BASE_URL/v1/chat/sessions/$SESSION_ID/messages" "$TMP_DIR/message.json" "$TMP_DIR/message.out.json"

MESSAGE_ID="$($PROJECT_PYTHON - "$TMP_DIR/message.out.json" <<'PY'
import json
import sys
with open(sys.argv[1], 'r', encoding='utf-8') as handle:
    payload = json.load(handle)
print(payload['data']['message']['message_id'])
PY
)"

cat > "$TMP_DIR/run.json" <<EOF
{
  "session_id": "$SESSION_ID",
  "message_id": "$MESSAGE_ID",
  "product_query": "digital photo frame",
  "analysis_goal": "评估 TikTok US 机会",
  "input_payload": {
    "target_platform": "tiktok",
    "target_market": "US",
    "validation_marketplace": "US"
  }
}
EOF

curl_json POST "$API_BASE_URL/v1/analysis/theme-runs" "$TMP_DIR/run.json" "$TMP_DIR/run.out.json"

RUN_ID="$($PROJECT_PYTHON - "$TMP_DIR/run.out.json" <<'PY'
import json
import sys
with open(sys.argv[1], 'r', encoding='utf-8') as handle:
    payload = json.load(handle)
print(payload['data']['run']['run_id'])
PY
)"

cat > "$TMP_DIR/callback.json" <<EOF
{
  "run_id": "$RUN_ID",
  "status": "completed",
  "dify_run_id": "dify_demo_run_001",
  "final_answer_text": "主题有机会，但竞争强，建议先聚焦礼品和家庭场景。",
  "assistant_message": "综合 theme_api 与知识库结果，这个主题在 TikTok US 有切入空间，但需要避开泛电子配件竞争。",
  "artifacts": [
    {
      "artifact_type": "theme_summary",
      "artifact_key": "summary",
      "artifact_payload": {
        "opportunity": "medium",
        "risk": "competition_high"
      }
    }
  ],
  "usage_events": [
    {
      "event_type": "theme_run_completed",
      "units": 1,
      "meta": {
        "source": "smoke_test"
      }
    }
  ]
}
EOF

curl_json POST "$API_BASE_URL/internal/dify/run-callback" "$TMP_DIR/callback.json" "$TMP_DIR/callback.out.json"
curl_json GET "$API_BASE_URL/v1/chat/sessions/$SESSION_ID" "" "$TMP_DIR/session.out.json"
curl_json GET "$API_BASE_URL/v1/chat/sessions/$SESSION_ID/messages" "" "$TMP_DIR/messages.out.json"
curl_json GET "$API_BASE_URL/v1/analysis/theme-runs/$RUN_ID" "" "$TMP_DIR/run-detail.out.json"
curl_json GET "$API_BASE_URL/v1/analysis/theme-runs/$RUN_ID/artifacts" "" "$TMP_DIR/artifacts.out.json"
curl_json GET "$API_BASE_URL/v1/me" "" "$TMP_DIR/me.out.json"
curl_json GET "$API_BASE_URL/v1/me/account-overview" "" "$TMP_DIR/account-overview.out.json"
curl_json GET "$API_BASE_URL/v1/me/usage" "" "$TMP_DIR/usage.out.json"
curl_json GET "$API_BASE_URL/v1/me/plan" "" "$TMP_DIR/plan.out.json"

cat > "$TMP_DIR/close.json" <<EOF
{}
EOF

curl_json POST "$API_BASE_URL/v1/chat/sessions/$SESSION_ID/close" "$TMP_DIR/close.json" "$TMP_DIR/close.out.json"

validate_response "health" "$TMP_DIR/health.out.json" "/health"
validate_response "create-session" "$TMP_DIR/create-session.out.json" "/v1/chat/sessions"
validate_response "create-message" "$TMP_DIR/message.out.json" "/v1/chat/sessions/$SESSION_ID/messages"
validate_response "create-run" "$TMP_DIR/run.out.json" "/v1/analysis/theme-runs"
validate_response "callback" "$TMP_DIR/callback.out.json" "/internal/dify/run-callback"
validate_response "get-session" "$TMP_DIR/session.out.json" "/v1/chat/sessions/$SESSION_ID"
validate_response "list-messages" "$TMP_DIR/messages.out.json" "/v1/chat/sessions/$SESSION_ID/messages"
validate_response "get-run" "$TMP_DIR/run-detail.out.json" "/v1/analysis/theme-runs/$RUN_ID"
validate_response "get-artifacts" "$TMP_DIR/artifacts.out.json" "/v1/analysis/theme-runs/$RUN_ID/artifacts"
validate_response "me" "$TMP_DIR/me.out.json" "/v1/me"
validate_response "account-overview" "$TMP_DIR/account-overview.out.json" "/v1/me/account-overview"
validate_response "usage" "$TMP_DIR/usage.out.json" "/v1/me/usage"
validate_response "plan" "$TMP_DIR/plan.out.json" "/v1/me/plan"
validate_response "close-session" "$TMP_DIR/close.out.json" "/v1/chat/sessions/$SESSION_ID/close"

pretty_print "health" "$TMP_DIR/health.out.json"
pretty_print "create-session" "$TMP_DIR/create-session.out.json"
pretty_print "create-message" "$TMP_DIR/message.out.json"
pretty_print "create-run" "$TMP_DIR/run.out.json"
pretty_print "callback" "$TMP_DIR/callback.out.json"
pretty_print "get-session" "$TMP_DIR/session.out.json"
pretty_print "list-messages" "$TMP_DIR/messages.out.json"
pretty_print "get-run" "$TMP_DIR/run-detail.out.json"
pretty_print "get-artifacts" "$TMP_DIR/artifacts.out.json"
pretty_print "me" "$TMP_DIR/me.out.json"
pretty_print "account-overview" "$TMP_DIR/account-overview.out.json"
pretty_print "usage" "$TMP_DIR/usage.out.json"
pretty_print "plan" "$TMP_DIR/plan.out.json"
pretty_print "close-session" "$TMP_DIR/close.out.json"