"""Business orchestration for the workspace domain."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from data_platform.chat_backend.infra.settings import _generate_id
from data_platform.chat_backend.domains.workspace import repository
from data_platform.chat_backend.domains.workspace import chart_render
from data_platform.chat_backend.domains.workspace.tokens import sign_chart_token


# ---------------------------------------------------------------------------
# Serializers — 把 DB 行转成稳定的对外契约（datetime -> ISO 字符串）
# ---------------------------------------------------------------------------

def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def serialize_workspace(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "workspace_id": row.get("workspace_id"),
        "theme_key": row.get("theme_key"),
        "title": row.get("title"),
        "source_run_id": row.get("source_run_id"),
        "brief": row.get("brief_json") or {},
        "evidence": row.get("evidence_json") or {},
        "status": row.get("status"),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
    }


def serialize_asset(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": row.get("asset_id"),
        "workspace_id": row.get("workspace_id"),
        "asset_type": row.get("asset_type"),
        "title": row.get("title"),
        "content": row.get("content_json") or {},
        "status": row.get("status"),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
    }


def serialize_watch(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {"watch_enabled": False, "watch_config": {}, "last_scanned_at": None}
    return {
        "watch_enabled": bool(row.get("watch_enabled")),
        "watch_config": row.get("watch_config_json") or {},
        "last_scanned_at": _iso(row.get("last_scanned_at")),
    }


def serialize_alert(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "alert_id": row.get("alert_id"),
        "workspace_id": row.get("workspace_id"),
        "alert_kind": row.get("alert_kind"),
        "severity": row.get("severity"),
        "title": row.get("title"),
        "body": row.get("body") or "",
        "payload": row.get("payload_json") or {},
        "read_at": _iso(row.get("read_at")),
        "created_at": _iso(row.get("created_at")),
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def upsert_workspace_from_analysis(
    conn,
    *,
    user_id: str,
    theme_key: str,
    title: str,
    source_run_id: str | None = None,
    brief: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """一次分析完成后，落成或更新「一个用户在追的一个品」的工作台。

    同一 (user_id, theme_key) 只保留一个 active 工作台；并发安全靠 advisory 锁保证。
    """
    repository.lock_user_theme(conn, user_id, theme_key)
    existing = repository.find_active_workspace_by_theme(conn, user_id, theme_key)
    if existing is not None:
        row = repository.update_workspace_payload(
            conn,
            workspace_id=existing["workspace_id"],
            title=title,
            source_run_id=source_run_id,
            brief=brief,
            evidence=evidence,
        )
        return serialize_workspace(row)

    row = repository.insert_workspace(
        conn,
        workspace_id=_generate_id("ws"),
        user_id=user_id,
        theme_key=theme_key,
        title=title,
        source_run_id=source_run_id,
        brief=brief,
        evidence=evidence,
    )
    return serialize_workspace(row)


def add_detail_page_asset(
    conn,
    *,
    user_id: str,
    workspace_id: str,
    title: str | None,
    content: dict[str, Any] | None,
) -> dict[str, Any] | None:
    owned = repository.get_workspace_for_user(conn, user_id, workspace_id)
    if owned is None:
        return None
    row = repository.insert_asset(
        conn,
        asset_id=_generate_id("wsa"),
        workspace_id=workspace_id,
        asset_type="detail_page",
        title=title,
        content=content,
    )
    return serialize_asset(row)


def set_watch(
    conn,
    *,
    user_id: str,
    workspace_id: str,
    watch_enabled: bool,
    watch_config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    owned = repository.get_workspace_for_user(conn, user_id, workspace_id)
    if owned is None:
        return None
    row = repository.upsert_watch(
        conn,
        workspace_id=workspace_id,
        user_id=user_id,
        watch_enabled=watch_enabled,
        watch_config=watch_config,
    )
    return serialize_watch(row)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def get_workspace_detail(conn, user_id: str, workspace_id: str) -> dict[str, Any] | None:
    row = repository.get_workspace_for_user(conn, user_id, workspace_id)
    if row is None:
        return None
    detail = serialize_workspace(row)
    detail["assets"] = [serialize_asset(a) for a in repository.list_assets(conn, workspace_id)]
    detail["watch"] = serialize_watch(repository.get_watch(conn, workspace_id))
    return detail


def list_workspaces(conn, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = repository.list_workspaces_for_user(conn, user_id, limit=limit)
    return [serialize_workspace(r) for r in rows]


def list_alerts(conn, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = repository.list_alerts_for_user(conn, user_id, limit=limit)
    return [serialize_alert(r) for r in rows]


# ---------------------------------------------------------------------------
# Evidence charts (SVG) — 把工作台 evidence 映射成证据图
# ---------------------------------------------------------------------------

_CHART_TITLES = {
    "trend": "趋势",
    "price": "价格带",
    "competition": "竞争度",
    "forecast": "预测区间",
    "risk": "风险概览",
}


def _extract_series_values(series: Any) -> list[Any]:
    """trend_series 可能是数值列表，也可能是 [{date,value}] 这类对象列表。"""
    if not isinstance(series, list):
        return []
    values: list[Any] = []
    for point in series:
        if isinstance(point, dict):
            values.append(
                point.get("value")
                if point.get("value") is not None
                else point.get("y")
                if point.get("y") is not None
                else point.get("sales")
            )
        else:
            values.append(point)
    return values


def chart_has_data(evidence: dict[str, Any] | None, chart_kind: str) -> bool:
    evidence = evidence or {}
    if chart_kind == "trend":
        return len(_extract_series_values(evidence.get("trend_series"))) >= 2
    if chart_kind == "price":
        band = evidence.get("price_band") or {}
        return band.get("low") is not None and band.get("high") is not None
    if chart_kind == "competition":
        return evidence.get("competition_score") is not None
    if chart_kind == "forecast":
        band = evidence.get("forecast_band") or {}
        return bool(band.get("lower")) and bool(band.get("upper"))
    if chart_kind == "risk":
        return bool(evidence.get("risk_lights"))
    return False


def render_workspace_chart(evidence: dict[str, Any] | None, chart_kind: str) -> str:
    """把 evidence 映射到对应证据图，返回 SVG 字符串（永不抛错，由 chart_render 兜底）。"""
    evidence = evidence or {}
    if chart_kind == "trend":
        values = _extract_series_values(evidence.get("trend_series"))
        return chart_render.render_trend_sparkline(values, label=_CHART_TITLES["trend"])
    if chart_kind == "price":
        band = evidence.get("price_band") or {}
        return chart_render.render_price_band(
            band.get("low"), band.get("high"), band.get("current"), label=_CHART_TITLES["price"]
        )
    if chart_kind == "competition":
        return chart_render.render_competition_gauge(
            evidence.get("competition_score"), label=_CHART_TITLES["competition"]
        )
    if chart_kind == "forecast":
        band = evidence.get("forecast_band") or {}
        return chart_render.render_forecast_band(
            band.get("lower") or [], band.get("upper") or [], band.get("mid"), label=_CHART_TITLES["forecast"]
        )
    if chart_kind == "risk":
        return chart_render.render_risk_lights(evidence.get("risk_lights") or [], label=_CHART_TITLES["risk"])
    return chart_render.render_placeholder("未知证据图")


def build_evidence_chart_links(
    workspace_id: str,
    evidence: dict[str, Any] | None,
    *,
    public_base_url: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """为有数据的证据图生成签名 SVG 链接（最多 limit 个，按固定优先级）。"""
    base = (public_base_url or "").rstrip("/")
    links: list[dict[str, Any]] = []
    for chart_kind in ("trend", "competition", "price", "forecast", "risk"):
        if len(links) >= max(1, limit):
            break
        if not chart_has_data(evidence, chart_kind):
            continue
        token = sign_chart_token(workspace_id, chart_kind)
        links.append(
            {
                "kind": chart_kind,
                "title": _CHART_TITLES.get(chart_kind, chart_kind),
                "svg_url": f"{base}/portal/api/evidence/chart/{token}.svg",
            }
        )
    return links


def get_workspace_evidence(conn, workspace_id: str) -> dict[str, Any] | None:
    """供已验签的公开证据图路由按 id 取 evidence（不做 user 归属校验）。"""
    row = repository.get_workspace_by_id(conn, workspace_id)
    if row is None:
        return None
    return row.get("evidence_json") or {}
