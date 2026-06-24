"""证据图 SVG 渲染（纯函数，零外部依赖）。

设计要点：
- 全部为纯函数：输入数据 -> 返回 SVG 字符串，无 IO、无全局状态，便于单测。
- 任意异常都兜底成一张占位 SVG，绝不抛错到调用方（气泡渲染链路必须稳）。
- 仅依赖标准库；输出可直接内联为 ``data:image/svg+xml`` 或经 ``/portal/api/evidence/chart`` 暴露。

坐标系约定：默认画布 320x120，留出内边距。颜色走中性品牌色，避免误导性强对比。
"""
from __future__ import annotations

import html
from typing import Any, Sequence

_W = 320
_H = 120
_PAD = 12

_INK = "#1f2937"
_MUTED = "#9ca3af"
_ACCENT = "#2563eb"
_BG = "#ffffff"
_GOOD = "#16a34a"
_WARN = "#d97706"
_BAD = "#dc2626"


def _esc(text: Any) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def _to_floats(values: Sequence[Any]) -> list[float]:
    out: list[float] = []
    for v in values:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            continue
    return out


def _svg_open(width: int = _W, height: int = _H) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="{_BG}"/>'
    )


def _placeholder(message: str = "暂无数据") -> str:
    return (
        _svg_open()
        + f'<text x="{_W / 2}" y="{_H / 2}" fill="{_MUTED}" font-size="13" '
        f'font-family="sans-serif" text-anchor="middle" dominant-baseline="middle">'
        f"{_esc(message)}</text></svg>"
    )


def render_placeholder(message: str = "暂无数据") -> str:
    """对外暴露的占位图（与内部 ``_placeholder`` 同义）。"""
    return _placeholder(message)


def _safe(render):
    """装饰器：渲染失败时返回占位图而非抛错。"""

    def wrapper(*args, **kwargs) -> str:
        try:
            result = render(*args, **kwargs)
            return result if isinstance(result, str) and result.strip() else _placeholder()
        except Exception:  # noqa: BLE001 — 证据图渲染必须永不抛错
            return _placeholder()

    return wrapper


# ---------------------------------------------------------------------------
# 1) 趋势折线（sparkline）
# ---------------------------------------------------------------------------

@_safe
def render_trend_sparkline(values: Sequence[Any], *, label: str = "") -> str:
    points = _to_floats(values)
    if len(points) < 2:
        return _placeholder("趋势数据不足")

    lo, hi = min(points), max(points)
    span = (hi - lo) or 1.0
    inner_w = _W - 2 * _PAD
    inner_h = _H - 2 * _PAD - (14 if label else 0)
    step = inner_w / (len(points) - 1)

    coords = []
    for i, val in enumerate(points):
        x = _PAD + i * step
        y = _PAD + inner_h - (val - lo) / span * inner_h
        coords.append((x, y))

    path = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in coords)
    last_x, last_y = coords[-1]
    label_text = (
        f'<text x="{_PAD}" y="{_H - 4}" fill="{_MUTED}" font-size="11" '
        f'font-family="sans-serif">{_esc(label)}</text>'
        if label
        else ""
    )
    return (
        _svg_open()
        + f'<path d="{path}" fill="none" stroke="{_ACCENT}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        + f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3" fill="{_ACCENT}"/>'
        + label_text
        + "</svg>"
    )


# ---------------------------------------------------------------------------
# 2) 价格带
# ---------------------------------------------------------------------------

@_safe
def render_price_band(low: Any, high: Any, current: Any = None, *, label: str = "价格带") -> str:
    lo = float(low)
    hi = float(high)
    if hi < lo:
        lo, hi = hi, lo
    span = (hi - lo) or 1.0

    track_y = _H / 2
    track_x0 = _PAD + 30
    track_x1 = _W - _PAD
    track_w = track_x1 - track_x0

    marker = ""
    if current is not None:
        cur = max(lo, min(hi, float(current)))
        cx = track_x0 + (cur - lo) / span * track_w
        marker = (
            f'<circle cx="{cx:.1f}" cy="{track_y}" r="5" fill="{_ACCENT}"/>'
            f'<text x="{cx:.1f}" y="{track_y - 10}" fill="{_INK}" font-size="11" '
            f'font-family="sans-serif" text-anchor="middle">{_esc(round(float(current), 2))}</text>'
        )
    return (
        _svg_open()
        + f'<text x="{_PAD}" y="{_H - 8}" fill="{_MUTED}" font-size="11" '
        f'font-family="sans-serif">{_esc(label)}</text>'
        + f'<rect x="{track_x0}" y="{track_y - 4}" width="{track_w}" height="8" rx="4" '
        f'fill="#e5e7eb"/>'
        + f'<text x="{track_x0}" y="{track_y + 22}" fill="{_MUTED}" font-size="10" '
        f'font-family="sans-serif">{_esc(round(lo, 2))}</text>'
        + f'<text x="{track_x1}" y="{track_y + 22}" fill="{_MUTED}" font-size="10" '
        f'font-family="sans-serif" text-anchor="end">{_esc(round(hi, 2))}</text>'
        + marker
        + "</svg>"
    )


# ---------------------------------------------------------------------------
# 3) 竞争度仪表（0..1）
# ---------------------------------------------------------------------------

@_safe
def render_competition_gauge(score: Any, *, label: str = "竞争度") -> str:
    s = max(0.0, min(1.0, float(score)))
    track_x0 = _PAD
    track_x1 = _W - _PAD
    track_w = track_x1 - track_x0
    track_y = _H / 2
    fill_w = track_w * s
    color = _GOOD if s < 0.34 else _WARN if s < 0.67 else _BAD
    return (
        _svg_open()
        + f'<text x="{_PAD}" y="{track_y - 14}" fill="{_INK}" font-size="12" '
        f'font-family="sans-serif">{_esc(label)}</text>'
        + f'<rect x="{track_x0}" y="{track_y - 6}" width="{track_w}" height="12" rx="6" '
        f'fill="#e5e7eb"/>'
        + f'<rect x="{track_x0}" y="{track_y - 6}" width="{fill_w:.1f}" height="12" rx="6" '
        f'fill="{color}"/>'
        + f'<text x="{track_x1}" y="{track_y + 26}" fill="{_MUTED}" font-size="11" '
        f'font-family="sans-serif" text-anchor="end">{int(round(s * 100))}%</text>'
        + "</svg>"
    )


# ---------------------------------------------------------------------------
# 4) 预测区间带
# ---------------------------------------------------------------------------

@_safe
def render_forecast_band(
    lower: Sequence[Any], upper: Sequence[Any], mid: Sequence[Any] | None = None, *, label: str = "预测区间"
) -> str:
    lo = _to_floats(lower)
    hi = _to_floats(upper)
    n = min(len(lo), len(hi))
    if n < 2:
        return _placeholder("预测数据不足")
    lo, hi = lo[:n], hi[:n]
    mid_pts = _to_floats(mid)[:n] if mid else []

    all_vals = lo + hi + mid_pts
    vmin, vmax = min(all_vals), max(all_vals)
    span = (vmax - vmin) or 1.0
    inner_w = _W - 2 * _PAD
    inner_h = _H - 2 * _PAD - 14
    step = inner_w / (n - 1)

    def _y(v: float) -> float:
        return _PAD + inner_h - (v - vmin) / span * inner_h

    def _x(i: int) -> float:
        return _PAD + i * step

    top = [(_x(i), _y(hi[i])) for i in range(n)]
    bottom = [(_x(i), _y(lo[i])) for i in range(n - 1, -1, -1)]
    area = (
        "M "
        + " L ".join(f"{x:.1f} {y:.1f}" for x, y in top)
        + " L "
        + " L ".join(f"{x:.1f} {y:.1f}" for x, y in bottom)
        + " Z"
    )
    mid_path = ""
    if mid_pts:
        mid_path = (
            '<path d="M '
            + " L ".join(f"{_x(i):.1f} {_y(mid_pts[i]):.1f}" for i in range(n))
            + f'" fill="none" stroke="{_ACCENT}" stroke-width="2"/>'
        )
    return (
        _svg_open()
        + f'<path d="{area}" fill="{_ACCENT}" fill-opacity="0.15" stroke="none"/>'
        + mid_path
        + f'<text x="{_PAD}" y="{_H - 4}" fill="{_MUTED}" font-size="11" '
        f'font-family="sans-serif">{_esc(label)}</text>'
        + "</svg>"
    )


# ---------------------------------------------------------------------------
# 5) 风险灯（多指标红黄绿）
# ---------------------------------------------------------------------------

@_safe
def render_risk_lights(items: Sequence[dict[str, Any]], *, label: str = "风险概览") -> str:
    lights = list(items or [])
    if not lights:
        return _placeholder("暂无风险项")
    color_map = {"good": _GOOD, "green": _GOOD, "warn": _WARN, "yellow": _WARN, "bad": _BAD, "red": _BAD}

    height = _PAD * 2 + 18 + len(lights) * 22
    parts = [_svg_open(_W, height)]
    parts.append(
        f'<text x="{_PAD}" y="{_PAD + 8}" fill="{_INK}" font-size="12" '
        f'font-family="sans-serif">{_esc(label)}</text>'
    )
    for idx, item in enumerate(lights):
        cy = _PAD + 28 + idx * 22
        level = str(item.get("level", "warn")).lower()
        color = color_map.get(level, _MUTED)
        name = item.get("name", "")
        parts.append(f'<circle cx="{_PAD + 6}" cy="{cy - 4}" r="6" fill="{color}"/>')
        parts.append(
            f'<text x="{_PAD + 20}" y="{cy}" fill="{_INK}" font-size="12" '
            f'font-family="sans-serif">{_esc(name)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)
