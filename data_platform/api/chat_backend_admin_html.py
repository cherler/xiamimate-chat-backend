from __future__ import annotations


def render_admin_backoffice_html(*, trusted_openwebui_admin: bool = False) -> str:
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
      --shell-max-width: 1880px;
      --shell-padding: 18px;
      --layout-gap: 16px;
      --panel-padding: 16px;
      --section-gap: 12px;
      --surface-radius: 20px;
      --topbar-offset: 10px;
      --topbar-height: 78px;
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
      max-width: var(--shell-max-width);
      margin: 0 auto;
      padding: calc(var(--topbar-height) + var(--topbar-offset) + var(--layout-gap)) var(--shell-padding) var(--shell-padding);
    }

    .hero {
      position: fixed;
      top: var(--topbar-offset);
      left: max(var(--shell-padding), calc((100vw - var(--shell-max-width)) / 2));
      right: max(var(--shell-padding), calc((100vw - var(--shell-max-width)) / 2));
      z-index: 40;
    }

    .hero > *,
    .layout > * {
      min-width: 0;
    }

    .card {
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: var(--surface-radius);
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }

    h1 {
      margin: 0;
      font-family: "Space Grotesk", "Avenir Next", sans-serif;
      font-size: 32px;
      line-height: 1.1;
    }

    .hint {
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }

    .hero-header {
      min-height: var(--topbar-height);
      padding: 10px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--section-gap);
      flex-wrap: wrap;
      background: rgba(255, 251, 245, 0.94);
    }

    .hero-controls {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: var(--section-gap);
      flex-wrap: wrap;
      flex: 0 1 auto;
      margin-left: auto;
    }

    .hero-control {
      min-width: 0;
      flex: 0 1 auto;
    }

    .hero-inline-field {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .hero-inline-field label {
      margin: 0;
      white-space: nowrap;
    }

    .hero-inline-field input {
      min-width: 220px;
    }

    .hero-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .hero-status {
      min-width: 0;
      max-width: 340px;
      text-align: left;
    }

    .layout {
      display: grid;
      grid-template-columns: 400px minmax(0, 1fr);
      gap: var(--layout-gap);
      align-items: start;
    }

    .panel {
      padding: var(--panel-padding);
      min-width: 0;
    }

    .sticky-panel {
      position: sticky;
      top: calc(var(--topbar-offset) + var(--topbar-height) + var(--layout-gap));
      max-height: calc(100vh - var(--topbar-offset) - var(--topbar-height) - var(--layout-gap) - var(--shell-padding));
      display: flex;
      flex-direction: column;
      gap: var(--layout-gap);
      overflow: hidden;
    }

    .sidebar-search {
      display: grid;
      gap: var(--section-gap);
      flex: none;
      min-width: 0;
    }

    .sidebar-search .button-row button {
      flex: 1 1 0;
    }

    .panel h2,
    .panel h3 {
      margin: 0 0 var(--section-gap);
      font-family: "Space Grotesk", "Avenir Next", sans-serif;
    }

    .sidebar-search h2,
    .sidebar-results h3,
    .module-nav h3 {
      font-size: 18px;
      line-height: 1.2;
      margin-bottom: 0;
    }

    .admin-page > h2,
    .module-card-head h3 {
      font-size: 26px;
      line-height: 1.15;
      margin: 0;
    }

    .field-grid {
      display: grid;
      gap: var(--section-gap);
    }

    .field-label-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
    }

    .field-label-row label {
      margin-bottom: 0;
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
      gap: 8px;
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

    .toggle-chip-button {
      padding: 8px 14px;
      font-size: 13px;
      line-height: 1.2;
      white-space: nowrap;
    }

    .toggle-chip-button.active {
      background: var(--accent);
      color: white;
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
      gap: var(--section-gap);
      margin-bottom: var(--layout-gap);
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
      gap: var(--section-gap);
    }

    .user-item,
    .mini-card {
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      background: rgba(255, 255, 255, 0.82);
    }

    .user-item {
      display: grid;
      gap: 4px;
      align-content: start;
    }

    .user-item.active {
      border-color: rgba(17, 75, 95, 0.32);
      box-shadow: 0 10px 24px rgba(17, 75, 95, 0.12);
      background: rgba(255, 255, 255, 0.96);
    }

    .user-item strong {
      line-height: 1.4;
      overflow-wrap: anywhere;
    }

    .user-item .hint {
      font-size: 12.5px;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }

    .user-item button {
      margin-top: 8px;
      justify-self: start;
    }

    .detail-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: var(--section-gap);
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

    .admin-main > .admin-page {
      display: none;
    }

    .admin-main > .admin-page.active {
      display: block;
    }

    .sidebar-sections {
      flex: 1;
      min-height: 0;
      display: grid;
      grid-template-rows: minmax(280px, 1.35fr) minmax(220px, 1fr);
      gap: var(--layout-gap);
      overflow: hidden;
    }

    .sidebar-results,
    .module-nav {
      min-height: 0;
      display: grid;
      gap: var(--section-gap);
      align-content: start;
      overflow: hidden;
    }

    .sidebar-results {
      grid-template-rows: auto minmax(0, 1fr);
    }

    .sidebar-results h3 {
      margin: 0;
    }

    .sidebar-results .scroll-stack {
      min-height: 0;
      max-height: none;
      margin-top: 0;
      padding-right: 4px;
    }

    .module-nav {
      grid-template-rows: auto minmax(0, 1fr);
      padding-top: 4px;
      border-top: 1px solid rgba(17, 75, 95, 0.08);
    }

    .section-status {
      min-height: 18px;
      font-size: 12px;
    }

    .module-nav h3 {
      margin: 0;
      font-size: 18px;
    }

    .module-nav-list {
      display: grid;
      gap: 8px;
      min-height: 0;
      overflow: auto;
      overscroll-behavior: contain;
      padding-right: 4px;
    }

    .module-nav-button {
      width: 100%;
      justify-content: flex-start;
      text-align: left;
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(17, 75, 95, 0.08);
      color: var(--accent);
    }

    .module-nav-button.active {
      background: var(--accent);
      color: #fff;
    }

    .ops-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: var(--layout-gap);
    }

    .management-stack {
      display: none;
      gap: var(--layout-gap);
    }

    .management-stack.active {
      display: grid;
    }

    .management-module {
      padding: var(--panel-padding);
      border-radius: var(--surface-radius);
      border: 1px solid rgba(17, 75, 95, 0.16);
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(255, 249, 241, 0.92) 100%),
        var(--paper);
      box-shadow: 0 16px 36px rgba(17, 75, 95, 0.08);
    }

    .ops-grid > .management-module {
      display: none;
    }

    .ops-grid > .management-module.active {
      display: flex;
    }

    .module-card {
      display: flex;
      flex-direction: column;
      min-height: 420px;
      max-height: none;
      overflow: visible;
    }

    .module-card-head {
      display: grid;
      gap: 4px;
      margin-bottom: var(--section-gap);
    }

    .module-card-body {
      flex: 1;
      overflow: visible;
      padding-right: 0;
    }

    .module-anchor {
      scroll-margin-top: 24px;
    }

    .redeem-batch-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 10px;
    }

    .code-pill-list {
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }

    .code-pill {
      border: 1px dashed rgba(17, 75, 95, 0.18);
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.88);
      padding: 10px 12px;
    }

    .code-pill strong {
      display: block;
      font-family: "Space Grotesk", "Avenir Next", sans-serif;
      font-size: 16px;
      margin-bottom: 4px;
    }

    .redeem-detail-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }

    .redeem-toolbar {
      display: grid;
      gap: var(--section-gap);
      margin-bottom: 4px;
    }

    .redeem-toolbar-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }

    .redeem-toolbar-row .text-input-inline {
      flex: 1 1 260px;
      min-width: 220px;
    }

    .redeem-section-title {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }

    .redeem-batch-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
    }

    .redeem-batch-card.active {
      border-color: rgba(17, 75, 95, 0.34);
      box-shadow: 0 10px 24px rgba(17, 75, 95, 0.12);
      background: rgba(255, 255, 255, 0.95);
    }

    .copy-button[disabled] {
      opacity: 0.5;
      cursor: not-allowed;
      transform: none;
    }

    @media (max-width: 1100px) {
      .hero,
      .layout,
      .detail-grid,
      .ops-grid {
        grid-template-columns: 1fr;
      }

      .hero-header,
      .hero-controls {
        align-items: stretch;
      }

      .hero {
        position: static;
        left: auto;
        right: auto;
      }

      .hero-inline-field {
        align-items: stretch;
        flex-wrap: wrap;
      }

      .hero-inline-field input {
        min-width: 0;
      }

      .hero-status {
        text-align: left;
        min-width: 0;
      }

      .sticky-panel {
        position: static;
        max-height: none;
        grid-template-rows: none;
        overflow: visible;
      }

      .shell {
        padding: 20px;
      }

      .sidebar-sections,
      .module-nav,
      .module-nav-list {
        min-height: auto;
        max-height: none;
        overflow: visible;
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

      .hero-control,
      .hero-actions {
        flex: 1 1 100%;
      }

      .hero-inline-field {
        width: 100%;
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
      <div class="card hero-header">
        <h1>管理后台</h1>
        <div class="hero-controls">
          <div id="admin-token-group" class="hero-control hero-inline-field">
            <label for="admin-token">后台令牌</label>
            <input id="admin-token" type="password" placeholder="请输入 Bearer Token" />
          </div>
          <div class="hero-control hero-inline-field">
            <label for="admin-operator">操作人</label>
            <input id="admin-operator" type="text" placeholder="例如 ops-liu" />
          </div>
          <div class="hero-actions">
            <button id="load-overview">刷新</button>
            <div id="global-status" class="status hero-status"></div>
          </div>
        </div>
      </div>
    </section>

    <section class="layout">
      <aside class="card panel sticky-panel">
        <div class="sidebar-search">
          <h2>用户检索</h2>
          <div class="field-grid">
            <div>
              <div class="field-label-row">
                <label for="user-query">用户 ID / 邮箱 / 显示名</label>
                <button type="button" id="toggle-orphaned-users" class="secondary toggle-chip-button">显示孤儿账户</button>
              </div>
              <input id="user-query" type="text" placeholder="guest、邮箱或用户 ID" />
            </div>
            <div class="button-row">
              <button id="search-users">搜索用户</button>
              <button id="search-all" class="secondary">最近用户</button>
            </div>
            <div id="search-status" class="status section-status"></div>
          </div>
        </div>
        <div class="sidebar-sections">
          <div class="sidebar-results">
            <h3>用户结果</h3>
            <div class="scroll-stack">
              <div id="user-results" class="user-list"></div>
            </div>
          </div>
          <div class="module-nav">
            <h3>模块导航</h3>
            <div class="module-nav-list">
              <button class="module-nav-button secondary active" data-nav-target="section-overview">总览</button>
              <button class="module-nav-button secondary" data-nav-target="section-user-detail">用户详情</button>
              <button class="module-nav-button secondary" data-nav-target="module-grant">人工加积分</button>
              <button class="module-nav-button secondary" data-nav-target="module-broadcast">系统通知广播</button>
              <button class="module-nav-button secondary" data-nav-target="module-redeem">兑换码运营</button>
              <button class="module-nav-button secondary" data-nav-target="module-pricing">计价管理</button>
              <button class="module-nav-button secondary" data-nav-target="module-site-config">站点联络配置</button>
              <button class="module-nav-button secondary" data-nav-target="module-email-verification">邮箱验证码风控</button>
              <button class="module-nav-button secondary" data-nav-target="section-audit">后台审计</button>
              <button class="module-nav-button secondary" data-nav-target="section-broadcast-history">系统广播记录</button>
            </div>
          </div>
        </div>
      </aside>

      <main class="section-list admin-main">
        <section id="section-overview" data-admin-page="section-overview" class="card panel module-anchor admin-page active">
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

        <section id="section-user-detail" data-admin-page="section-user-detail" class="card panel module-anchor admin-page">
          <h2>用户详情</h2>
          <div id="user-detail" class="detail-grid full">
            <div class="empty">先搜索并选择一个用户。</div>
          </div>
        </section>

        <section id="section-management" class="management-stack module-anchor admin-page-shell">
          <div class="ops-grid">
            <section id="module-grant" data-admin-page="module-grant" class="card panel management-module module-card module-anchor">
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

            <section id="module-broadcast" data-admin-page="module-broadcast" class="card panel management-module module-card module-anchor">
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

            <section id="module-redeem" data-admin-page="module-redeem" class="card panel management-module module-card module-anchor">
              <div class="module-card-head">
                <h3>兑换码运营</h3>
                <div class="hint">批量生成积分兑换码，统一走账本；同一账号同一批次仅允许兑换一次，且支持按批次继续查看明文。</div>
              </div>
              <div class="module-card-body">
                <div class="field-grid">
                  <div class="redeem-toolbar">
                    <div class="redeem-toolbar-row">
                      <input id="redeem-batch-filter" class="text-input-inline" type="text" placeholder="按批次名称或 batch_id 筛选，例如 五一 / redeem_batch_xxx" />
                      <button id="apply-redeem-batch-filter" class="secondary">筛选批次</button>
                      <button id="reset-redeem-batch-filter" class="secondary">清空筛选</button>
                    </div>
                    <div class="hint">支持按批次名称或 batch_id 筛选；批次详情支持分页查看与复制本页明文。</div>
                  </div>
                  <div>
                    <label for="redeem-batch-name">批次名称</label>
                    <input id="redeem-batch-name" type="text" placeholder="例如：五一活动赠码 / 线下售卡 202604" />
                  </div>
                  <div class="detail-grid">
                    <div>
                      <label for="redeem-code-type">类型</label>
                      <select id="redeem-code-type" style="width:100%; border:1px solid rgba(17, 75, 95, 0.18); border-radius:14px; background:rgba(255,255,255,0.92); padding:12px 14px; color:var(--ink);">
                        <option value="promotion">赠送型</option>
                        <option value="recharge">充值型</option>
                      </select>
                    </div>
                    <div>
                      <label for="redeem-points">每张积分</label>
                      <input id="redeem-points" type="number" min="1" value="500" />
                    </div>
                    <div>
                      <label for="redeem-code-count">生成数量</label>
                      <input id="redeem-code-count" type="number" min="1" max="500" value="10" />
                    </div>
                    <div>
                      <label for="redeem-valid-until">失效时间（可选）</label>
                      <input id="redeem-valid-until" type="datetime-local" />
                    </div>
                  </div>
                  <div>
                    <label for="redeem-note">说明</label>
                    <textarea id="redeem-note" placeholder="例如：渠道投放 / 客诉补偿 / 线下售卖批次"></textarea>
                  </div>
                  <div class="button-row">
                    <button id="redeem-create-submit" class="warn">生成兑换码</button>
                    <button id="load-redeem-codes" class="secondary">刷新记录</button>
                  </div>
                  <div id="redeem-code-status" class="status"></div>
                  <div id="redeem-created-codes" class="hint"></div>
                  <div class="redeem-section-title">
                    <h3 style="margin:0;">批次列表</h3>
                    <div class="hint" id="redeem-batch-meta">加载中…</div>
                  </div>
                  <div id="redeem-batch-summary"></div>
                  <div id="redeem-batch-pagination" class="pager"></div>
                  <div id="redeem-batch-detail"></div>
                  <div id="redeem-batch-detail-pagination" class="pager"></div>
                  <div class="redeem-section-title">
                    <h3 style="margin:0;">最近兑换码记录</h3>
                    <div class="hint" id="redeem-code-meta">加载中…</div>
                  </div>
                  <div id="redeem-code-list"></div>
                  <div id="redeem-code-pagination" class="pager"></div>
                </div>
              </div>
            </section>

            <section id="module-pricing" data-admin-page="module-pricing" class="card panel management-module module-card module-anchor">
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

            <section id="module-site-config" data-admin-page="module-site-config" class="card panel management-module module-card module-anchor">
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

            <section id="module-email-verification" data-admin-page="module-email-verification" class="card panel management-module module-card module-anchor">
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

        <section id="section-audit" data-admin-page="section-audit" class="card panel module-anchor admin-page">
          <h2>后台审计</h2>
          <div id="audit-logs"></div>
        </section>

        <section id="section-broadcast-history" data-admin-page="section-broadcast-history" class="card panel module-anchor admin-page">
          <h2>系统广播记录</h2>
          <div id="broadcast-history"></div>
        </section>
      </main>
    </section>
  </div>

  <script>
    const state = {
      selectedUserId: null,
      authMode: '__INITIAL_ADMIN_AUTH_MODE__',
      currentAdminPage: 'section-overview',
      lastUserQuery: '',
      includeOrphanedUsers: false,
      selectedRedeemBatchId: null,
      redeemBatchKeyword: '',
      redeemCodeOffset: 0,
      redeemBatchOffset: 0,
      redeemSelectedBatchOffset: 0,
    };

    const getToken = () => document.getElementById('admin-token').value.trim();
    const getOperator = () => document.getElementById('admin-operator').value.trim();

    const setStatus = (id, text, tone = '') => {
      const element = document.getElementById(id);
      if (!element) {
        return;
      }
      element.textContent = text || '';
      element.className = `status ${tone}`.trim();
    };

    const setDualStatus = (primaryId, secondaryId, text, tone = '') => {
      setStatus(primaryId, text, tone);
      setStatus(secondaryId, text, tone);
    };

    const setButtonBusy = (button, busy, busyText = '处理中...') => {
      if (!button) {
        return;
      }
      if (!button.dataset.originalText) {
        button.dataset.originalText = button.textContent || '';
      }
      button.disabled = busy;
      button.textContent = busy ? busyText : button.dataset.originalText;
    };

    const runWithButtonBusy = async (button, action, busyText) => {
      if (!button || button.disabled) {
        return;
      }
      setButtonBusy(button, true, busyText);
      try {
        await action();
      } finally {
        setButtonBusy(button, false);
      }
    };

    const syncOrphanedUsersToggle = () => {
      const button = document.getElementById('toggle-orphaned-users');
      if (!button) {
        return;
      }
      button.classList.toggle('active', !!state.includeOrphanedUsers);
      button.textContent = state.includeOrphanedUsers ? '隐藏孤儿账户' : '显示孤儿账户';
    };

    const setActiveUserCard = (userId) => {
      document.querySelectorAll('#user-results .user-item[data-user-id]').forEach((card) => {
        card.classList.toggle('active', card.dataset.userId === userId);
      });
    };

    const ADMIN_PAGE_IDS = [
      'section-overview',
      'section-user-detail',
      'module-grant',
      'module-broadcast',
      'module-redeem',
      'module-pricing',
      'module-site-config',
      'module-email-verification',
      'section-audit',
      'section-broadcast-history',
    ];

    const setActiveNav = (sectionId) => {
      document.querySelectorAll('[data-nav-target]').forEach((button) => {
        button.classList.toggle('active', button.dataset.navTarget === sectionId);
      });
    };

    const openAdminPage = (pageId, behavior = 'none') => {
      const normalizedPageId = ADMIN_PAGE_IDS.includes(pageId) ? pageId : 'section-overview';
      state.currentAdminPage = normalizedPageId;
      setActiveNav(normalizedPageId);
      document.querySelectorAll('.admin-main > [data-admin-page]').forEach((section) => {
        section.classList.toggle('active', section.dataset.adminPage === normalizedPageId);
      });
      const managementShell = document.getElementById('section-management');
      const isManagementPage = normalizedPageId.startsWith('module-');
      managementShell.classList.toggle('active', isManagementPage);
      managementShell.querySelectorAll('[data-admin-page]').forEach((section) => {
        section.classList.toggle('active', section.dataset.adminPage === normalizedPageId);
      });
    };

    const copyText = async (text) => {
      const normalized = String(text || '').trim();
      if (!normalized) {
        return;
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(normalized);
        return;
      }
      const textarea = document.createElement('textarea');
      textarea.value = normalized;
      textarea.setAttribute('readonly', 'readonly');
      textarea.style.position = 'absolute';
      textarea.style.left = '-9999px';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    };

    const wirePager = ({ targetId, pagination, onPrev, onNext, emptyText = '暂无更多记录' }) => {
      const target = document.getElementById(targetId);
      if (!target) {
        return;
      }
      const total = Number(pagination?.total || 0);
      const limit = Math.max(1, Number(pagination?.limit || 20));
      const offset = Math.max(0, Number(pagination?.offset || 0));
      if (total <= 0) {
        target.innerHTML = `<div class="pager-status">${emptyText}</div>`;
        return;
      }
      const currentPage = Math.floor(offset / limit) + 1;
      const totalPages = Math.max(1, Math.ceil(total / limit));
      target.innerHTML = `
        <button class="secondary" data-pager-prev ${offset <= 0 ? 'disabled' : ''}>上一页</button>
        <div class="pager-status">第 ${currentPage} / ${totalPages} 页 · 共 ${total} 条</div>
        <button class="secondary" data-pager-next ${offset + limit >= total ? 'disabled' : ''}>下一页</button>
      `;
      target.querySelector('[data-pager-prev]')?.addEventListener('click', onPrev);
      target.querySelector('[data-pager-next]')?.addEventListener('click', onNext);
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
      workflow_run: '历史 Workflow 请求',
      report_quick_run: '快速报告',
      report_standard_run: '标准报告',
      report_deep_run: '深度报告',
      report_research_run: '研究报告',
      kb_retrieve: '知识库检索',
      dify_knowledge_retrieve: '知识库检索',
      product_api_call: '商品 API 检索',
      web_search: '网络搜索',
      recharge: '充值到账',
      signup_gift: '新用户注册赠送',
      referral_invited_reward: '绑定邀请码奖励',
      referral_inviter_reward: '邀请新用户注册奖励',
      redeem_code_redeem: '兑换码兑换',
      subscription_grant: '订阅积分发放',
      subscription_expire: '套餐到期清零',
      daily_quota_reset: '每日额度重置',
      admin_grant: '后台加积分',
      promotion_reward: '活动奖励',
    };

    const localizeLedgerEntryType = (entryType, eventType = '') => {
      const normalized = String(entryType || '').trim().toLowerCase();
      if (eventType && normalized && (normalized === 'promotion_reward' || normalized === 'recharge')) {
        const eventLabel = localizeLedgerEventType(eventType);
        if (eventLabel) {
          return eventLabel;
        }
      }
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
      tokenGroup.style.display = 'none';
      tokenInput.value = '';
      tokenInput.disabled = true;
      if (!getOperator()) {
        document.getElementById('admin-operator').value = localStorage.getItem('xiamimate_admin_operator') || 'openwebui-admin';
      }
    };

    const detectAuthMode = async () => {
      if (state.authMode === 'trusted-openwebui-admin') {
        applyTrustedAdminMode();
        return;
      }
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
        ['孤儿账户', metrics.orphaned_users],
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
        setStatus('search-status', '没有找到匹配用户');
        return;
      }
      target.innerHTML = users.map((user) => `
        <div class="user-item ${state.selectedUserId === user.user_id ? 'active' : ''}" data-user-id="${escapeHtml(user.user_id)}">
          <strong>${escapeHtml(user.display_name || user.user_id)}</strong>
          <div class="hint">${escapeHtml(user.user_id)}</div>
          <div class="hint">${escapeHtml(user.email || '')}</div>
          <div class="hint">套餐=${escapeHtml(user.plan_tier)} · 积分=${escapeHtml(user.balance_points)}</div>
          <div class="hint">业务状态=${escapeHtml(user.status || '-')} · 源状态=${escapeHtml(user.source_state || 'active')}</div>
          <button data-user-id="${escapeHtml(user.user_id)}">查看详情</button>
        </div>
      `).join('');

      target.querySelectorAll('button[data-user-id]').forEach((button) => {
        button.addEventListener('click', () => {
          setActiveUserCard(button.dataset.userId);
          loadUserDetail(button.dataset.userId);
        });
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
              ['源状态', user.source_state],
              ['源最近见到', user.source_last_seen_at],
              ['标记孤儿时间', user.source_orphaned_at],
              ['源恢复时间', user.source_recovered_at],
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
      state.lastUserQuery = query;
      setDualStatus('global-status', 'search-status', query ? `正在搜索 ${query}...` : '正在加载最近用户...');
      document.getElementById('user-results').innerHTML = '<div class="empty">正在加载用户列表...</div>';
      try {
        const data = await fetchJson(`/admin/api/users?limit=20&query=${encodeURIComponent(query)}&include_orphaned=${state.includeOrphanedUsers ? 'true' : 'false'}`);
        renderUserResults(data.users || []);
        setDualStatus('global-status', 'search-status', `用户列表已刷新，共 ${Number((data.users || []).length)} 条`, 'ok');
      } catch (error) {
        setDualStatus('global-status', 'search-status', error.message, 'error');
      }
    };

    const loadUserDetail = async (userId) => {
      if (!userId) {
        return;
      }
      state.selectedUserId = userId;
      setActiveUserCard(userId);
      document.getElementById('user-detail').innerHTML = '<div class="empty">正在加载用户详情...</div>';
      openAdminPage('section-user-detail');
      setDualStatus('global-status', 'search-status', `正在加载用户 ${userId}...`);
      try {
        const data = await fetchJson(`/admin/api/users/${encodeURIComponent(userId)}`);
        renderUserDetail(data);
        setDualStatus('global-status', 'search-status', `用户 ${userId} 已加载`, 'ok');
      } catch (error) {
        setDualStatus('global-status', 'search-status', error.message, 'error');
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
        await searchUsers(state.lastUserQuery);
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

    const renderRedeemBatchSummary = (batches, pagination) => {
      const target = document.getElementById('redeem-batch-summary');
      const meta = document.getElementById('redeem-batch-meta');
      if (meta) {
        meta.textContent = `共 ${Number(pagination?.total || 0)} 个批次`;
      }
      if (!batches || batches.length === 0) {
        target.innerHTML = '<div class="empty">暂无兑换码批次</div>';
        wirePager({ targetId: 'redeem-batch-pagination', pagination, onPrev: () => {}, onNext: () => {}, emptyText: '暂无批次分页' });
        return;
      }
      target.innerHTML = `<div class="redeem-batch-grid">${batches.map((batch) => `
        <div class="mini-card redeem-batch-card ${state.selectedRedeemBatchId === batch.batch_id ? 'active' : ''}">
          <strong>${escapeHtml(batch.batch_name || batch.batch_id)}</strong>
          <div class="hint">${escapeHtml(batch.code_type === 'recharge' ? '充值型' : '赠送型')} · ${escapeHtml(batch.points_amount)} 积分/张 · 已兑换 ${escapeHtml(batch.redeemed_count)}/${escapeHtml(batch.code_count)}</div>
          <div class="hint">创建人 ${escapeHtml(batch.created_by || '-')} · ${escapeHtml(batch.created_at || '-')}</div>
          <div class="redeem-batch-actions">
            <button class="secondary" data-view-redeem-batch="${escapeHtml(batch.batch_id)}">继续查看明文</button>
          </div>
        </div>
      `).join('')}</div>`;
      target.querySelectorAll('button[data-view-redeem-batch]').forEach((button) => {
        button.addEventListener('click', () => viewRedeemBatch(button.dataset.viewRedeemBatch));
      });
      wirePager({
        targetId: 'redeem-batch-pagination',
        pagination,
        onPrev: () => {
          state.redeemBatchOffset = Math.max(0, state.redeemBatchOffset - Number(pagination?.limit || 10));
          loadRedeemCodes();
        },
        onNext: () => {
          state.redeemBatchOffset += Number(pagination?.limit || 10);
          loadRedeemCodes();
        },
      });
    };

    const renderRedeemBatchDetail = (batch, codes, pagination) => {
      const target = document.getElementById('redeem-batch-detail');
      const plainCodes = (Array.isArray(codes) ? codes : []).map((row) => row.plain_code).filter(Boolean);
      if (!batch) {
        target.innerHTML = '<div class="empty">点击上方批次的“继续查看明文”，即可展开该批次的兑换码详情。</div>';
        wirePager({ targetId: 'redeem-batch-detail-pagination', pagination, onPrev: () => {}, onNext: () => {}, emptyText: '未展开批次详情' });
        return;
      }
      const rows = Array.isArray(codes) ? codes : [];
      const plainCodeCards = rows.length
        ? `<div class="code-pill-list">${rows.map((row) => `
            <div class="code-pill">
              <strong>${escapeHtml(row.plain_code || '历史批次未保存明文')}</strong>
              <div class="hint">掩码 ${escapeHtml(row.code_mask || '-')} · 状态 ${escapeHtml(row.status || '-')} · 兑换用户 ${escapeHtml(row.redeemed_by_display_name || row.redeemed_by_user_id || '-')}</div>
              <div class="redeem-batch-actions">
                <button class="secondary copy-button" data-copy-plain-code="${escapeHtml(row.plain_code || '')}" ${row.plain_code ? '' : 'disabled'}>复制这张</button>
              </div>
            </div>
          `).join('')}</div>`
        : '<div class="empty">当前批次暂无兑换码记录</div>';
      target.innerHTML = `
        <div class="mini-card">
          <div class="redeem-detail-head">
            <div>
              <h3 style="margin:0 0 6px;">${escapeHtml(batch.batch_name || batch.batch_id || '批次详情')}</h3>
              <div class="hint">${escapeHtml(batch.code_type === 'recharge' ? '充值型' : '赠送型')} · ${escapeHtml(batch.points_amount)} 积分/张 · 已兑换 ${escapeHtml(batch.redeemed_count)}/${escapeHtml(batch.code_count)}</div>
              <div class="hint">仅新生成且已保存明文的兑换码支持继续查看；旧批次若未保存明文，会显示占位提示。</div>
            </div>
            <div class="button-row">
              <button class="secondary copy-button" id="copy-redeem-batch-page" ${plainCodes.length ? '' : 'disabled'}>复制本页明文</button>
              <button class="secondary" id="clear-redeem-batch-detail">收起详情</button>
            </div>
          </div>
          ${plainCodeCards}
        </div>
      `;
      document.getElementById('copy-redeem-batch-page')?.addEventListener('click', async () => {
        try {
          await copyText(plainCodes.join('\\n'));
          setStatus('redeem-code-status', `已复制 ${plainCodes.length} 个兑换码`, 'ok');
        } catch (error) {
          setStatus('redeem-code-status', `复制失败：${error.message}`, 'error');
        }
      });
      target.querySelectorAll('[data-copy-plain-code]').forEach((button) => {
        button.addEventListener('click', async () => {
          if (!button.dataset.copyPlainCode) {
            return;
          }
          try {
            await copyText(button.dataset.copyPlainCode);
            setStatus('redeem-code-status', '兑换码已复制', 'ok');
          } catch (error) {
            setStatus('redeem-code-status', `复制失败：${error.message}`, 'error');
          }
        });
      });
      document.getElementById('clear-redeem-batch-detail')?.addEventListener('click', () => {
        state.selectedRedeemBatchId = null;
        state.redeemSelectedBatchOffset = 0;
        renderRedeemBatchDetail(null, [], null);
      });
      wirePager({
        targetId: 'redeem-batch-detail-pagination',
        pagination,
        onPrev: () => {
          state.redeemSelectedBatchOffset = Math.max(0, state.redeemSelectedBatchOffset - Number(pagination?.limit || 20));
          viewRedeemBatch(state.selectedRedeemBatchId, { preservePage: true });
        },
        onNext: () => {
          state.redeemSelectedBatchOffset += Number(pagination?.limit || 20);
          viewRedeemBatch(state.selectedRedeemBatchId, { preservePage: true });
        },
      });
    };

    const renderRedeemCodeList = (codes, pagination) => {
      const target = document.getElementById('redeem-code-list');
      const meta = document.getElementById('redeem-code-meta');
      if (meta) {
        meta.textContent = `共 ${Number(pagination?.total || 0)} 条记录`;
      }
      if (!codes || codes.length === 0) {
        target.innerHTML = '<div class="empty">暂无兑换码记录</div>';
        wirePager({ targetId: 'redeem-code-pagination', pagination, onPrev: () => {}, onNext: () => {}, emptyText: '暂无记录分页' });
        return;
      }
      target.innerHTML = `
        <div class="scroll-window tall">
          <table>
            <thead>
              <tr>
                <th>批次/卡号</th>
                <th>类型</th>
                <th>积分</th>
                <th>状态</th>
                <th>兑换用户</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              ${codes.map((row) => `
                <tr>
                  <td>
                    <div>${escapeHtml(row.code_mask || '-')}</div>
                    <div class="hint">${escapeHtml(row.batch_name || row.batch_id || '-')}</div>
                  </td>
                  <td>${escapeHtml(row.code_type === 'recharge' ? '充值型' : '赠送型')}</td>
                  <td>${escapeHtml(row.points_amount)}</td>
                  <td>${escapeHtml(row.status)}</td>
                  <td>${escapeHtml(row.redeemed_by_display_name || row.redeemed_by_user_id || '-')}</td>
                  <td>${row.status === 'active' ? `<button class="secondary" data-disable-redeem-code="${escapeHtml(row.code_id)}">禁用</button>` : '<span class="hint">-</span>'}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;
      target.querySelectorAll('button[data-disable-redeem-code]').forEach((button) => {
        button.addEventListener('click', () => disableRedeemCode(button.dataset.disableRedeemCode));
      });
      wirePager({
        targetId: 'redeem-code-pagination',
        pagination,
        onPrev: () => {
          state.redeemCodeOffset = Math.max(0, state.redeemCodeOffset - Number(pagination?.limit || 20));
          loadRedeemCodes();
        },
        onNext: () => {
          state.redeemCodeOffset += Number(pagination?.limit || 20);
          loadRedeemCodes();
        },
      });
    };

    const loadRedeemCodes = async () => {
      setStatus('redeem-code-status', '正在加载兑换码记录...');
      try {
        const params = new URLSearchParams({
          limit: '20',
          offset: String(state.redeemCodeOffset),
          batch_limit: '8',
          batch_offset: String(state.redeemBatchOffset),
        });
        if (state.redeemBatchKeyword) {
          params.set('batch_keyword', state.redeemBatchKeyword);
        }
        const data = await fetchJson(`/admin/api/redeem-codes?${params.toString()}`);
        renderRedeemBatchSummary(data.redeem_batches || [], data.redeem_batch_pagination || null);
        renderRedeemCodeList(data.redeem_codes || [], data.redeem_code_pagination || null);
        if (!state.selectedRedeemBatchId) {
          renderRedeemBatchDetail(null, [], null);
        }
        setStatus('redeem-code-status', '兑换码记录已刷新', 'ok');
      } catch (error) {
        setStatus('redeem-code-status', error.message, 'error');
      }
    };

    const viewRedeemBatch = async (batchId, { preservePage = false } = {}) => {
      if (!batchId) {
        setStatus('redeem-code-status', '缺少 batch_id', 'error');
        return;
      }
      if (!preservePage) {
        state.redeemSelectedBatchOffset = 0;
      }
      setStatus('redeem-code-status', `正在查看批次 ${batchId}...`);
      try {
        const params = new URLSearchParams({
          limit: '20',
          batch_limit: '1',
          batch_id: batchId,
          include_plain_codes: '1',
          selected_batch_offset: String(state.redeemSelectedBatchOffset),
        });
        const data = await fetchJson(`/admin/api/redeem-codes?${params.toString()}`);
        state.selectedRedeemBatchId = batchId;
        renderRedeemBatchDetail(data.selected_batch || null, data.selected_batch_codes || [], data.selected_batch_pagination || null);
        openAdminPage('module-redeem', 'smooth');
        setStatus('redeem-code-status', `批次 ${batchId} 已展开`, 'ok');
      } catch (error) {
        setStatus('redeem-code-status', error.message, 'error');
      }
    };

    const applyRedeemBatchFilter = async () => {
      state.redeemBatchKeyword = document.getElementById('redeem-batch-filter').value.trim();
      state.redeemBatchOffset = 0;
      state.redeemCodeOffset = 0;
      state.selectedRedeemBatchId = null;
      state.redeemSelectedBatchOffset = 0;
      await loadRedeemCodes();
      openAdminPage('module-redeem');
    };

    const resetRedeemBatchFilter = async () => {
      document.getElementById('redeem-batch-filter').value = '';
      state.redeemBatchKeyword = '';
      state.redeemBatchOffset = 0;
      state.redeemCodeOffset = 0;
      state.selectedRedeemBatchId = null;
      state.redeemSelectedBatchOffset = 0;
      await loadRedeemCodes();
    };

    const createRedeemCodeBatch = async () => {
      const batchName = document.getElementById('redeem-batch-name').value.trim();
      const codeType = document.getElementById('redeem-code-type').value;
      const points = Number(document.getElementById('redeem-points').value || 0);
      const codeCount = Number(document.getElementById('redeem-code-count').value || 0);
      const validUntil = document.getElementById('redeem-valid-until').value;
      const note = document.getElementById('redeem-note').value.trim();
      if (!Number.isFinite(points) || points <= 0) {
        setStatus('redeem-code-status', '每张积分必须大于 0', 'error');
        return;
      }
      if (!Number.isFinite(codeCount) || codeCount <= 0) {
        setStatus('redeem-code-status', '生成数量必须大于 0', 'error');
        return;
      }

      setStatus('redeem-code-status', '正在生成兑换码...');
      try {
        const data = await fetchJson('/admin/api/redeem-codes/batches', {
          method: 'POST',
          body: JSON.stringify({
            batch_name: batchName || null,
            code_type: codeType,
            points: Math.trunc(points),
            code_count: Math.trunc(codeCount),
            valid_until: validUntil ? new Date(validUntil).toISOString() : null,
            note: note || null,
          }),
        });
        const createdCodes = (data.codes || []).map((row) => row.plain_code).filter(Boolean);
        document.getElementById('redeem-created-codes').innerHTML = createdCodes.length
          ? ('<strong>本次生成：</strong><br />' + createdCodes.map((code) => escapeHtml(code)).join('<br />'))
          : '本次未返回可展示的兑换码';
        setStatus('redeem-code-status', `已生成 ${createdCodes.length} 个兑换码`, 'ok');
        state.redeemCodeOffset = 0;
        state.redeemBatchOffset = 0;
        await loadRedeemCodes();
        if (data.batch?.batch_id) {
          await viewRedeemBatch(data.batch.batch_id);
        }
        await loadAuditLogs();
      } catch (error) {
        setStatus('redeem-code-status', error.message, 'error');
      }
    };

    const disableRedeemCode = async (codeId) => {
      if (!codeId) {
        setStatus('redeem-code-status', '缺少 code_id', 'error');
        return;
      }
      setStatus('redeem-code-status', `正在禁用 ${codeId}...`);
      try {
        await fetchJson(`/admin/api/redeem-codes/${encodeURIComponent(codeId)}/disable`, {
          method: 'POST',
        });
        setStatus('redeem-code-status', '兑换码已禁用', 'ok');
        await loadRedeemCodes();
        if (state.selectedRedeemBatchId) {
          await viewRedeemBatch(state.selectedRedeemBatchId, { preservePage: true });
        }
        await loadAuditLogs();
      } catch (error) {
        setStatus('redeem-code-status', error.message, 'error');
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

    document.getElementById('load-overview').addEventListener('click', (event) => {
      runWithButtonBusy(event.currentTarget, loadOverview, '刷新中...');
    });
    document.getElementById('load-pricing').addEventListener('click', loadPricing);
    document.getElementById('load-site-config').addEventListener('click', loadSiteConfig);
    document.getElementById('load-email-verification-config').addEventListener('click', loadSiteConfig);
    document.getElementById('search-users').addEventListener('click', (event) => {
      runWithButtonBusy(event.currentTarget, () => searchUsers(document.getElementById('user-query').value.trim()), '搜索中...');
    });
    document.getElementById('search-all').addEventListener('click', (event) => {
      runWithButtonBusy(event.currentTarget, () => searchUsers(''), '加载中...');
    });
    document.getElementById('toggle-orphaned-users').addEventListener('click', (event) => {
      runWithButtonBusy(event.currentTarget, async () => {
        state.includeOrphanedUsers = !state.includeOrphanedUsers;
        syncOrphanedUsersToggle();
        await searchUsers(document.getElementById('user-query').value.trim());
      }, '切换中...');
    });
    document.getElementById('grant-submit').addEventListener('click', (event) => {
      runWithButtonBusy(event.currentTarget, grantPoints, '处理中...');
    });
    document.getElementById('broadcast-submit').addEventListener('click', (event) => {
      runWithButtonBusy(event.currentTarget, sendBroadcast, '发送中...');
    });
    document.getElementById('redeem-create-submit').addEventListener('click', (event) => {
      runWithButtonBusy(event.currentTarget, createRedeemCodeBatch, '生成中...');
    });
    document.getElementById('load-redeem-codes').addEventListener('click', (event) => {
      runWithButtonBusy(event.currentTarget, loadRedeemCodes, '刷新中...');
    });
    document.getElementById('apply-redeem-batch-filter').addEventListener('click', (event) => {
      runWithButtonBusy(event.currentTarget, applyRedeemBatchFilter, '筛选中...');
    });
    document.getElementById('reset-redeem-batch-filter').addEventListener('click', (event) => {
      runWithButtonBusy(event.currentTarget, resetRedeemBatchFilter, '清空中...');
    });
    document.getElementById('user-query').addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        document.getElementById('search-users').click();
      }
    });
    document.getElementById('redeem-batch-filter').addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        applyRedeemBatchFilter();
      }
    });
    document.querySelectorAll('[data-nav-target]').forEach((button) => {
      button.addEventListener('click', () => openAdminPage(button.dataset.navTarget));
    });

    const savedToken = sessionStorage.getItem('xiamimate_admin_token');
    const savedOperator = localStorage.getItem('xiamimate_admin_operator');
    syncOrphanedUsersToggle();
    if (savedToken) {
      document.getElementById('admin-token').value = savedToken;
    }
    if (savedOperator) {
      document.getElementById('admin-operator').value = savedOperator;
    }

    detectAuthMode().finally(() => {
      openAdminPage(state.currentAdminPage, 'none');
      loadOverview().catch(() => {});
      loadPricing().catch(() => {});
      loadRedeemCodes().catch(() => {});
      loadSiteConfig().catch(() => {});
      searchUsers('').catch(() => {});
      loadAuditLogs().catch(() => {});
      loadBroadcasts().catch(() => {});
    });
  </script>
</body>
</html>
""".replace(
    '__INITIAL_ADMIN_AUTH_MODE__',
    'trusted-openwebui-admin' if trusted_openwebui_admin else 'fixed-token',
  )