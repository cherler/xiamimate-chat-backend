from __future__ import annotations


def render_admin_backoffice_html() -> str:
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>XiaMimate 管理后台</title>
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

    .hero > *,
    .layout > * {
      min-width: 0;
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
      min-width: 0;
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
      letter-spacing: 0.04em;
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
      min-width: 0;
    }

    .detail-grid.full {
      grid-template-columns: 1fr;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      table-layout: fixed;
    }

    .scroll-window {
      width: 100%;
      min-width: 0;
      max-height: 320px;
      overflow: auto;
      overscroll-behavior: contain;
      border: 1px solid rgba(17, 75, 95, 0.08);
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.58);
    }

    .scroll-window.tall {
      max-height: 420px;
    }

    .scroll-stack {
      max-height: 420px;
      overflow: auto;
      overscroll-behavior: contain;
      padding-right: 4px;
    }

    th,
    td {
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid rgba(17, 75, 95, 0.08);
      vertical-align: top;
      overflow-wrap: anywhere;
      word-break: break-word;
    }

    th {
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.04em;
      position: sticky;
      top: 0;
      background: rgba(255, 251, 245, 0.98);
      z-index: 1;
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

    .section-list,
    .mini-card {
      min-width: 0;
    }

    .ops-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }

    .module-card {
      display: flex;
      flex-direction: column;
      min-height: 320px;
      max-height: 440px;
      overflow: hidden;
    }

    .module-card-head {
      display: grid;
      gap: 6px;
      margin-bottom: 12px;
    }

    .module-card-body {
      flex: 1;
      overflow: auto;
      overscroll-behavior: contain;
      padding-right: 4px;
    }

    @media (max-width: 1100px) {
      .hero,
      .layout,
      .detail-grid,
      .ops-grid {
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
        <div class="eyebrow">后台管理</div>
        <h1>XiaMimate Chat Backend</h1>
        <p>这是一版内置在 chat_backend 里的最小后台。它覆盖四件事：看清用户账务、看清订单/订阅、带审计地人工加积分，以及主动广播系统通知。</p>
      </div>
      <div class="card hero-side">
        <div id="admin-token-group">
          <label for="admin-token">后台令牌</label>
          <input id="admin-token" type="password" placeholder="请输入 Bearer Token" />
        </div>
        <div>
          <label for="admin-operator">操作人</label>
          <input id="admin-operator" type="text" placeholder="例如 ops-liu" />
        </div>
        <p id="admin-auth-hint" class="hint">当前仍是固定后台令牌模式。页面只在当前浏览器会话内缓存令牌，不再写入长期本地存储。</p>
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
            <label for="user-query">用户 ID / 邮箱 / 显示名</label>
            <input id="user-query" type="text" placeholder="guest、邮箱或用户 ID" />
          </div>
          <div class="button-row">
            <button id="search-users">搜索用户</button>
            <button id="search-all" class="secondary">最近用户</button>
          </div>
        </div>
        <div class="scroll-stack" style="margin-top: 14px;">
          <div id="user-results" class="user-list"></div>
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
          <h2>管理操作</h2>
          <div class="ops-grid">
            <section class="mini-card module-card">
              <div class="module-card-head">
                <h3>人工加积分</h3>
                <div class="hint">对指定用户做带审计的人工补额，适合补单、客诉补偿和运营灰度。</div>
              </div>
              <div class="module-card-body">
                <div class="field-grid">
                  <div>
                    <label for="grant-user-id">目标用户 ID</label>
                    <input id="grant-user-id" type="text" placeholder="先从左侧检索或右侧详情填充" />
                  </div>
                  <div>
                    <label for="grant-points">积分数</label>
                    <input id="grant-points" type="number" min="1" value="100" />
                  </div>
                  <div>
                    <label for="grant-description">说明</label>
                    <textarea id="grant-description" placeholder="例如：手工补单 / 客诉补偿 / 灰度测试加额"></textarea>
                  </div>
                  <button id="grant-submit" class="warn">执行加积分</button>
                  <div id="grant-status" class="status"></div>
                </div>
              </div>
            </section>

            <section class="mini-card module-card">
              <div class="module-card-head">
                <h3>系统通知广播</h3>
                <div class="hint">向通知中心批量投递系统消息，可附带跳转链接与展示级别。</div>
              </div>
              <div class="module-card-body">
                <div class="field-grid">
                  <div>
                    <label for="broadcast-title">通知标题</label>
                    <input id="broadcast-title" type="text" placeholder="例如：五一期间客服响应时间调整" />
                  </div>
                  <div>
                    <label for="broadcast-tag">标签</label>
                    <input id="broadcast-tag" type="text" value="系统通知" />
                  </div>
                  <div>
                    <label for="broadcast-level">级别</label>
                    <input id="broadcast-level" type="text" value="info" placeholder="info / success / warning / error" />
                  </div>
                  <div>
                    <label for="broadcast-action-url">跳转链接（可选）</label>
                    <input id="broadcast-action-url" type="text" placeholder="例如：/portal/guide" />
                  </div>
                  <div>
                    <label for="broadcast-body">通知正文</label>
                    <textarea id="broadcast-body" placeholder="请输入要推送到通知中心系统通知中的内容"></textarea>
                  </div>
                  <button id="broadcast-submit" class="warn">发送系统通知</button>
                  <div id="broadcast-status" class="status"></div>
                </div>
              </div>
            </section>

            <section class="mini-card module-card">
              <div class="module-card-head">
                <h3>计价管理</h3>
                <div class="hint">统一维护事件计价和展示顺序，卡片内部支持滚动查看完整配置。</div>
              </div>
              <div class="module-card-body">
                <div id="pricing-list" class="field-grid" style="margin-bottom: 10px;"></div>
                <div class="button-row">
                  <button id="load-pricing" class="secondary">刷新计价</button>
                </div>
                <div id="pricing-status" class="status"></div>
              </div>
            </section>

            <section class="mini-card module-card">
              <div class="module-card-head">
                <h3>站点联络配置</h3>
                <div class="hint">管理门户页顶部联络入口：联系邮箱、企微二维码、公众号二维码、意见反馈链接。</div>
              </div>
              <div class="module-card-body">
                <div id="site-config-list" class="field-grid" style="margin-bottom: 10px;"></div>
                <div class="button-row">
                  <button id="load-site-config" class="secondary">刷新联络配置</button>
                </div>
                <div id="site-config-status" class="status"></div>
              </div>
            </section>

            <section class="mini-card module-card">
              <div class="module-card-head">
                <h3>邮箱验证码风控</h3>
                <div class="hint">单独管理邮箱验证码的限流、次数、配额和锁定策略，方便运营按场景调参。</div>
              </div>
              <div class="module-card-body">
                <div id="email-verification-config-list" class="field-grid" style="margin-bottom: 10px;"></div>
                <div class="button-row">
                  <button id="load-email-verification-config" class="secondary">刷新风控配置</button>
                </div>
                <div id="email-verification-config-status" class="status"></div>
              </div>
            </section>
          </div>
        </section>

        <section class="card panel">
          <h2>后台审计</h2>
          <div id="audit-logs"></div>
        </section>

        <section class="card panel">
          <h2>系统广播记录</h2>
          <div id="broadcast-history"></div>
        </section>
      </main>
    </section>
  </div>

  <script>
    const state = {
      selectedUserId: null,
      authMode: 'fixed-token',
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

    const ledgerEntryTypeLabels = {
      consume: '消费',
      refund: '退款',
      grant: '赠送',
      recharge: '充值到账',
      signup_gift: '注册赠送',
      admin_grant: '后台加积分',
      subscription_grant: '订阅发放',
      promotion_reward: '活动奖励',
      subscription_expire: '套餐到期清零',
      daily_quota_reset: '每日额度重置',
    };

    const ledgerEventTypeLabels = {
      llm_request: 'LLM 请求',
      workflow_run: 'Workflow 请求',
      kb_retrieve: '知识库检索',
      dify_knowledge_retrieve: '知识库检索',
      product_api_call: '商品 API 检索',
      web_search: '网络搜索',
      recharge: '充值到账',
      signup_gift: '新用户注册赠送',
      referral_invited_reward: '绑定邀请码奖励',
      referral_inviter_reward: '邀请新用户注册奖励',
      subscription_grant: '订阅积分发放',
      subscription_expire: '套餐到期清零',
      daily_quota_reset: '每日额度重置',
      admin_grant: '后台加积分',
      promotion_reward: '活动奖励',
    };

    const localizeLedgerEntryType = (entryType, eventType = '') => {
      const normalized = String(entryType || '').trim().toLowerCase();
      if (normalized && ledgerEntryTypeLabels[normalized]) {
        return ledgerEntryTypeLabels[normalized];
      }
      return localizeLedgerEventType(eventType) || String(entryType || '');
    };

    const localizeLedgerEventType = (eventType) => {
      const normalized = String(eventType || '').trim().toLowerCase();
      return ledgerEventTypeLabels[normalized] || String(eventType || '');
    };

    const applyTrustedAdminMode = () => {
      state.authMode = 'trusted-openwebui-admin';
      const tokenGroup = document.getElementById('admin-token-group');
      const tokenInput = document.getElementById('admin-token');
      const authHint = document.getElementById('admin-auth-hint');
      tokenGroup.style.display = 'none';
      tokenInput.value = '';
      tokenInput.disabled = true;
      authHint.textContent = '当前通过 Open WebUI 管理员会话访问，无需填写后台令牌。仍建议填写操作人，便于后台审计。';
      if (!getOperator()) {
        document.getElementById('admin-operator').value = localStorage.getItem('xiamimate_admin_operator') || 'openwebui-admin';
      }
    };

    const detectAuthMode = async () => {
      try {
        const response = await fetch('/api/v1/users/user/settings', {
          credentials: 'same-origin',
          redirect: 'manual',
        });
        if (response.ok) {
          applyTrustedAdminMode();
        }
      } catch (error) {
      }
    };

    const authHeaders = () => {
      const operator = getOperator();
      if (!operator) {
        throw new Error('请先填写操作人');
      }
      localStorage.setItem('xiamimate_admin_operator', operator);
      if (state.authMode === 'trusted-openwebui-admin') {
        return {
          'X-Admin-Operator': operator,
        };
      }
      const token = getToken();
      if (!token) {
        throw new Error('请先填写后台令牌');
      }
      sessionStorage.setItem('xiamimate_admin_token', token);
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
      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) {
        const rawText = await response.text();
        if (response.status === 401 || response.status === 403 || response.status === 302) {
          throw new Error('当前管理员登录态已失效，请返回 Open WebUI 重新登录后再试');
        }
        throw new Error(rawText.slice(0, 120) || `HTTP ${response.status}`);
      }
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

    const renderTable = (columns, rows, options = {}) => {
      if (!rows || rows.length === 0) {
        return '<div class="empty">暂无数据</div>';
      }
      return `
        <div class="scroll-window ${escapeHtml(options.className || '')}">
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
        </div>
      `;
    };

    const renderMetrics = (metrics) => {
      const entries = [
        ['总用户数', metrics.total_users],
        ['活跃 API Key', metrics.active_api_keys],
        ['已支付订单', metrics.paid_orders],
        ['生效订阅', metrics.active_subscriptions],
        ['运行中分析', metrics.running_analysis_runs],
        ['账户总积分', metrics.total_balance_points],
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
          <div class="hint">套餐=${escapeHtml(user.plan_tier)} · 积分=${escapeHtml(user.balance_points)}</div>
          <button data-user-id="${escapeHtml(user.user_id)}">查看详情</button>
        </div>
      `).join('');

      target.querySelectorAll('button[data-user-id]').forEach((button) => {
        button.addEventListener('click', () => loadUserDetail(button.dataset.userId));
      });
    };

    const renderOverviewTables = (data) => {
      document.getElementById('recent-ledger').innerHTML = renderTable([
        { label: '时间', render: (row) => row.created_at },
        { label: '用户', render: (row) => `${row.display_name} (${row.user_id})` },
        { label: '类型', render: (row) => localizeLedgerEntryType(row.entry_type, row.event_type) },
        { label: '事件', render: (row) => localizeLedgerEventType(row.event_type) },
        { label: '变动', render: (row) => row.points_delta },
        { label: '变动后余额', render: (row) => row.balance_after_points },
      ], data.recent_ledger || []);

      document.getElementById('recent-orders').innerHTML = renderTable([
        { label: '时间', render: (row) => row.created_at },
        { label: '用户', render: (row) => `${row.display_name} (${row.user_id})` },
        { label: '套餐', render: (row) => row.package_code },
        { label: '状态', render: (row) => row.status },
        { label: '积分', render: (row) => row.points_amount },
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
              ['用户 ID', user.user_id],
              ['显示名', user.display_name],
              ['Email', user.email],
              ['状态', user.status],
              ['套餐层级', data.plan_tier],
            ])}
          </div>
          <div class="mini-card">
            <h3>积分账户</h3>
            ${renderKv([
              ['当前余额', pointsAccount.balance_points],
              ['累计发放', pointsAccount.lifetime_granted_points],
              ['累计购买', pointsAccount.lifetime_purchased_points],
              ['累计消耗', pointsAccount.lifetime_spent_points],
              ['更新时间', pointsAccount.updated_at],
            ])}
          </div>
          <div class="mini-card">
            <h3>Guest 日配额</h3>
            ${Object.keys(dailyQuota).length ? renderKv([
              ['配额日期', dailyQuota.quota_date],
              ['配额积分', dailyQuota.quota_points],
              ['已补差额', dailyQuota.applied_delta_points],
              ['已消耗', dailyQuota.consumed_points],
              ['重置参考', dailyQuota.reset_reference_id],
            ]) : '<div class="empty">当前用户没有 daily quota 状态</div>'}
          </div>
          <div class="mini-card">
            <h3>API Keys</h3>
            ${renderTable([
              { label: 'API Key ID', render: (row) => row.api_key_id },
              { label: '前缀', render: (row) => row.api_key_prefix },
              { label: '末四位', render: (row) => row.api_key_last4 },
              { label: '状态', render: (row) => row.status },
              { label: '最后使用时间', render: (row) => row.last_used_at },
            ], data.api_keys || [])}
          </div>
        </div>
        <div class="detail-grid">
          <div class="mini-card">
            <h3>最近账本</h3>
            ${renderTable([
              { label: '时间', render: (row) => row.created_at },
                { label: '账本类型', render: (row) => localizeLedgerEntryType(row.entry_type, row.event_type) },
                { label: '事件', render: (row) => localizeLedgerEventType(row.event_type) },
              { label: '变动', render: (row) => row.points_delta },
              { label: '变动后余额', render: (row) => row.balance_after_points },
              { label: '说明', render: (row) => row.description },
            ], data.recent_ledger || [])}
          </div>
          <div class="mini-card">
            <h3>使用摘要</h3>
            ${renderKv([
              ['近 1 天调用量', data.usage_summary?.units_1d],
              ['近 7 天调用量', data.usage_summary?.units_7d],
              ['近 30 天调用量', data.usage_summary?.units_30d],
              ['近 30 天事件数', data.usage_summary?.event_count_30d],
            ])}
            <div style="margin-top: 12px;">
              ${renderTable([
                { label: '事件类型', render: (row) => localizeLedgerEventType(row.event_type) },
                { label: '近 30 天总调用量', render: (row) => row.total_units },
              ], data.usage_by_type_30d || [])}
            </div>
          </div>
        </div>
        <div class="detail-grid">
          <div class="mini-card">
            <h3>订单 / 订阅</h3>
            <div style="margin-bottom: 12px;">
              ${renderTable([
                { label: '订单 ID', render: (row) => row.order_id },
                { label: '套餐', render: (row) => row.package_code },
                { label: '状态', render: (row) => row.status },
                { label: '积分', render: (row) => row.points_amount },
              ], data.recent_orders || [])}
            </div>
            ${renderTable([
              { label: '订阅 ID', render: (row) => row.subscription_id },
              { label: '套餐', render: (row) => row.package_code },
              { label: '状态', render: (row) => row.status },
              { label: '月度积分', render: (row) => row.monthly_points },
            ], data.subscriptions || [])}
          </div>
          <div class="mini-card">
            <h3>会话 / 运行</h3>
            <div style="margin-bottom: 12px;">
              ${renderTable([
                { label: '会话 ID', render: (row) => row.session_id },
                { label: '标题', render: (row) => row.title },
                { label: '状态', render: (row) => row.status },
                { label: '更新时间', render: (row) => row.updated_at },
              ], data.recent_sessions || [])}
            </div>
            ${renderTable([
              { label: '运行 ID', render: (row) => row.run_id },
              { label: '查询词', render: (row) => row.product_query },
              { label: '状态', render: (row) => row.status },
              { label: '更新时间', render: (row) => row.updated_at },
            ], data.recent_runs || [])}
          </div>
        </div>
      `;
    };

    const renderAuditLogs = (data) => {
      document.getElementById('audit-logs').innerHTML = renderTable([
        { label: '时间', render: (row) => row.created_at },
        { label: '操作人', render: (row) => row.operator_id },
        { label: '动作', render: (row) => row.action },
        { label: '目标', render: (row) => `${row.target_type}:${row.target_id || ''}` },
        { label: '请求体', render: (row) => JSON.stringify(row.request_json || {}) },
      ], data.audit_logs || [], { className: 'tall' });
    };

    const renderBroadcastHistory = (data) => {
      document.getElementById('broadcast-history').innerHTML = renderTable([
        { label: '发送时间', render: (row) => row.created_at },
        { label: '操作人', render: (row) => row.operator_id },
        { label: '标签', render: (row) => row.tag },
        { label: '级别', render: (row) => row.level },
        { label: '标题', render: (row) => row.title },
        { label: '覆盖用户数', render: (row) => row.delivered_user_count },
        { label: '跳转链接', render: (row) => row.action_url || '-' },
      ], data.system_notifications || [], { className: 'tall' });
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

    const loadBroadcasts = async () => {
      try {
        const data = await fetchJson('/admin/api/system-notifications?limit=20');
        renderBroadcastHistory(data);
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

    const sendBroadcast = async () => {
      const title = document.getElementById('broadcast-title').value.trim();
      const tag = document.getElementById('broadcast-tag').value.trim() || '系统通知';
      const level = document.getElementById('broadcast-level').value.trim() || 'info';
      const actionUrl = document.getElementById('broadcast-action-url').value.trim();
      const body = document.getElementById('broadcast-body').value.trim();
      if (!title) {
        setStatus('broadcast-status', '请先填写通知标题', 'error');
        return;
      }
      if (!body) {
        setStatus('broadcast-status', '请先填写通知正文', 'error');
        return;
      }

      setStatus('broadcast-status', '正在发送系统通知...');
      try {
        const data = await fetchJson('/admin/api/system-notifications', {
          method: 'POST',
          body: JSON.stringify({
            title,
            tag,
            level,
            action_url: actionUrl || null,
            body,
          }),
        });
        document.getElementById('broadcast-title').value = '';
        document.getElementById('broadcast-action-url').value = '';
        document.getElementById('broadcast-body').value = '';
        setStatus('broadcast-status', `发送成功，已覆盖 ${data.broadcast?.delivered_user_count || 0} 个用户`, 'ok');
        await loadBroadcasts();
      } catch (error) {
        setStatus('broadcast-status', error.message, 'error');
      }
    };

    const renderPricingList = (rows) => {
      const target = document.getElementById('pricing-list');
      if (!rows || rows.length === 0) {
        target.innerHTML = '<div class="empty">暂无计价配置</div>';
        return;
      }

      target.innerHTML = rows.map((row) => `
        <div class="mini-card" data-pricing-card="${escapeHtml(row.event_type)}">
          <div style="display:grid; gap:10px;">
            <div>
              <strong>${escapeHtml(row.display_name || row.event_type)}</strong>
              <div class="hint">event_type = ${escapeHtml(row.event_type)}</div>
            </div>
            <div class="detail-grid">
              <div>
                <label for="pricing-name-${escapeHtml(row.event_type)}">显示名称</label>
                <input id="pricing-name-${escapeHtml(row.event_type)}" type="text" value="${escapeHtml(row.display_name || '')}" />
              </div>
              <div>
                <label for="pricing-points-${escapeHtml(row.event_type)}">积分/次</label>
                <input id="pricing-points-${escapeHtml(row.event_type)}" type="number" min="0" value="${escapeHtml(row.points_per_unit)}" />
              </div>
              <div>
                <label for="pricing-order-${escapeHtml(row.event_type)}">排序</label>
                <input id="pricing-order-${escapeHtml(row.event_type)}" type="number" value="${escapeHtml(row.display_order)}" />
              </div>
              <div>
                <label for="pricing-status-${escapeHtml(row.event_type)}">状态</label>
                <select id="pricing-status-${escapeHtml(row.event_type)}" style="width:100%; border:1px solid rgba(17, 75, 95, 0.18); border-radius:14px; background:rgba(255,255,255,0.92); padding:12px 14px; color:var(--ink);">
                  <option value="active" ${row.status === 'active' ? 'selected' : ''}>active</option>
                  <option value="disabled" ${row.status === 'disabled' ? 'selected' : ''}>disabled</option>
                </select>
              </div>
            </div>
            <div class="button-row">
              <button class="secondary" data-save-pricing="${escapeHtml(row.event_type)}">保存计价</button>
            </div>
          </div>
        </div>
      `).join('');

      target.querySelectorAll('button[data-save-pricing]').forEach((button) => {
        button.addEventListener('click', () => savePricing(button.dataset.savePricing));
      });
    };

    const loadPricing = async () => {
      setStatus('pricing-status', '正在加载计价配置...');
      try {
        const data = await fetchJson('/admin/api/pricing');
        renderPricingList(data.event_pricing || []);
        setStatus('pricing-status', `计价已刷新，版本 ${data.pricing_version || '-'}`, 'ok');
      } catch (error) {
        setStatus('pricing-status', error.message, 'error');
      }
    };

    const savePricing = async (eventType) => {
      if (!eventType) {
        setStatus('pricing-status', '缺少 event_type', 'error');
        return;
      }

      const displayName = document.getElementById(`pricing-name-${eventType}`)?.value.trim() || eventType;
      const rawPoints = Number(document.getElementById(`pricing-points-${eventType}`)?.value || 0);
      const rawOrder = Number(document.getElementById(`pricing-order-${eventType}`)?.value || 0);
      const status = document.getElementById(`pricing-status-${eventType}`)?.value || 'active';

      if (!Number.isFinite(rawPoints) || rawPoints < 0) {
        setStatus('pricing-status', '积分单价必须是大于等于 0 的整数', 'error');
        return;
      }
      if (!Number.isFinite(rawOrder)) {
        setStatus('pricing-status', '排序必须是整数', 'error');
        return;
      }

      setStatus('pricing-status', `正在保存 ${displayName}...`);
      try {
        await fetchJson(`/admin/api/pricing/${encodeURIComponent(eventType)}`, {
          method: 'PUT',
          body: JSON.stringify({
            display_name: displayName,
            points_per_unit: Math.trunc(rawPoints),
            display_order: Math.trunc(rawOrder),
            status,
          }),
        });
        setStatus('pricing-status', `${displayName} 已更新`, 'ok');
        await loadPricing();
        await loadOverview();
        if (state.selectedUserId) {
          await loadUserDetail(state.selectedUserId);
        }
      } catch (error) {
        setStatus('pricing-status', error.message, 'error');
      }
    };

    const siteConfigInputType = (key) => {
      if (key === 'wechat_qr_base64' || key === 'official_account_qr_base64') return 'file';
      if (key === 'feedback_url') return 'url';
      return 'text';
    };

    const SITE_CONFIG_IMAGE_FILE_MAX_BYTES = 2 * 1024 * 1024;
    const SITE_CONFIG_DATA_URL_MAX_LENGTH = 3_000_000;

    const siteConfigDescriptions = {
      contact_email: '顶部“邮件”按钮使用的联系邮箱。',
      wechat_qr_base64: '顶部“企微”按钮弹窗展示的二维码图片，建议上传清晰正方形图片。',
      official_account_qr_base64: '顶部“公众号”按钮弹窗展示的二维码图片，建议上传清晰正方形图片。',
      feedback_url: '顶部“反馈”按钮跳转的外部意见收集链接。',
      email_verification_request_ip_window_seconds: '验证码发送接口按 IP 统计的时间窗口，单位秒。',
      email_verification_request_ip_max_attempts: '同一 IP 在发送窗口内最多可请求多少次验证码。',
      email_verification_confirm_ip_window_seconds: '验证码确认接口按 IP 统计的时间窗口，单位秒。',
      email_verification_confirm_ip_max_attempts: '同一 IP 在确认窗口内最多可提交多少次验证码。',
      email_verification_daily_send_limit_per_user: '同一登录用户每天最多发送多少次验证码。',
      email_verification_daily_send_limit_per_email: '同一邮箱每天最多可收到多少次验证码。',
      email_verification_max_failed_attempts: '单个验证码 challenge 最多允许输错几次。',
      email_verification_lock_seconds: '输错达到上限后锁定多久，单位秒。',
    };

    const siteContactConfigGroups = [
      {
        key: 'site_contact',
        title: '站点联络配置',
        description: '管理顶部联络入口和外部反馈信息。',
        keys: ['contact_email', 'wechat_qr_base64', 'official_account_qr_base64', 'feedback_url'],
      },
    ];

    const emailVerificationConfigGroups = [
      {
        key: 'email_verification_basic',
        title: '验证码风控 · 基础推荐',
        description: '建议优先调整发送频率、确认频率和单日发送配额，覆盖常见刷接口场景。',
        keys: [
          'email_verification_request_ip_window_seconds',
          'email_verification_request_ip_max_attempts',
          'email_verification_confirm_ip_window_seconds',
          'email_verification_confirm_ip_max_attempts',
          'email_verification_daily_send_limit_per_user',
          'email_verification_daily_send_limit_per_email',
        ],
      },
      {
        key: 'email_verification_strict',
        title: '验证码风控 · 严格模式',
        description: '攻击明显时再收紧这一组，主要控制验证码输错后的封禁强度。',
        keys: [
          'email_verification_max_failed_attempts',
          'email_verification_lock_seconds',
        ],
      },
    ];

    const emailVerificationConfigKeys = new Set(emailVerificationConfigGroups.flatMap((group) => group.keys));

    const renderSiteConfigCard = (row) => {
      const inputType = siteConfigInputType(row.config_key);
      const description = siteConfigDescriptions[row.config_key] || '';
      if (inputType === 'file') {
        const previewHtml = row.config_value
          ? `<img src="${escapeHtml(row.config_value)}" style="max-width:120px;max-height:120px;border-radius:8px;margin-top:6px;" />`
          : '<div class="hint">暂无图片</div>';
        return `
          <div class="mini-card" data-site-config-card="${escapeHtml(row.config_key)}">
            <div style="display:grid; gap:10px;">
              <div>
                <strong>${escapeHtml(row.display_name || row.config_key)}</strong>
                <div class="hint">config_key = ${escapeHtml(row.config_key)}</div>
                ${description ? `<div class="hint" style="margin-top:6px;line-height:1.6;">${escapeHtml(description)}</div>` : ''}
              </div>
              ${previewHtml}
              <div>
                <label for="site-config-file-${escapeHtml(row.config_key)}">上传新图片</label>
                <input id="site-config-file-${escapeHtml(row.config_key)}" type="file" accept="image/*" style="width:100%;" />
              </div>
              <div class="button-row">
                <button class="secondary" data-save-site-config="${escapeHtml(row.config_key)}" data-input-type="file">保存</button>
              </div>
            </div>
          </div>
        `;
      }
      return `
        <div class="mini-card" data-site-config-card="${escapeHtml(row.config_key)}">
          <div style="display:grid; gap:10px;">
            <div>
              <strong>${escapeHtml(row.display_name || row.config_key)}</strong>
              <div class="hint">config_key = ${escapeHtml(row.config_key)}</div>
              ${description ? `<div class="hint" style="margin-top:6px;line-height:1.6;">${escapeHtml(description)}</div>` : ''}
            </div>
            <div>
              <label for="site-config-val-${escapeHtml(row.config_key)}">值</label>
              <input id="site-config-val-${escapeHtml(row.config_key)}" type="${inputType}" value="${escapeHtml(row.config_value || '')}" />
            </div>
            <div class="button-row">
              <button class="secondary" data-save-site-config="${escapeHtml(row.config_key)}" data-input-type="text">保存</button>
            </div>
          </div>
        </div>
      `;
    };

    const renderSiteConfigGroup = (group, rows) => {
      if (!rows || rows.length === 0) return '';
      return `
        <div style="grid-column:1 / -1; display:grid; gap:12px; margin-bottom:4px;">
          <div>
            <div style="font-size:0.95rem; font-weight:700; color:#1f2937;">${escapeHtml(group.title)}</div>
            <div class="hint" style="margin-top:4px; line-height:1.6;">${escapeHtml(group.description || '')}</div>
          </div>
          <div class="field-grid">${rows.map(renderSiteConfigCard).join('')}</div>
        </div>
      `;
    };

    const renderGroupedSiteConfigList = ({ rows, targetId, groups, emptyText, remainingGroup = null }) => {
      const target = document.getElementById(targetId);
      if (!rows || rows.length === 0) {
        target.innerHTML = `<div class="empty">${escapeHtml(emptyText)}</div>`;
        return;
      }

      const rowByKey = new Map(rows.map((row) => [row.config_key, row]));
      const groupedKeys = new Set();
      const groupedSectionsHtml = groups.map((group) => {
        const groupRows = group.keys
          .map((key) => rowByKey.get(key))
          .filter(Boolean);
        groupRows.forEach((row) => groupedKeys.add(row.config_key));
        return renderSiteConfigGroup(group, groupRows);
      }).join('');

      const remainingRows = rows.filter((row) => !groupedKeys.has(row.config_key));
      const remainingHtml = remainingGroup && remainingRows.length
        ? renderSiteConfigGroup(remainingGroup, remainingRows)
        : '';

      target.innerHTML = groupedSectionsHtml + remainingHtml;

      target.querySelectorAll('button[data-save-site-config]').forEach((button) => {
        button.addEventListener('click', () => saveSiteConfig(button.dataset.saveSiteConfig, button.dataset.inputType));
      });
    };

    const renderSiteContactConfigList = (rows) => {
      const siteContactRows = rows.filter((row) => !emailVerificationConfigKeys.has(row.config_key));
      renderGroupedSiteConfigList({
        rows: siteContactRows,
        targetId: 'site-config-list',
        groups: siteContactConfigGroups,
        emptyText: '暂无站点联络配置',
        remainingGroup: {
          title: '其他站点配置',
          description: '不属于顶部联络入口的其他后台配置项。',
        },
      });
    };

    const renderEmailVerificationConfigList = (rows) => {
      renderGroupedSiteConfigList({
        rows: rows.filter((row) => emailVerificationConfigKeys.has(row.config_key)),
        targetId: 'email-verification-config-list',
        groups: emailVerificationConfigGroups,
        emptyText: '暂无邮箱验证码风控配置',
      });
    };

    const siteConfigStatusId = (configKey) => emailVerificationConfigKeys.has(configKey)
      ? 'email-verification-config-status'
      : 'site-config-status';

    const loadSiteConfig = async () => {
      setStatus('site-config-status', '正在加载联络配置...');
      setStatus('email-verification-config-status', '正在加载风控配置...');
      try {
        const data = await fetchJson('/admin/api/site-config');
        const rows = data.site_config || [];
        renderSiteContactConfigList(rows);
        renderEmailVerificationConfigList(rows);
        setStatus('site-config-status', '联络配置已刷新', 'ok');
        setStatus('email-verification-config-status', '风控配置已刷新', 'ok');
      } catch (error) {
        setStatus('site-config-status', error.message, 'error');
        setStatus('email-verification-config-status', error.message, 'error');
      }
    };

    const saveSiteConfig = async (configKey, inputType) => {
      if (!configKey) {
        setStatus('site-config-status', '缺少 config_key', 'error');
        return;
      }

      const statusId = siteConfigStatusId(configKey);

      let configValue = '';
      if (inputType === 'file') {
        const fileInput = document.getElementById(`site-config-file-${configKey}`);
        const file = fileInput && fileInput.files && fileInput.files[0];
        if (!file) {
          setStatus(statusId, '请先选择文件', 'error');
          return;
        }
        if (file.size > SITE_CONFIG_IMAGE_FILE_MAX_BYTES) {
          setStatus(statusId, '图片过大，请压缩到 2MB 以内再上传', 'error');
          return;
        }
        configValue = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = () => reject(new Error('文件读取失败'));
          reader.readAsDataURL(file);
        });
        if (String(configValue || '').length > SITE_CONFIG_DATA_URL_MAX_LENGTH) {
          setStatus(statusId, '图片编码后仍然过大，请继续压缩后再上传', 'error');
          return;
        }
      } else {
        configValue = document.getElementById(`site-config-val-${configKey}`)?.value || '';
      }

      setStatus(statusId, `正在保存 ${configKey}...`);
      try {
        await fetchJson(`/admin/api/site-config/${encodeURIComponent(configKey)}`, {
          method: 'PUT',
          body: JSON.stringify({ config_value: configValue }),
        });
        setStatus(statusId, `${configKey} 已更新`, 'ok');
        await loadSiteConfig();
      } catch (error) {
        setStatus(statusId, error.message, 'error');
      }
    };

    document.getElementById('load-overview').addEventListener('click', loadOverview);
    document.getElementById('load-audit').addEventListener('click', loadAuditLogs);
    document.getElementById('load-pricing').addEventListener('click', loadPricing);
    document.getElementById('load-site-config').addEventListener('click', loadSiteConfig);
    document.getElementById('load-email-verification-config').addEventListener('click', loadSiteConfig);
    document.getElementById('search-users').addEventListener('click', () => searchUsers(document.getElementById('user-query').value.trim()));
    document.getElementById('search-all').addEventListener('click', () => searchUsers(''));
    document.getElementById('grant-submit').addEventListener('click', grantPoints);
    document.getElementById('broadcast-submit').addEventListener('click', sendBroadcast);

    const savedToken = sessionStorage.getItem('xiamimate_admin_token');
    const savedOperator = localStorage.getItem('xiamimate_admin_operator');
    if (savedToken) {
      document.getElementById('admin-token').value = savedToken;
    }
    if (savedOperator) {
      document.getElementById('admin-operator').value = savedOperator;
    }

    detectAuthMode().finally(() => {
      loadOverview().catch(() => {});
      loadPricing().catch(() => {});
      loadSiteConfig().catch(() => {});
      searchUsers('').catch(() => {});
      loadAuditLogs().catch(() => {});
      loadBroadcasts().catch(() => {});
    });
  </script>
</body>
</html>
"""