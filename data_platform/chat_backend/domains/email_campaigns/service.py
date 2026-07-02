"""Email campaign domain — admin-selected one-to-one mailing."""
from __future__ import annotations

import html
from typing import Any

try:
    import psycopg2.extras
except ImportError:
    pass

from data_platform.chat_backend.infra.settings import _generate_id, _send_email_message
from data_platform.chat_backend.infra.postgres import _fetch_optional_one, _run_pg_dict_query


_CAMPAIGN_STATUSES = {"draft", "sending", "sent", "partial_failed", "failed"}


def _normalize_campaign_status(value: str) -> str:
    normalized = str(value or "draft").strip().lower() or "draft"
    return normalized if normalized in _CAMPAIGN_STATUSES else "draft"


def _normalize_user_ids(user_ids: list[str] | None, *, max_count: int = 1000) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for user_id in user_ids or []:
        candidate = str(user_id or "").strip()
        if not candidate or candidate in seen:
            continue
        normalized.append(candidate)
        seen.add(candidate)
        if len(normalized) >= max_count:
            break
    return normalized


def _campaign_json(value: Any) -> Any:
    return psycopg2.extras.Json(value)


def _list_email_campaign_recipients(
    conn,
    *,
    query: str = "",
    status: str | None = "active",
    email_verified: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit), 200))
    normalized_offset = max(0, int(offset))
    where_clauses = ["NULLIF(BTRIM(u.email), '') IS NOT NULL", "POSITION('@' IN u.email) > 1"]
    params: list[Any] = []
    normalized_status = str(status or "").strip().lower()
    if normalized_status and normalized_status != "all":
        where_clauses.append("u.status = %s")
        params.append(normalized_status)
    if email_verified == "verified":
        where_clauses.append("u.email_verified_at IS NOT NULL")
    elif email_verified == "unverified":
        where_clauses.append("u.email_verified_at IS NULL")
    normalized_query = str(query or "").strip()
    if normalized_query:
        like_query = f"%{normalized_query}%"
        where_clauses.append("(u.user_id ILIKE %s OR u.email ILIKE %s OR u.display_name ILIKE %s)")
        params.extend([like_query, like_query, like_query])
    where_sql = "WHERE " + " AND ".join(where_clauses)

    total_row = _fetch_optional_one(conn, f"SELECT COUNT(*) AS total FROM app.app_user u {where_sql}", params) or {"total": 0}
    rows = _run_pg_dict_query(
        conn,
        f"""
        SELECT u.user_id, u.email, u.display_name, u.status, u.plan_tier,
               u.email_verified_at, u.created_at, u.updated_at
        FROM app.app_user u
        {where_sql}
        ORDER BY u.created_at DESC, u.user_id DESC
        LIMIT %s OFFSET %s
        """,
        [*params, normalized_limit, normalized_offset],
    )
    return {
        "recipients": rows,
        "page": {
            "limit": normalized_limit,
            "offset": normalized_offset,
            "total": int(total_row.get("total") or 0),
        },
    }


def _list_email_campaigns(conn, *, limit: int = 50) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT campaign_id, operator_id, campaign_name, status, subject,
               total_recipient_count, sent_count, failed_count,
               send_started_at, send_finished_at, created_at, updated_at
        FROM app.email_campaign
        ORDER BY created_at DESC, campaign_id DESC
        LIMIT %s
        """,
        [max(1, min(int(limit), 100))],
    )


def _create_email_campaign(
    conn,
    *,
    operator_id: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    campaign_name: str | None = None,
    filter_json: dict[str, Any] | None = None,
    selected_user_ids: list[str] | None = None,
    status: str = "draft",
) -> dict[str, Any]:
    normalized_selected_user_ids = _normalize_user_ids(selected_user_ids)
    return _run_pg_dict_query(
        conn,
        """
        INSERT INTO app.email_campaign (
            campaign_id, operator_id, campaign_name, status, subject, text_body, html_body,
            filter_json, selected_user_ids_json, total_recipient_count, sent_count, failed_count,
            created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0, 0, NOW(), NOW())
        RETURNING campaign_id, operator_id, campaign_name, status, subject, text_body, html_body,
                  filter_json, selected_user_ids_json, total_recipient_count, sent_count, failed_count,
                  send_started_at, send_finished_at, created_at, updated_at
        """,
        [
            _generate_id("email_campaign"),
            str(operator_id or "").strip(),
            str(campaign_name or "").strip() or None,
            _normalize_campaign_status(status),
            str(subject or "").strip(),
            str(text_body or "").strip(),
            str(html_body or "").strip() or None,
            _campaign_json(filter_json or {}),
            _campaign_json(normalized_selected_user_ids),
        ],
    )[0]


def _load_campaign(conn, campaign_id: str) -> dict[str, Any] | None:
    return _fetch_optional_one(
        conn,
        """
        SELECT campaign_id, operator_id, campaign_name, status, subject, text_body, html_body,
               filter_json, selected_user_ids_json, total_recipient_count, sent_count, failed_count,
               send_started_at, send_finished_at, created_at, updated_at
        FROM app.email_campaign
        WHERE campaign_id = %s
        LIMIT 1
        """,
        [campaign_id],
    )


def _materialize_campaign_recipients(conn, campaign: dict[str, Any]) -> list[dict[str, Any]]:
    campaign_id = str(campaign.get("campaign_id") or "").strip()
    user_ids = _normalize_user_ids(campaign.get("selected_user_ids_json") or [])
    if not campaign_id or not user_ids:
        return []

    users = _run_pg_dict_query(
        conn,
        """
        SELECT user_id, email, display_name
        FROM app.app_user
        WHERE user_id = ANY(%s)
          AND NULLIF(BTRIM(email), '') IS NOT NULL
          AND POSITION('@' IN email) > 1
        ORDER BY created_at DESC, user_id DESC
        """,
        [user_ids],
    )
    for user in users:
        _run_pg_dict_query(
            conn,
            """
            INSERT INTO app.email_campaign_recipient (
                campaign_recipient_id, campaign_id, user_id, email, display_name,
                send_status, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, 'pending', NOW(), NOW())
            ON CONFLICT (campaign_id, email) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                display_name = EXCLUDED.display_name,
                updated_at = NOW()
            RETURNING campaign_recipient_id
            """,
            [
                _generate_id("email_recipient"),
                campaign_id,
                str(user.get("user_id") or ""),
                str(user.get("email") or "").strip(),
                str(user.get("display_name") or user.get("user_id") or "").strip(),
            ],
        )
    recipients = _run_pg_dict_query(
        conn,
        """
        SELECT campaign_recipient_id, campaign_id, user_id, email, display_name,
               send_status, error_message, sent_at, created_at, updated_at
        FROM app.email_campaign_recipient
        WHERE campaign_id = %s
        ORDER BY created_at ASC, campaign_recipient_id ASC
        """,
        [campaign_id],
    )
    _refresh_campaign_counts(conn, campaign_id)
    return recipients


def _render_recipient_body(body: str | None, recipient: dict[str, Any], *, is_html: bool = False) -> str | None:
    if body is None:
        return None
    display_name = str(recipient.get("display_name") or "").strip()
    email_value = str(recipient.get("email") or "").strip()
    if is_html:
        display_name = html.escape(display_name)
        email_value = html.escape(email_value)
    return str(body).replace("{display_name}", display_name).replace("{email}", email_value)


def _refresh_campaign_counts(conn, campaign_id: str) -> dict[str, Any]:
    rows = _run_pg_dict_query(
        conn,
        """
        WITH stats AS (
            SELECT
                COUNT(*)::int AS total_recipient_count,
                COUNT(*) FILTER (WHERE send_status = 'sent')::int AS sent_count,
                COUNT(*) FILTER (WHERE send_status = 'failed')::int AS failed_count
            FROM app.email_campaign_recipient
            WHERE campaign_id = %s
        )
        UPDATE app.email_campaign c
        SET total_recipient_count = stats.total_recipient_count,
            sent_count = stats.sent_count,
            failed_count = stats.failed_count,
            updated_at = NOW()
        FROM stats
        WHERE c.campaign_id = %s
        RETURNING c.campaign_id, c.operator_id, c.campaign_name, c.status, c.subject,
                  c.total_recipient_count, c.sent_count, c.failed_count,
                  c.send_started_at, c.send_finished_at, c.created_at, c.updated_at
        """,
        [campaign_id, campaign_id],
    )
    return rows[0] if rows else {}


def _send_email_campaign(conn, campaign_id: str) -> dict[str, Any]:
    campaign = _load_campaign(conn, campaign_id)
    if not campaign:
        raise ValueError("email campaign not found")

    recipients = _materialize_campaign_recipients(conn, campaign)
    if not recipients:
        raise ValueError("no valid recipients selected")

    _run_pg_dict_query(
        conn,
        """
        UPDATE app.email_campaign
        SET status = 'sending', send_started_at = COALESCE(send_started_at, NOW()), updated_at = NOW()
        WHERE campaign_id = %s
        RETURNING campaign_id
        """,
        [campaign_id],
    )

    sent_count = 0
    failed_count = 0
    for recipient in recipients:
        if str(recipient.get("send_status") or "pending") == "sent":
            sent_count += 1
            continue
        try:
            _send_email_message(
                str(recipient.get("email") or "").strip(),
                str(campaign.get("subject") or "").strip(),
                _render_recipient_body(str(campaign.get("text_body") or ""), recipient) or "",
                _render_recipient_body(campaign.get("html_body"), recipient, is_html=True),
            )
            _run_pg_dict_query(
                conn,
                """
                UPDATE app.email_campaign_recipient
                SET send_status = 'sent', error_message = NULL, sent_at = NOW(), updated_at = NOW()
                WHERE campaign_recipient_id = %s
                RETURNING campaign_recipient_id
                """,
                [recipient.get("campaign_recipient_id")],
            )
            sent_count += 1
        except Exception as exc:  # noqa: BLE001 - keep campaign sending other recipients.
            _run_pg_dict_query(
                conn,
                """
                UPDATE app.email_campaign_recipient
                SET send_status = 'failed', error_message = %s, updated_at = NOW()
                WHERE campaign_recipient_id = %s
                RETURNING campaign_recipient_id
                """,
                [str(exc)[:1000], recipient.get("campaign_recipient_id")],
            )
            failed_count += 1

    final_status = "sent" if failed_count == 0 else ("failed" if sent_count == 0 else "partial_failed")
    _run_pg_dict_query(
        conn,
        """
        UPDATE app.email_campaign
        SET status = %s, send_finished_at = NOW(), updated_at = NOW()
        WHERE campaign_id = %s
        RETURNING campaign_id
        """,
        [final_status, campaign_id],
    )
    return _refresh_campaign_counts(conn, campaign_id)


def _list_campaign_recipients(conn, campaign_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
    return _run_pg_dict_query(
        conn,
        """
        SELECT campaign_recipient_id, campaign_id, user_id, email, display_name,
               send_status, error_message, sent_at, created_at, updated_at
        FROM app.email_campaign_recipient
        WHERE campaign_id = %s
        ORDER BY created_at ASC, campaign_recipient_id ASC
        LIMIT %s
        """,
        [campaign_id, max(1, min(int(limit), 500))],
    )