from __future__ import annotations


def render_admin_backoffice_html() -> str:
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>XiaMimate Admin Backoffice</title>
  <style>
    :root {
      --bg: #f5efe4;
      --paper: rgba(255, 251, 245, 0.9);
      --ink: #1e2a2f;
      --muted: #68767d;
      --accent: #114b5f;
      --accent-2: #d97706;
      --line: rgba(17, 75, 95, 0.12);
      --danger: #b42318;
      --ok: #0f766e;
      --shadow: 0 18px 48px rgba(30, 42, 47, 0.12);
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      font-family: "IBM Plex Sans", "Helvetica Neue", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(217, 119, 6, 0.18), transparent 24%),
        radial-gradient(circle at right 20%, rgba(17, 75, 95, 0.18), transparent 22%),
        linear-gradient(180deg, #fffdf8 0%, var(--bg) 100%);
      min-height: 100vh;
    }

    .shell {
      max-width: 1480px;
      margin: 0 auto;
      padding: 28px;
    }

    .hero {
      display: grid;
      grid-template-columns: 1.5fr 1fr;
      gap: 20px;
      margin-bottom: 20px;
    }

    .card {
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }

    .hero-main {
      padding: 24px;
    }

    .eyebrow {
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--accent-2);
      margin-bottom: 10px;
    }

    h1 {
      margin: 0 0 12px;
      font-family: "Space Grotesk", "Avenir Next", sans-serif;
      font-size: 38px;
      line-height: 1.05;
    }

    .hero-main p,
    .hint {
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }

    .hero-side {
      padding: 20px;
      display: grid;
      gap: 12px;
      align-content: start;
    }

    .layout {
      display: grid;
      grid-template-columns: 360px minmax(0, 1fr);
      gap: 20px;
      align-items: start;
    }

    .panel {
      padding: 18px;
    }

    .panel h2,
    .panel h3 {
      margin: 0 0 14px;
      font-family: "Space Grotesk", "Avenir Next", sans-serif;
    }

    .field-grid {
      display: grid;
      gap: 10px;
    }

    label {
      display: block;
      font-size: 13px;
      font-weight: 700;
      color: var(--muted);
      margin-bottom: 6px;
    }

    input,
    textarea,
    button {
      font: inherit;
    }

    input,
    textarea {
      width: 100%;
      border: 1px solid rgba(17, 75, 95, 0.18);
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.92);
      padding: 12px 14px;
      color: var(--ink);
    }

    textarea {
      min-height: 92px;
      resize: vertical;
    }

    .button-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    button {
      border: 0;
      border-radius: 999px;
      padding: 11px 16px;
      background: var(--accent);
      color: white;
      cursor: pointer;
      transition: transform 120ms ease, opacity 120ms ease;
    }

    button.secondary {
      background: rgba(17, 75, 95, 0.1);
      color: var(--accent);
    }

    button.warn {
      background: var(--accent-2);
    }

    button:hover {
      transform: translateY(-1px);
      opacity: 0.96;
    }

    .status {
      min-height: 22px;
      font-size: 13px;
      color: var(--muted);
    }

    .status.error {
      color: var(--danger);
    }

    .status.ok {
      color: var(--ok);
    }

    .metric-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }

    .metric {
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      background: rgba(255, 255, 255, 0.7);
    }

    .metric .label {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .metric .value {
      margin-top: 8px;
      font-family: "Space Grotesk", "Avenir Next", sans-serif;
      font-size: 28px;
    }

    .user-list,
    .section-list {
      display: grid;
      gap: 10px;
    }

    .user-item,
    .mini-card {
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px 14px;
      background: rgba(255, 255, 255, 0.82);
    }

    .user-item button {
      margin-top: 10px;
    }

    .detail-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }

    .detail-grid.full {
      grid-template-columns: 1fr;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }

    th,
    td {
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid rgba(17, 75, 95, 0.08);
      vertical-align: top;
    }

    th {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }

    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      background: rgba(17, 75, 95, 0.06);
      border-radius: 14px;
      padding: 12px;
      font-size: 12px;
      line-height: 1.5;
    }

    .empty {
      color: var(--muted);
      font-size: 13px;
      padding: 12px 0;
    }

    @media (max-width: 1100px) {
      .hero,
      .layout,
      .detail-grid {
        grid-template-columns: 1fr;
      }

      .metric-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }

    @media (max-width: 720px) {
      .shell {
        padding: 16px;
      }

      h1 {
        font-size: 28px;
      }

      .metric-grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div class="card hero-main">
        <div class="eyebrow">Admin Backoffice</div>
        <h1>XiaMimate Chat Backend</h1>
        <p>这是一版内置在 chat_backend 里的最小后台。它先解决三件事：看清用户账务、看清订单/订阅、带审计地人工加积分。</p>
      </div>
      <div class="card hero-side">
        <div>
          <label for="admin-token">Admin Token</label>
          <input id="admin-token" type="password" placeholder="Bearer token" />
        </div>
        <div>
          <label for="admin-operator">Operator</label>
          <input id="admin-operator" type="text" placeholder="例如 ops-liu" />
        </div>
        <div class="button-row">
          <button id="load-overview">刷新总览</button>
          <button id="load-audit" class="secondary">刷新审计</button>
        </div>
        <div id="global-status" class="status"></div>
      </div>
    </section>

    <section class="layout">
      <aside class="card panel">
        <h2>用户检索</h2>
        <div class="field-grid">
          <div>
            <label for="user-query">User ID / Email / Display Name</label>
            <input id="user-query" type="text" placeholder="guest 或邮箱或用户 ID" />
          </div>
          <div class="button-row">
            <button id="search-users">搜索用户</button>
            <button id="search-all" class="secondary">最近用户</button>
          </div>
        </div>
        <div id="user-results" class="user-list" style="margin-top: 14px;"></div>

        <div style="margin-top: 18px;">
          <h3>人工加积分</h3>
          <div class="field-grid">
            <div>
              <label for="grant-user-id">Target User ID</label>
              <input id="grant-user-id" type="text" placeholder="先从右侧详情或搜索结果填充" />
            </div>
            <div>
              <label for="grant-points">Points</label>
              <input id="grant-points" type="number" min="1" value="100" />
            </div>
            <div>
              <label for="grant-description">Description</label>
              <textarea id="grant-description" placeholder="例如：手工补单 / 客诉补偿 / 灰度测试加额"></textarea>
            </div>
            <button id="grant-submit" class="warn">执行加积分</button>
            <div id="grant-status" class="status"></div>
          </div>
        </div>

        <div style="margin-top: 18px;">
          <h3>计价管理</h3>
          <div id="pricing-list" class="field-grid" style="margin-bottom: 10px;"></div>
          <div class="button-row">
            <button id="load-pricing" class="secondary">刷新计价</button>
          </div>
          <div id="pricing-status" class="status"></div>
        </div>
      </aside>

      <main class="section-list">
        <section class="card panel">
          <h2>总览</h2>
          <div id="metric-grid" class="metric-grid"></div>
          <div class="detail-grid">
            <div class="mini-card">
              <h3>最近账本</h3>
              <div id="recent-ledger"></div>
            </div>
            <div class="mini-card">
              <h3>最近订单</h3>
              <div id="recent-orders"></div>
            </div>
          </div>
        </section>

        <section class="card panel">
          <h2>用户详情</h2>
          <div id="user-detail" class="detail-grid full">
            <div class="empty">先搜索并选择一个用户。</div>
          </div>
        </section>

        <section class="card panel">
          <h2>后台审计</h2>
          <div id="audit-logs"></div>
        </section>
      </main>
    </section>
  </div>

  <script>
    const state = {
      selectedUserId: null,
    };

    const getToken = () => document.getElementById('admin-token').value.trim();
    const getOperator = () => document.getElementById('admin-operator').value.trim();

    const setStatus = (id, text, tone = '') => {
      const element = document.getElementById(id);
      element.textContent = text || '';
      element.className = `status ${tone}`.trim();
    };

    const escapeHtml = (value) => String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;');

    const authHeaders = () => {
      const token = getToken();
      const operator = getOperator();
      if (!token) {
        throw new Error('请先填写 Admin Token');
      }
      if (!operator) {
        throw new Error('请先填写 Operator');
      }
      localStorage.setItem('xiamimate_admin_token', token);
      localStorage.setItem('xiamimate_admin_operator', operator);
      return {
        'Authorization': `Bearer ${token}`,
        'X-Admin-Operator': operator,
      };
    };

    const fetchJson = async (url, options = {}) => {
      const headers = {
        ...(options.headers || {}),
        ...authHeaders(),
      };
      if (options.body && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
      }
      const response = await fetch(url, {
        ...options,
        headers,
      });
      const payload = await response.json();
      if (!response.ok || payload.success !== true) {
        throw new Error(payload.message || `HTTP ${response.status}`);
      }
      return payload.data || {};
    };

    const renderKv = (pairs) => `
      <table>
        <tbody>
          ${pairs.map(([label, value]) => `
            <tr>
              <th>${escapeHtml(label)}</th>
              <td>${escapeHtml(value)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;

    const renderTable = (columns, rows) => {
      if (!rows || rows.length === 0) {
        return '<div class="empty">暂无数据</div>';
      }
      return `
        <table>
          <thead>
            <tr>${columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join('')}</tr>
          </thead>
          <tbody>
            ${rows.map((row) => `
              <tr>
                ${columns.map((column) => `<td>${escapeHtml(column.render(row))}</td>`).join('')}
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    };

    const renderMetrics = (metrics) => {
      const entries = [
        ['Total Users', metrics.total_users],
        ['Active API Keys', metrics.active_api_keys],
        ['Paid Orders', metrics.paid_orders],
        ['Active Subs', metrics.active_subscriptions],
        ['Running Runs', metrics.running_analysis_runs],
        ['Balance Points', metrics.total_balance_points],
      ];
      document.getElementById('metric-grid').innerHTML = entries.map(([label, value]) => `
        <div class="metric">
          <div class="label">${escapeHtml(label)}</div>
          <div class="value">${escapeHtml(value)}</div>
        </div>
      `).join('');
    };

    const renderUserResults = (users) => {
      const target = document.getElementById('user-results');
      if (!users || users.length === 0) {
        target.innerHTML = '<div class="empty">没有找到匹配用户</div>';
        return;
      }
      target.innerHTML = users.map((user) => `
        <div class="user-item">
          <strong>${escapeHtml(user.display_name || user.user_id)}</strong>
          <div class="hint">${escapeHtml(user.user_id)}</div>
          <div class="hint">${escapeHtml(user.email || '')}</div>
          <div class="hint">plan=${escapeHtml(user.plan_tier)} · balance=${escapeHtml(user.balance_points)}</div>
          <button data-user-id="${escapeHtml(user.user_id)}">查看详情</button>
        </div>
      `).join('');

      target.querySelectorAll('button[data-user-id]').forEach((button) => {
        button.addEventListener('click', () => loadUserDetail(button.dataset.userId));
      });
    };

    const renderOverviewTables = (data) => {
      document.getElementById('recent-ledger').innerHTML = renderTable([
        { label: 'Time', render: (row) => row.created_at },
        { label: 'User', render: (row) => `${row.display_name} (${row.user_id})` },
        { label: 'Type', render: (row) => row.entry_type },
        { label: 'Delta', render: (row) => row.points_delta },
        { label: 'Balance', render: (row) => row.balance_after_points },
      ], data.recent_ledger || []);

      document.getElementById('recent-orders').innerHTML = renderTable([
        { label: 'Time', render: (row) => row.created_at },
        { label: 'User', render: (row) => `${row.display_name} (${row.user_id})` },
        { label: 'Package', render: (row) => row.package_code },
        { label: 'Status', render: (row) => row.status },
        { label: 'Points', render: (row) => row.points_amount },
      ], data.recent_orders || []);
    };

    const renderUserDetail = (data) => {
      const user = data.user || {};
      const pointsAccount = data.points_account || {};
      const dailyQuota = data.daily_quota_state || {};
      state.selectedUserId = user.user_id || null;
      document.getElementById('grant-user-id').value = state.selectedUserId || '';

      document.getElementById('user-detail').innerHTML = `
        <div class="detail-grid">
          <div class="mini-card">
            <h3>用户主档</h3>
            ${renderKv([
              ['User ID', user.user_id],
              ['Display Name', user.display_name],
              ['Email', user.email],
              ['Status', user.status],
              ['Plan Tier', data.plan_tier],
            ])}
          </div>
          <div class="mini-card">
            <h3>积分账户</h3>
            ${renderKv([
              ['Balance', pointsAccount.balance_points],
              ['Lifetime Granted', pointsAccount.lifetime_granted_points],
              ['Lifetime Purchased', pointsAccount.lifetime_purchased_points],
              ['Lifetime Spent', pointsAccount.lifetime_spent_points],
              ['Updated At', pointsAccount.updated_at],
            ])}
          </div>
          <div class="mini-card">
            <h3>Guest 日配额</h3>
            ${Object.keys(dailyQuota).length ? renderKv([
              ['Quota Date', dailyQuota.quota_date],
              ['Quota Points', dailyQuota.quota_points],
              ['Applied Delta', dailyQuota.applied_delta_points],
              ['Consumed', dailyQuota.consumed_points],
              ['Reference', dailyQuota.reset_reference_id],
            ]) : '<div class="empty">当前用户没有 daily quota 状态</div>'}
          </div>
          <div class="mini-card">
            <h3>API Keys</h3>
            ${renderTable([
              { label: 'API Key ID', render: (row) => row.api_key_id },
              { label: 'Prefix', render: (row) => row.api_key_prefix },
              { label: 'Last4', render: (row) => row.api_key_last4 },
              { label: 'Status', render: (row) => row.status },
              { label: 'Last Used', render: (row) => row.last_used_at },
            ], data.api_keys || [])}
          </div>
        </div>
        <div class="detail-grid">
          <div class="mini-card">
            <h3>最近账本</h3>
            ${renderTable([
              { label: 'Time', render: (row) => row.created_at },
              { label: 'Entry Type', render: (row) => row.entry_type },
              { label: 'Event', render: (row) => row.event_type },
              { label: 'Delta', render: (row) => row.points_delta },
              { label: 'Balance', render: (row) => row.balance_after_points },
              { label: 'Desc', render: (row) => row.description },
            ], data.recent_ledger || [])}
          </div>
          <div class="mini-card">
            <h3>Usage 摘要</h3>
            ${renderKv([
              ['1d Units', data.usage_summary?.units_1d],
              ['7d Units', data.usage_summary?.units_7d],
              ['30d Units', data.usage_summary?.units_30d],
              ['30d Events', data.usage_summary?.event_count_30d],
            ])}
            <div style="margin-top: 12px;">
              ${renderTable([
                { label: 'Event Type', render: (row) => row.event_type },
                { label: 'Total Units (30d)', render: (row) => row.total_units },
              ], data.usage_by_type_30d || [])}
            </div>
          </div>
        </div>
        <div class="detail-grid">
          <div class="mini-card">
            <h3>订单 / 订阅</h3>
            <div style="margin-bottom: 12px;">
              ${renderTable([
                { label: 'Order', render: (row) => row.order_id },
                { label: 'Package', render: (row) => row.package_code },
                { label: 'Status', render: (row) => row.status },
                { label: 'Points', render: (row) => row.points_amount },
              ], data.recent_orders || [])}
            </div>
            ${renderTable([
              { label: 'Subscription', render: (row) => row.subscription_id },
              { label: 'Package', render: (row) => row.package_code },
              { label: 'Status', render: (row) => row.status },
              { label: 'Monthly Points', render: (row) => row.monthly_points },
            ], data.subscriptions || [])}
          </div>
          <div class="mini-card">
            <h3>会话 / 运行</h3>
            <div style="margin-bottom: 12px;">
              ${renderTable([
                { label: 'Session', render: (row) => row.session_id },
                { label: 'Title', render: (row) => row.title },
                { label: 'Status', render: (row) => row.status },
                { label: 'Updated', render: (row) => row.updated_at },
              ], data.recent_sessions || [])}
            </div>
            ${renderTable([
              { label: 'Run', render: (row) => row.run_id },
              { label: 'Query', render: (row) => row.product_query },
              { label: 'Status', render: (row) => row.status },
              { label: 'Updated', render: (row) => row.updated_at },
            ], data.recent_runs || [])}
          </div>
        </div>
      `;
    };

    const renderAuditLogs = (data) => {
      document.getElementById('audit-logs').innerHTML = renderTable([
        { label: 'Time', render: (row) => row.created_at },
        { label: 'Operator', render: (row) => row.operator_id },
        { label: 'Action', render: (row) => row.action },
        { label: 'Target', render: (row) => `${row.target_type}:${row.target_id || ''}` },
        { label: 'Request', render: (row) => JSON.stringify(row.request_json || {}) },
      ], data.audit_logs || []);
    };

    const loadOverview = async () => {
      setStatus('global-status', '正在加载总览...');
      try {
        const data = await fetchJson('/admin/api/overview');
        renderMetrics(data.metrics || {});
        renderOverviewTables(data);
        setStatus('global-status', '总览已刷新', 'ok');
      } catch (error) {
        setStatus('global-status', error.message, 'error');
      }
    };

    const searchUsers = async (query = '') => {
      setStatus('global-status', query ? `正在搜索 ${query}...` : '正在加载最近用户...');
      try {
        const data = await fetchJson(`/admin/api/users?limit=20&query=${encodeURIComponent(query)}`);
        renderUserResults(data.users || []);
        setStatus('global-status', '用户列表已刷新', 'ok');
      } catch (error) {
        setStatus('global-status', error.message, 'error');
      }
    };

    const loadUserDetail = async (userId) => {
      if (!userId) {
        return;
      }
      setStatus('global-status', `正在加载用户 ${userId}...`);
      try {
        const data = await fetchJson(`/admin/api/users/${encodeURIComponent(userId)}`);
        renderUserDetail(data);
        setStatus('global-status', `用户 ${userId} 已加载`, 'ok');
      } catch (error) {
        setStatus('global-status', error.message, 'error');
      }
    };

    const loadAuditLogs = async () => {
      try {
        const targetId = state.selectedUserId ? `?target_id=${encodeURIComponent(state.selectedUserId)}` : '';
        const data = await fetchJson(`/admin/api/audit-logs${targetId}`);
        renderAuditLogs(data);
      } catch (error) {
        setStatus('global-status', error.message, 'error');
      }
    };

    const grantPoints = async () => {
      const userId = document.getElementById('grant-user-id').value.trim();
      const points = Number(document.getElementById('grant-points').value || 0);
      const description = document.getElementById('grant-description').value.trim();
      if (!userId) {
        setStatus('grant-status', '请先填写目标 user_id', 'error');
        return;
      }
      if (!Number.isFinite(points) || points <= 0) {
        setStatus('grant-status', '积分必须大于 0', 'error');
        return;
      }

      setStatus('grant-status', '正在执行加积分...');
      try {
        await fetchJson(`/admin/api/users/${encodeURIComponent(userId)}/grant-points`, {
          method: 'POST',
          body: JSON.stringify({
            points,
            description,
          }),
        });
        setStatus('grant-status', '加积分成功', 'ok');
        await loadUserDetail(userId);
        await loadAuditLogs();
        await loadOverview();
      } catch (error) {
        setStatus('grant-status', error.message, 'error');
      }
    };

    document.getElementById('load-overview').addEventListener('click', loadOverview);
    document.getElementById('load-audit').addEventListener('click', loadAuditLogs);
    document.getElementById('search-users').addEventListener('click', () => searchUsers(document.getElementById('user-query').value.trim()));
    document.getElementById('search-all').addEventListener('click', () => searchUsers(''));
    document.getElementById('grant-submit').addEventListener('click', grantPoints);

    const savedToken = localStorage.getItem('xiamimate_admin_token');
    const savedOperator = localStorage.getItem('xiamimate_admin_operator');
    if (savedToken) {
      document.getElementById('admin-token').value = savedToken;
    }
    if (savedOperator) {
      document.getElementById('admin-operator').value = savedOperator;
    }

    loadOverview().catch(() => {});
    searchUsers('').catch(() => {});
    loadAuditLogs().catch(() => {});
  </script>
</body>
</html>
"""