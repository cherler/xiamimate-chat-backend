#!/usr/bin/env python3
"""Preview or clean placeholder/test users by email domain keywords.

Default behavior is read-only. Destructive actions require --execute.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_platform.chat_backend.infra.postgres import _postgres_conn, _run_pg_dict_query
from data_platform.chat_backend.infra.settings import OPENWEBUI_DB_PATH


DEFAULT_DOMAIN_KEYWORDS = ("local", "example", "test")


def _parse_keywords(value: str) -> list[str]:
    keywords = [item.strip().lower() for item in value.split(",") if item.strip()]
    return keywords or list(DEFAULT_DOMAIN_KEYWORDS)


def _email_domain(email: str) -> str:
    candidate = str(email or "").strip().lower()
    if "@" not in candidate:
        return ""
    return candidate.rsplit("@", 1)[-1]


def _matches_placeholder_domain(email: str, keywords: list[str]) -> bool:
    domain = _email_domain(email)
    return bool(domain and any(keyword in domain for keyword in keywords))


def _load_app_candidates(conn, keywords: list[str], limit: int) -> list[dict[str, Any]]:
    rows = _run_pg_dict_query(
        conn,
        """
        SELECT user_id, email, display_name, status, plan_tier, created_at, updated_at
        FROM app.app_user
        WHERE NULLIF(BTRIM(email), '') IS NOT NULL
          AND POSITION('@' IN email) > 1
        ORDER BY created_at DESC, user_id DESC
        LIMIT %s
        """,
        [max(1, int(limit))],
    )
    return [row for row in rows if _matches_placeholder_domain(str(row.get("email") or ""), keywords)]


def _resolve_openwebui_db_path() -> Path | None:
    configured = str(OPENWEBUI_DB_PATH or "").strip()
    if not configured:
        return None
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path if path.exists() else None


def _load_openwebui_candidates(keywords: list[str], limit: int) -> list[dict[str, Any]]:
    db_path = _resolve_openwebui_db_path()
    if db_path is None:
        return []
    conn = sqlite3.connect(str(db_path), timeout=5)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        rows = conn.execute(
            """
            SELECT auth.id AS user_id,
                   LOWER(auth.email) AS email,
                   COALESCE(user.name, user.email, auth.email) AS display_name,
                   auth.active AS active
            FROM auth
            LEFT JOIN user ON user.id = auth.id
            WHERE auth.email IS NOT NULL
            ORDER BY auth.id DESC
            LIMIT ?
            """,
            [max(1, int(limit))],
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows if _matches_placeholder_domain(str(row["email"] or ""), keywords)]


def _print_candidates(label: str, rows: list[dict[str, Any]], *, max_rows: int = 80) -> None:
    print(f"\n[{label}] matched_count={len(rows)}")
    for row in rows[:max_rows]:
        print(
            "\t".join(
                [
                    str(row.get("user_id") or ""),
                    str(row.get("email") or ""),
                    str(row.get("display_name") or ""),
                    str(row.get("status") if "status" in row else row.get("active")),
                    str(row.get("created_at") or ""),
                ]
            )
        )
    if len(rows) > max_rows:
        print(f"... {len(rows) - max_rows} more rows omitted")


def _disable_app_users(conn, user_ids: list[str]) -> list[dict[str, Any]]:
    if not user_ids:
        return []
    return _run_pg_dict_query(
        conn,
        """
        UPDATE app.app_user
        SET status = 'disabled', updated_at = NOW()
        WHERE user_id = ANY(%s)
        RETURNING user_id, email, display_name, status, updated_at
        """,
        [user_ids],
    )


def _delete_app_shadow_users(conn, user_ids: list[str]) -> dict[str, Any]:
    if not user_ids:
        return {"usage_events_deleted": 0, "chat_sessions_deleted": 0, "app_users_deleted": []}
    usage_events = _run_pg_dict_query(
        conn,
        "DELETE FROM app.usage_event WHERE user_id = ANY(%s) RETURNING event_id",
        [user_ids],
    )
    chat_sessions = _run_pg_dict_query(
        conn,
        "DELETE FROM app.chat_session WHERE user_id = ANY(%s) RETURNING session_id",
        [user_ids],
    )
    deleted_users = _run_pg_dict_query(
        conn,
        """
        DELETE FROM app.app_user
        WHERE user_id = ANY(%s)
        RETURNING user_id, email, display_name, status
        """,
        [user_ids],
    )
    return {
        "usage_events_deleted": len(usage_events),
        "chat_sessions_deleted": len(chat_sessions),
        "app_users_deleted": deleted_users,
    }


def _deactivate_openwebui_users(emails: list[str]) -> list[dict[str, Any]]:
    db_path = _resolve_openwebui_db_path()
    if db_path is None or not emails:
        return []
    normalized_emails = sorted({str(email or "").strip().lower() for email in emails if str(email or "").strip()})
    conn = sqlite3.connect(str(db_path), timeout=5)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        placeholders = ", ".join(["?"] * len(normalized_emails))
        rows = conn.execute(
            f"""
            SELECT id AS user_id, LOWER(email) AS email, active
            FROM auth
            WHERE LOWER(email) IN ({placeholders})
            """,
            normalized_emails,
        ).fetchall()
        conn.execute(
            f"UPDATE auth SET active = 0 WHERE LOWER(email) IN ({placeholders})",
            normalized_emails,
        )
        conn.commit()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean placeholder users by email domain keywords.")
    parser.add_argument("--keywords", default=",".join(DEFAULT_DOMAIN_KEYWORDS), help="Comma-separated domain keywords. Default: local,example,test")
    parser.add_argument("--limit", type=int, default=5000, help="Maximum app/openwebui users to scan before Python filtering.")
    parser.add_argument("--action", choices=["preview", "disable-app", "delete-app-shadow"], default="preview")
    parser.add_argument("--deactivate-openwebui", action="store_true", help="Also set Open WebUI auth.active=0 for matched emails when --execute is present.")
    parser.add_argument("--execute", action="store_true", help="Actually perform the selected action. Omit for dry-run preview.")
    args = parser.parse_args()

    keywords = _parse_keywords(args.keywords)
    print(f"domain_keywords={','.join(keywords)}")
    with _postgres_conn() as conn:
        app_candidates = _load_app_candidates(conn, keywords, args.limit)
        openwebui_candidates = _load_openwebui_candidates(keywords, args.limit)
        _print_candidates("app.app_user", app_candidates)
        _print_candidates("openwebui.auth", openwebui_candidates)

        if args.action == "preview" or not args.execute:
            if args.action != "preview":
                print("\ndry_run=true; add --execute to apply the selected action")
            return 0

        user_ids = [str(row.get("user_id") or "").strip() for row in app_candidates if str(row.get("user_id") or "").strip()]
        emails = [str(row.get("email") or "").strip().lower() for row in app_candidates if str(row.get("email") or "").strip()]
        if args.action == "disable-app":
            updated_users = _disable_app_users(conn, user_ids)
            print(f"\ndisabled_app_users={len(updated_users)}")
        elif args.action == "delete-app-shadow":
            result = _delete_app_shadow_users(conn, user_ids)
            print(f"\nusage_events_deleted={result['usage_events_deleted']}")
            print(f"chat_sessions_deleted={result['chat_sessions_deleted']}")
            print(f"app_users_deleted={len(result['app_users_deleted'])}")

    if args.execute and args.deactivate_openwebui:
        deactivated_users = _deactivate_openwebui_users(emails)
        print(f"openwebui_users_deactivated={len(deactivated_users)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())