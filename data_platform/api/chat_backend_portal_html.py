from __future__ import annotations


def render_portal_html() -> str:
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>虾密小助手 - 我的账户</title>
  <style>
    :root {
      --bg: #f5efe4;
      --paper: rgba(255, 251, 245, 0.92);
      --ink: #1e2a2f;
      --muted: #68767d;
      --accent: #114b5f;
      --accent-2: #d97706;
      --line: rgba(17, 75, 95, 0.12);
      --danger: #b42318;
      --ok: #0f766e;
      --shadow: 0 18px 48px rgba(30, 42, 47, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "IBM Plex Sans", "Helvetica Neue", "PingFang SC", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(217, 119, 6, 0.18), transparent 24%),
        radial-gradient(circle at right 20%, rgba(17, 75, 95, 0.18), transparent 22%),
        linear-gradient(180deg, #fffdf8 0%, var(--bg) 100%);
      min-height: 100vh;
    }
    .shell { max-width: 960px; margin: 0 auto; padding: 28px 20px; }
    h1 { font-size: 1.5rem; margin: 0 0 6px; }
    .subtitle { color: var(--muted); font-size: 0.88rem; margin-bottom: 24px; }
    .card {
      background: var(--paper);
      border-radius: 14px;
      box-shadow: var(--shadow);
      padding: 20px 24px;
      margin-bottom: 20px;
    }
    .card h2 {
      font-size: 1.1rem;
      margin: 0 0 14px;
      color: var(--accent);
      border-bottom: 1px solid var(--line);
      padding-bottom: 8px;
    }

    /* KPI row */
    .kpi-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
      margin-bottom: 10px;
    }
    .kpi { text-align: center; }
    .kpi .value {
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--accent);
    }
    .kpi .label {
      font-size: 0.78rem;
      color: var(--muted);
      margin-top: 2px;
    }

    /* Table */
    table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
    thead th {
      text-align: left;
      font-weight: 600;
      color: var(--muted);
      padding: 6px 8px;
      border-bottom: 2px solid var(--line);
      white-space: nowrap;
    }
    tbody td {
      padding: 5px 8px;
      border-bottom: 1px solid var(--line);
    }
    tbody tr:hover { background: rgba(17, 75, 95, 0.04); }
    .positive { color: var(--ok); }
    .negative { color: var(--danger); }

    /* Pricing pills */
    .pricing-row { display: flex; flex-wrap: wrap; gap: 10px; }
    .pricing-pill {
      background: rgba(17, 75, 95, 0.07);
      border-radius: 8px;
      padding: 6px 14px;
      font-size: 0.82rem;
    }
    .pricing-pill .name { font-weight: 600; }
    .pricing-pill .cost { color: var(--accent-2); margin-left: 6px; }

    /* Pagination */
    .pager {
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 10px;
      margin-top: 12px;
      font-size: 0.82rem;
    }

    /* Usage chart */
    .chart-row {
      display: flex;
      align-items: flex-end;
      gap: 3px;
      height: 100px;
      margin-top: 10px;
    }
    .chart-bar {
      flex: 1;
      min-width: 6px;
      max-width: 28px;
      background: var(--accent);
      border-radius: 3px 3px 0 0;
      position: relative;
      cursor: default;
    }
    .chart-bar:hover::after {
      content: attr(data-tip);
      position: absolute;
      bottom: 100%;
      left: 50%;
      transform: translateX(-50%);
      background: var(--ink);
      color: #fff;
      padding: 3px 7px;
      border-radius: 4px;
      font-size: 0.7rem;
      white-space: nowrap;
    }
    .chart-labels {
      display: flex;
      gap: 3px;
      margin-top: 2px;
      font-size: 0.58rem;
      color: var(--muted);
    }
    .chart-labels span { flex: 1; min-width: 6px; max-width: 28px; text-align: center; overflow: hidden; }

    button {
      cursor: pointer;
      border: 1px solid var(--line);
      background: var(--paper);
      color: var(--accent);
      padding: 5px 14px;
      border-radius: 6px;
      font-size: 0.82rem;
    }
    button:hover { background: rgba(17, 75, 95, 0.06); }
    button:disabled { opacity: 0.5; cursor: default; }

    .error-msg {
      background: rgba(180, 35, 24, 0.08);
      color: var(--danger);
      padding: 20px;
      border-radius: 10px;
      text-align: center;
      font-size: 0.95rem;
    }

    .plan-badge {
      display: inline-block;
      background: var(--accent);
      color: #fff;
      padding: 2px 10px;
      border-radius: 6px;
      font-size: 0.78rem;
      margin-left: 8px;
    }

    @media (max-width: 600px) {
      .shell { padding: 16px 12px; }
      .kpi-row { grid-template-columns: repeat(2, 1fr); }
      table { font-size: 0.75rem; }
    }
  </style>
</head>
<body>
<div class="shell">
  <h1>🦐 虾密小助手 <span id="plan-badge" class="plan-badge" style="display:none;"></span></h1>
  <div class="subtitle" id="user-info">加载中…</div>

  <div id="error-panel" style="display:none;" class="error-msg"></div>

  <!-- KPI -->
  <div id="kpi-section" class="card" style="display:none;">
    <h2>积分概览</h2>
    <div class="kpi-row" id="kpi-row"></div>
  </div>

  <!-- Pricing -->
  <div id="pricing-section" class="card" style="display:none;">
    <h2>当前计价</h2>
    <div class="pricing-row" id="pricing-row"></div>
  </div>

  <!-- Usage chart -->
  <div id="usage-section" class="card" style="display:none;">
    <h2>消费趋势 (近 30 天)</h2>
    <div class="chart-row" id="usage-chart"></div>
    <div class="chart-labels" id="usage-labels"></div>
  </div>

  <!-- Ledger -->
  <div id="ledger-section" class="card" style="display:none;">
    <h2>积分明细</h2>
    <table>
      <thead>
        <tr>
          <th>时间</th>
          <th>类型</th>
          <th>事件</th>
          <th>变动</th>
          <th>余额</th>
          <th>说明</th>
        </tr>
      </thead>
      <tbody id="ledger-body"></tbody>
    </table>
    <div class="pager" id="ledger-pager"></div>
  </div>
</div>

<script>
(function() {
  const params = new URLSearchParams(location.search);
  const token = params.get("t") || "";
  if (!token) {
    showError("缺少访问令牌。请通过对话中 /me 命令获取链接访问。");
    return;
  }

  const headers = { "Authorization": "Bearer " + token };
  let ledgerPage = 1;

  function showError(msg) {
    const el = document.getElementById("error-panel");
    el.textContent = msg;
    el.style.display = "block";
  }

  function fmtTime(ts) {
    if (!ts) return "-";
    const d = new Date(ts);
    if (isNaN(d.getTime())) return String(ts).slice(0, 19);
    const pad = n => String(n).padStart(2, "0");
    return pad(d.getMonth()+1) + "-" + pad(d.getDate()) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  function fmtDay(ds) {
    if (!ds) return "";
    return String(ds).slice(5);
  }

  async function apiFetch(path) {
    const resp = await fetch(path, { headers });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.detail || body.message || resp.statusText);
    }
    const json = await resp.json();
    if (json.success !== true) throw new Error(json.message || "请求失败");
    return json.data;
  }

  async function loadAccount() {
    try {
      const data = await apiFetch("/portal/api/account");
      renderAccount(data);
    } catch (e) {
      showError("加载失败：" + e.message);
    }
  }

  function renderAccount(data) {
    const user = data.user || {};
    const pa = data.points_account || {};
    const us = data.usage_summary || {};
    const planTier = data.plan_tier || user.plan_tier || "free";

    document.getElementById("user-info").textContent =
      (user.display_name || user.user_id || "用户") + "  ·  " + (user.email || "");

    const badge = document.getElementById("plan-badge");
    badge.textContent = planTier;
    badge.style.display = "inline-block";

    // KPIs
    const kpis = [
      { label: "当前余额", value: intVal(pa.balance_points) },
      { label: "累计赠送", value: intVal(pa.lifetime_granted_points) },
      { label: "累计购买", value: intVal(pa.lifetime_purchased_points) },
      { label: "累计消费", value: intVal(pa.lifetime_spent_points) },
      { label: "30天事件数", value: intVal(us.event_count_30d) },
    ];
    const kpiRow = document.getElementById("kpi-row");
    kpiRow.innerHTML = kpis.map(k =>
      '<div class="kpi"><div class="value">' + k.value + '</div><div class="label">' + k.label + '</div></div>'
    ).join("");
    document.getElementById("kpi-section").style.display = "block";

    // Pricing
    const costMap = data.point_cost_by_event || {};
    const displayMap = data.event_pricing_display || {};
    const pricingRow = document.getElementById("pricing-row");
    pricingRow.innerHTML = Object.entries(costMap).map(([et, pts]) => {
      const label = displayMap[et] || et;
      return '<div class="pricing-pill"><span class="name">' + esc(label) + '</span><span class="cost">' + pts + ' 积分/次</span></div>';
    }).join("");
    if (Object.keys(costMap).length > 0) {
      document.getElementById("pricing-section").style.display = "block";
    }
  }

  async function loadUsageChart() {
    try {
      const data = await apiFetch("/portal/api/usage-daily?days=30");
      renderUsageChart(data.rows || []);
    } catch (e) { /* silently skip chart */ }
  }

  function renderUsageChart(rows) {
    // Aggregate by day
    const byDay = {};
    rows.forEach(r => {
      const d = String(r.day || "").slice(0, 10);
      byDay[d] = (byDay[d] || 0) + intVal(r.total_units);
    });
    // Fill last 30 days
    const days = [];
    const now = new Date();
    for (let i = 29; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      days.push({ day: key, units: byDay[key] || 0 });
    }
    const maxU = Math.max(1, ...days.map(d => d.units));
    const chartEl = document.getElementById("usage-chart");
    const labelsEl = document.getElementById("usage-labels");
    chartEl.innerHTML = days.map(d => {
      const h = Math.max(2, (d.units / maxU) * 96);
      return '<div class="chart-bar" style="height:' + h + 'px" data-tip="' + fmtDay(d.day) + ': ' + d.units + '积分"></div>';
    }).join("");
    labelsEl.innerHTML = days.map((d, i) => {
      const show = i % 5 === 0 || i === days.length - 1;
      return '<span>' + (show ? fmtDay(d.day) : '') + '</span>';
    }).join("");
    document.getElementById("usage-section").style.display = "block";
  }

  async function loadLedger(page) {
    ledgerPage = page || 1;
    try {
      const data = await apiFetch("/portal/api/ledger?page=" + ledgerPage + "&page_size=20");
      renderLedger(data);
    } catch (e) { /* skip */ }
  }

  function renderLedger(data) {
    const rows = data.rows || [];
    const total = data.total || 0;
    const pageSize = data.page_size || 20;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));

    const tbody = document.getElementById("ledger-body");
    tbody.innerHTML = rows.map(r => {
      const delta = intVal(r.points_delta);
      const cls = delta >= 0 ? "positive" : "negative";
      const sign = delta >= 0 ? "+" : "";
      return '<tr>' +
        '<td>' + fmtTime(r.created_at) + '</td>' +
        '<td>' + esc(r.entry_type || "") + '</td>' +
        '<td>' + esc(r.event_type || "") + '</td>' +
        '<td class="' + cls + '">' + sign + delta + '</td>' +
        '<td>' + intVal(r.balance_after_points) + '</td>' +
        '<td>' + esc(r.description || "") + '</td>' +
        '</tr>';
    }).join("");

    const pager = document.getElementById("ledger-pager");
    pager.innerHTML =
      '<button id="pg-prev" ' + (ledgerPage <= 1 ? 'disabled' : '') + '>上一页</button>' +
      '<span>' + ledgerPage + ' / ' + totalPages + ' (共 ' + total + ' 条)</span>' +
      '<button id="pg-next" ' + (ledgerPage >= totalPages ? 'disabled' : '') + '>下一页</button>';
    document.getElementById("pg-prev").onclick = () => loadLedger(ledgerPage - 1);
    document.getElementById("pg-next").onclick = () => loadLedger(ledgerPage + 1);
    document.getElementById("ledger-section").style.display = "block";
  }

  function intVal(v) { return parseInt(v, 10) || 0; }
  function esc(s) {
    const el = document.createElement("span");
    el.textContent = s;
    return el.innerHTML;
  }

  // Boot
  loadAccount();
  loadUsageChart();
  loadLedger(1);
})();
</script>
</body>
</html>"""
