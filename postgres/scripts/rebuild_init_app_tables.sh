#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_FILE="$ROOT_DIR/init_app_tables.sql"
FRAGMENTS=(
  "$ROOT_DIR/migrations/app/001_create_app_schema.sql"
  "$ROOT_DIR/migrations/app/010_app_business_tables.sql"
  "$ROOT_DIR/migrations/app/020_app_indexes.sql"
)

for fragment in "${FRAGMENTS[@]}"; do
  if [[ ! -f "$fragment" ]]; then
    echo "missing fragment: $fragment" >&2
    exit 1
  fi
done

{
  printf '%s\n\n' '-- ============================================================'
  printf '%s\n' '-- app compatibility bootstrap: rebuild from postgres/migrations/app/*'
  printf '%s\n' '-- do not hand-edit this file; edit fragments then rerun rebuild'
  printf '%s\n' '-- ============================================================'
  printf '\n'

  for fragment in "${FRAGMENTS[@]}"; do
    relative_fragment="${fragment#"$ROOT_DIR/"}"
    printf '%s\n' "-- >>> BEGIN ${relative_fragment}"
    cat "$fragment"
    printf '\n%s\n\n' "-- <<< END ${relative_fragment}"
  done
} > "$OUTPUT_FILE"

echo "rebuilt $OUTPUT_FILE"