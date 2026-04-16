from __future__ import annotations

from html import escape

from data_platform.chat_backend.domains.portal.service import _portal_base_url


def render_portal_html() -> str:
    openwebui_home_url = escape(_portal_base_url())
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>虾密小助手 - 我的账户</title>
  <style>
    :root {
      --bg: #f5efe4;
      --paper: rgba(255, 251, 245, 0.96);
      --panel: rgba(255, 251, 245, 0.9);
      --ink: #1e2a2f;
      --muted: #68767d;
      --accent: #114b5f;
      --accent-soft: rgba(17, 75, 95, 0.08);
      --accent-2: #d97706;
      --line: rgba(17, 75, 95, 0.12);
      --danger: #b42318;
      --ok: #0f766e;
      --shadow: 0 18px 48px rgba(30, 42, 47, 0.12);
      --sidebar-w: 228px;
      --content-w: 1220px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "IBM Plex Sans", "Helvetica Neue", "PingFang SC", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(217, 119, 6, 0.18), transparent 24%),
        radial-gradient(circle at right top, rgba(17, 75, 95, 0.18), transparent 20%),
        linear-gradient(180deg, #fffdf8 0%, var(--bg) 100%);
      min-height: 100vh;
      overflow: hidden;
    }
    .portal-shell {
      height: 100vh;
      display: flex;
    }

    /* Sidebar */
    .sidebar {
      width: var(--sidebar-w);
      height: 100vh;
      background: var(--panel);
      border-right: 1px solid var(--line);
      padding: 18px 0 24px;
      flex-shrink: 0;
      position: sticky;
      top: 0;
      overflow-y: auto;
    }
    .sidebar .brand {
      padding: 4px 18px 16px;
      font-size: 1.12rem;
      font-weight: 700;
      color: var(--ink);
      border-bottom: 1px solid var(--line);
      margin-bottom: 12px;
    }
    .sidebar .brand-subtitle {
      display: block;
      margin-top: 6px;
      color: var(--muted);
      font-size: 0.78rem;
      font-weight: 500;
    }
    .sidebar .nav-group {
      padding: 10px 10px 6px;
    }
    .sidebar .nav-group-title {
      padding: 6px 10px;
      font-size: 0.76rem;
      font-weight: 600;
      color: var(--muted);
      letter-spacing: 0.04em;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .sidebar .nav-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 10px 12px 10px 18px;
      font-size: 0.88rem;
      color: var(--ink);
      text-decoration: none;
      cursor: pointer;
      border-left: 3px solid transparent;
      border-radius: 10px;
      transition: background 0.15s, border-color 0.15s, color 0.15s;
    }
    .sidebar .nav-item:hover {
      background: rgba(23, 32, 51, 0.04);
    }
    .sidebar .nav-item.locked,
    .sidebar .nav-item.locked:hover {
      color: var(--muted);
      background: rgba(104, 118, 125, 0.08);
      border-left-color: transparent;
      cursor: not-allowed;
      opacity: 0.68;
    }
    .sidebar .nav-item.active {
      background: var(--accent-soft);
      border-left-color: var(--accent);
      .nav-item-label {
        min-width: 0;
      }
      .nav-item-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 22px;
        height: 22px;
        padding: 0 6px;
        border-radius: 999px;
        background: rgba(217, 38, 38, 0.12);
        color: #b91c1c;
        font-size: 0.74rem;
        font-weight: 700;
        flex-shrink: 0;
      }
      font-weight: 600;
      color: var(--accent);
    }

    .workspace {
      flex: 1;
      min-width: 0;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow-y: auto;
    }
    .workspace-topbar {
      position: sticky;
      top: 0;
      z-index: 10;
      backdrop-filter: blur(12px);
      background: rgba(255, 251, 245, 0.84);
      border-bottom: 1px solid var(--line);
    }
    .workspace-topbar-inner {
      width: min(var(--content-w), calc(100% - 48px));
      margin: 0 auto;
      min-height: 92px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      padding: 14px 0;
    }
    .topbar-actions {
      display: flex;
      align-items: center;
      gap: 14px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .top-route-nav {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .top-utility-actions {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .top-route-link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 40px;
      padding: 0 14px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(255, 251, 245, 0.75);
      color: var(--muted);
      text-decoration: none;
      font-size: 0.84rem;
      font-weight: 600;
      transition: border-color 0.15s, background 0.15s, color 0.15s;
    }
    .top-route-link:hover {
      color: var(--accent);
      border-color: rgba(17, 75, 95, 0.24);
    }
    .top-route-link.active {
      background: var(--accent-soft);
      color: var(--accent);
      border-color: rgba(17, 75, 95, 0.18);
    }
    .top-icon-link {
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 40px;
      height: 40px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(255, 251, 245, 0.78);
      color: var(--ink);
      text-decoration: none;
      font-size: 1.05rem;
      transition: border-color 0.15s, background 0.15s, color 0.15s;
    }
    .top-icon-link:hover,
    .top-icon-link.active {
      background: var(--accent-soft);
      color: var(--accent);
      border-color: rgba(17, 75, 95, 0.18);
    }
    .notif-badge {
      position: absolute;
      top: -5px;
      right: -5px;
      min-width: 18px;
      height: 18px;
      padding: 0 5px;
      border-radius: 999px;
      background: #d97706;
      color: #fff;
      font-size: 0.67rem;
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 6px 16px rgba(217, 119, 6, 0.28);
    }
    .top-home-link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 40px;
      padding: 0 16px;
      border-radius: 12px;
      border: 1px solid rgba(17, 75, 95, 0.18);
      background: var(--accent);
      color: #fff;
      text-decoration: none;
      font-size: 0.84rem;
      font-weight: 600;
      transition: background 0.15s, border-color 0.15s;
    }
    .top-home-link:hover {
      background: #0f3f50;
      border-color: #0f3f50;
    }
    .page-kicker {
      font-size: 0.78rem;
      color: var(--muted);
      letter-spacing: 0.06em;
      text-transform: uppercase;
      margin-bottom: 6px;
    }
    .page-title-row {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }
    .page-title-row h1 {
      font-size: 1.92rem;
      line-height: 1.08;
      margin: 0;
      font-weight: 700;
    }
    .subtitle {
      color: var(--muted);
      font-size: 0.92rem;
      margin-top: 8px;
      max-width: 720px;
    }
    .main {
      width: min(var(--content-w), calc(100% - 48px));
      margin: 28px auto 48px;
    }
    .main-stack {
      display: flex;
      flex-direction: column;
      gap: 18px;
    }

    .page { display: none; }
    .page.active { display: block; }
    .page-grid {
      display: grid;
      gap: 18px;
      grid-template-columns: minmax(0, 1fr);
    }
    .split-grid {
      display: grid;
      grid-template-columns: minmax(320px, 1.2fr) minmax(280px, 0.8fr);
      gap: 18px;
    }

    .card {
      background: var(--paper);
      border-radius: 18px;
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      padding: 22px 24px;
    }
    .card h2 {
      font-size: 1.02rem;
      margin: 0 0 16px;
      color: var(--ink);
      border-bottom: 1px solid var(--line);
      padding-bottom: 12px;
    }
    .card-note {
      color: var(--muted);
      font-size: 0.86rem;
      margin: -6px 0 14px;
    }
    .hero-card {
      background: linear-gradient(135deg, rgba(217, 119, 6, 0.1), rgba(255, 251, 245, 0.98));
    }
    .hero-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(260px, 320px);
      gap: 20px;
      align-items: stretch;
    }
    .hero-block {
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .hero-metric {
      border-radius: 16px;
      background: var(--paper);
      border: 1px solid var(--line);
      padding: 18px;
      display: grid;
      gap: 10px;
    }
    .hero-metric-value {
      font-size: 2rem;
      font-weight: 700;
      color: var(--ink);
    }
    .hero-metric-label,
    .hero-metric-subtitle {
      color: var(--muted);
      font-size: 0.86rem;
    }

    /* KPI row */
    .kpi-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
    }
    .kpi {
      text-align: left;
      padding: 16px 18px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: linear-gradient(180deg, rgba(255, 251, 245, 0.98), rgba(244, 236, 223, 0.98));
    }
    .kpi .value { font-size: 1.62rem; font-weight: 700; color: var(--ink); }
    .kpi .label { font-size: 0.8rem; color: var(--muted); margin-top: 4px; }

    /* Info rows */
    .info-row {
      display: flex;
      padding: 11px 0;
      border-bottom: 1px solid var(--line);
      font-size: 0.9rem;
    }
    .info-row:last-child { border-bottom: none; }
    .info-row .info-label { width: 140px; color: var(--muted); flex-shrink: 0; }
    .info-row .info-value { flex: 1; font-weight: 500; }

    /* Table */
    .table-wrap {
      border: 1px solid var(--line);
      border-radius: 14px;
      overflow: auto;
      background: rgba(255, 251, 245, 0.98);
    }
    .table-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 12px;
      font-size: 0.84rem;
      color: var(--muted);
    }
    .table-toolbar strong {
      color: var(--ink);
      font-weight: 600;
    }
    table { width: 100%; border-collapse: collapse; font-size: 0.83rem; }
    thead th {
      text-align: left; font-weight: 600; color: var(--muted);
      padding: 12px 14px; border-bottom: 1px solid var(--line); white-space: nowrap;
      background: rgba(244, 236, 223, 0.76);
      position: sticky;
      top: 0;
      z-index: 1;
    }
    tbody td { padding: 12px 14px; border-bottom: 1px solid var(--line); }
    tbody tr:hover { background: rgba(17, 75, 95, 0.04); }
    tbody tr:last-child td { border-bottom: none; }
    .positive { color: var(--ok); }
    .negative { color: var(--danger); }
    .empty-row td {
      padding: 38px 14px;
      text-align: center;
      color: var(--muted);
      background: linear-gradient(180deg, rgba(255, 251, 245, 0.98), rgba(244, 236, 223, 0.8));
    }

    /* Pricing pills */
    .pricing-row { display: flex; flex-wrap: wrap; gap: 10px; }
    .pricing-pill {
      background: rgba(17, 75, 95, 0.07); border-radius: 999px;
      padding: 8px 14px; font-size: 0.84rem;
      border: 1px solid rgba(17, 75, 95, 0.08);
    }
    .pricing-pill .name { font-weight: 600; }
    .pricing-pill .cost { color: var(--accent-2); margin-left: 6px; }

    /* Pagination */
    .pager {
      display: flex; justify-content: center; align-items: center;
      gap: 10px; margin-top: 14px; font-size: 0.84rem;
      flex-wrap: wrap;
    }
    .pager button {
      min-width: 84px;
    }
    .pager-status {
      color: var(--muted);
      min-width: 148px;
      text-align: center;
    }

    /* Usage chart */
    .chart-row { display: flex; align-items: flex-end; gap: 6px; height: 180px; margin-top: 18px; }
    .chart-bar {
      flex: 1; min-width: 10px; max-width: 32px;
      background: linear-gradient(180deg, #4d7a88 0%, var(--accent) 100%);
      border-radius: 8px 8px 0 0;
      position: relative; cursor: default;
    }
    .chart-bar:hover::after {
      content: attr(data-tip); position: absolute; bottom: 100%; left: 50%;
      transform: translateX(-50%); background: var(--ink); color: #fff;
      padding: 3px 7px; border-radius: 4px; font-size: 0.7rem; white-space: nowrap;
    }
    .chart-labels {
      display: flex; gap: 6px; margin-top: 8px;
      font-size: 0.68rem; color: var(--muted);
    }
    .chart-labels span { flex: 1; min-width: 10px; max-width: 32px; text-align: center; overflow: hidden; }

    /* Plan badge */
    .plan-badge {
      display: inline-flex; align-items: center; background: var(--accent-soft); color: var(--accent);
      padding: 5px 10px; border-radius: 999px; font-size: 0.76rem; font-weight: 600; margin-left: 8px;
    }
    .plan-badge.empty {
      background: rgba(104, 118, 125, 0.12);
      color: var(--muted);
    }
    .subnav-tabs {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }
    .sub-tab {
      border-radius: 999px;
      padding: 8px 14px;
      background: rgba(255, 251, 245, 0.78);
      color: var(--muted);
    }
    .sub-tab.active {
      background: var(--accent-soft);
      color: var(--accent);
      border-color: rgba(17, 75, 95, 0.18);
    }
    .subview {
      display: none;
    }
    .subview.active {
      display: block;
    }
    .invoice-grid,
    .notifications-list {
      display: grid;
      gap: 14px;
    }
    .invoice-grid {
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      margin-bottom: 16px;
    }
    .invoice-card,
    .notification-card {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255, 251, 245, 0.86);
      padding: 16px 18px;
    }
    .notifications-shell {
      display: grid;
      grid-template-columns: 220px minmax(0, 1fr);
      gap: 24px;
      align-items: start;
    }
    .notifications-side {
      border-right: 1px solid var(--line);
      padding-right: 18px;
    }
    .notifications-side-title {
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--ink);
      font-size: 0.94rem;
      font-weight: 700;
      margin-bottom: 16px;
    }
    .notifications-menu {
      display: grid;
      gap: 8px;
    }
    .notifications-menu-item {
      width: 100%;
      justify-content: flex-start;
      padding: 10px 14px;
      border-radius: 14px;
      text-align: left;
      background: rgba(255, 251, 245, 0.72);
      color: var(--muted);
    }
    .notifications-menu-item.active {
      background: var(--accent-soft);
      color: var(--accent);
      border-color: rgba(17, 75, 95, 0.18);
    }
    .notifications-content {
      min-width: 0;
    }
    .read-all-link {
      min-height: auto;
      padding: 0;
      border: none;
      background: transparent;
      color: var(--muted);
      font-size: 0.84rem;
    }
    .read-all-link:hover {
      background: transparent;
      color: var(--accent);
    }
    .notification-toolbar-actions {
      display: inline-flex;
      align-items: center;
      gap: 14px;
      flex-wrap: wrap;
    }
    .invoice-card-label,
    .notification-meta {
      color: var(--muted);
      font-size: 0.8rem;
    }
    .invoice-card-value {
      margin-top: 6px;
      font-size: 1.1rem;
      font-weight: 700;
      color: var(--ink);
    }
    .notification-card {
      display: grid;
      gap: 8px;
    }
    .notification-card.unread {
      border-color: rgba(17, 75, 95, 0.2);
      box-shadow: 0 10px 24px rgba(17, 75, 95, 0.08);
    }
    .notification-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }
    .notification-title-row {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .notification-unread-dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: #2563eb;
      box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.12);
      flex-shrink: 0;
    }
    .notification-title {
      font-size: 0.96rem;
      font-weight: 700;
      color: var(--ink);
    }
    .notification-desc {
      color: var(--muted);
      font-size: 0.86rem;
      line-height: 1.7;
    }
    .notification-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 2px;
    }
    .notification-toggle-link {
      min-height: auto;
      padding: 0;
      border: none;
      background: transparent;
      color: var(--accent);
      font-size: 0.82rem;
      font-weight: 600;
      cursor: pointer;
    }
    .notification-toggle-link:hover {
      color: #0f3f50;
      background: transparent;
    }
    .notification-tag {
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.74rem;
      font-weight: 700;
    }
    .notification-tag.success {
      background: rgba(15, 118, 110, 0.12);
      color: var(--ok);
    }
    .notification-tag.warning {
      background: rgba(217, 119, 6, 0.12);
      color: #9a6700;
    }
    .notification-tag.info {
      background: rgba(17, 75, 95, 0.12);
      color: var(--accent);
    }
    .action-stack {
      display: grid;
      gap: 12px;
      margin-top: 14px;
    }
    .inline-form {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .text-input {
      flex: 1 1 220px;
      min-height: 40px;
      padding: 0 12px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: rgba(255, 251, 245, 0.96);
      color: var(--ink);
      font-size: 0.84rem;
    }
    .helper-text {
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.6;
    }
    .status-badge {
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.76rem;
      font-weight: 700;
    }
    .status-badge.ok {
      background: rgba(15, 118, 110, 0.12);
      color: var(--ok);
    }
    .status-badge.pending {
      background: rgba(217, 119, 6, 0.12);
      color: #9a6700;
    }

    button {
      cursor: pointer; border: 1px solid var(--line); background: var(--paper);
      color: var(--ink); padding: 8px 14px; border-radius: 10px; font-size: 0.82rem;
    }
    button:hover { background: rgba(23, 32, 51, 0.04); }
    button:disabled { opacity: 0.5; cursor: default; }

    .error-msg {
      background: rgba(180, 35, 24, 0.08); color: var(--danger);
      padding: 16px 18px; border-radius: 14px; text-align: center; font-size: 0.95rem;
    }
    .gate-banner {
      display: none;
      background: rgba(217, 119, 6, 0.12);
      color: #9a6700;
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid rgba(217, 119, 6, 0.22);
      font-size: 0.9rem;
      line-height: 1.7;
    }

    @media (max-width: 700px) {
      .portal-shell { flex-direction: column; }
      body { overflow: auto; }
      .sidebar { width: 100%; min-height: auto; display: flex; overflow-x: auto; padding: 10px 0 0; border-right: none; border-bottom: 1px solid var(--line); position: static; }
      .sidebar .brand { padding: 0 12px 8px; white-space: nowrap; border-bottom: none; margin-bottom: 0; }
      .sidebar .nav-group { display: flex; padding: 0; }
      .sidebar .nav-group-title { display: none; }
      .sidebar .nav-item { padding: 8px 14px; border-left: none; border-bottom: 3px solid transparent; white-space: nowrap; }
      .sidebar .nav-item.active { border-left: none; border-bottom-color: var(--accent); }
        .nav-item-badge { min-width: 20px; height: 20px; }
      .portal-shell, .workspace, .sidebar { height: auto; }
      .workspace { overflow: visible; }
      .workspace-topbar-inner, .main { width: calc(100% - 24px); }
      .workspace-topbar-inner { min-height: 76px; padding: 10px 0; align-items: flex-start; }
      .topbar-actions, .top-route-nav, .top-utility-actions { justify-content: flex-start; }
      .page-title-row h1 { font-size: 1.5rem; }
      .main { margin: 16px auto 28px; }
      .split-grid, .hero-grid { grid-template-columns: 1fr; }
      .notifications-shell { grid-template-columns: 1fr; }
      .notifications-side { border-right: none; padding-right: 0; border-bottom: 1px solid var(--line); padding-bottom: 14px; }
      .kpi-row { grid-template-columns: repeat(2, 1fr); }
      table { font-size: 0.75rem; }
    }
  </style>
</head>
<body>
<div class="portal-shell">
<nav class="sidebar">
  <div class="brand">🦐 虾密小助手<span class="brand-subtitle">统一门户账户中心</span></div>
  <div class="nav-group">
    <div class="nav-group-title">📋 账户管理</div>
    <a class="nav-item" data-page="notifications"><span class="nav-item-label">通知中心</span><span class="nav-item-badge" id="notifications-nav-badge" style="display:none;">0</span></a>
    <a class="nav-item active" data-page="account"><span class="nav-item-label">账户信息</span></a>
  </div>
  <div class="nav-group">
    <div class="nav-group-title">💰 财务管理</div>
    <a class="nav-item" data-page="balance"><span class="nav-item-label">余额概览</span></a>
    <a class="nav-item" data-page="topup"><span class="nav-item-label">充值/赠送记录</span></a>
    <a class="nav-item" data-page="billing"><span class="nav-item-label">消费记录</span></a>
    <a class="nav-item" data-page="usage"><span class="nav-item-label">使用趋势</span></a>
  </div>
  <div class="nav-group">
    <div class="nav-group-title">📦 套餐管理</div>
    <a class="nav-item" data-page="plan"><span class="nav-item-label">当前套餐</span></a>
  </div>
</nav>

<div class="workspace">
  <div class="workspace-topbar">
    <div class="workspace-topbar-inner">
      <div>
        <div class="page-kicker">账户管理</div>
        <div class="page-title-row">
          <h1 id="page-title">账户信息</h1>
        </div>
        <div class="subtitle" id="user-info">加载中…</div>
      </div>
      <div class="topbar-actions">
        <div class="top-route-nav">
          <a class="top-route-link active" id="route-account-link" href="/portal/account">账户管理</a>
          <a class="top-route-link" id="route-products-link" href="/portal/products">订阅与充值</a>
          <a class="top-route-link" id="route-guide-link" href="/portal/guide">使用指南</a>
        </div>
        <div class="top-utility-actions">
          <a class="top-home-link" id="open-webui-home-link" href="__OPENWEBUI_HOME_URL__">首页</a>
        </div>
      </div>
    </div>
  </div>

<div class="main">
  <div class="main-stack">
  <div id="error-panel" style="display:none;" class="error-msg"></div>
  <div id="verification-gate-banner" class="gate-banner"></div>

  <!-- 账户信息 -->
  <div id="page-account" class="page active">
    <div class="page-grid">
      <div class="card hero-card">
        <div class="hero-grid">
          <div class="hero-block">
            <div>
              <h2>基本信息</h2>
              <div class="card-note">统一展示账户主体、套餐状态，以及月包积分和充值包积分的当前余额。</div>
            </div>
            <div id="account-info"></div>
          </div>
          <div class="hero-metric">
            <div class="hero-metric-label">当前积分余额</div>
            <div class="hero-metric-value" id="hero-balance">0</div>
            <div class="hero-metric-subtitle">消费时优先扣减月包积分；充值包积分永久有效。</div>
          </div>
        </div>
      </div>
      <div class="split-grid">
        <div class="card">
          <h2>安全设置</h2>
          <div class="info-row">
            <div class="info-label">登录方式</div>
            <div class="info-value">Open WebUI 统一登录</div>
          </div>
          <div class="info-row">
            <div class="info-label">门户访问</div>
            <div class="info-value">当前浏览器会话直连，无需额外 token</div>
          </div>
          <div class="info-row">
            <div class="info-label">邮箱验证</div>
            <div class="info-value" id="email-verification-status">加载中…</div>
          </div>
          <div class="info-row">
            <div class="info-label">验证邮箱</div>
            <div class="info-value" id="verification-email">-</div>
          </div>
          <div class="action-stack">
            <div class="inline-form">
              <button type="button" id="send-verification-code-button">发送邮箱验证码</button>
              <span class="helper-text" id="verification-request-message">注册成功以邮箱验证通过为准。</span>
            </div>
            <div class="inline-form">
              <input id="verification-code-input" class="text-input" type="text" inputmode="numeric" maxlength="8" placeholder="输入邮箱验证码" />
              <button type="button" id="confirm-verification-button">确认验证</button>
            </div>
            <div class="helper-text" id="verification-confirm-message">验证成功后，新用户自动到账 500 积分。</div>
          </div>
        </div>
        <div class="card">
          <h2>邀请有礼</h2>
          <div class="info-row">
            <div class="info-label">我的邀请码</div>
            <div class="info-value" id="my-invite-code">-</div>
          </div>
          <div class="info-row">
            <div class="info-label">邀请绑定</div>
            <div class="info-value" id="invite-binding-status">加载中…</div>
          </div>
          <div class="action-stack">
            <div class="helper-text">新用户无论是否被邀请，只要邮箱验证成功都会获得 500 积分；如果是被邀请来的，邀请人也会在你验证成功后获得 500 积分。</div>
            <div class="inline-form">
              <input id="invite-code-input" class="text-input" type="text" maxlength="32" placeholder="输入邀请人的邀请码" />
              <button type="button" id="bind-invite-code-button">绑定邀请码</button>
            </div>
            <div class="helper-text" id="bind-invite-code-message">如果你是被邀请来的，请先绑定邀请码，再完成邮箱验证。</div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 通知中心 -->
  <div id="page-notifications" class="page">
    <div class="page-grid">
      <div class="card">
        <div class="notifications-shell">
          <div class="notifications-side">
            <div class="notifications-side-title">🔔 消息通知</div>
            <div class="notifications-menu">
              <button type="button" class="notifications-menu-item" data-notification-category="user">用户通知</button>
              <button type="button" class="notifications-menu-item active" data-notification-category="system">系统通知</button>
            </div>
          </div>
          <div class="notifications-content">
            <div class="table-toolbar">
              <div><strong id="notifications-panel-title">系统通知</strong></div>
              <div class="notification-toolbar-actions">
                <button type="button" class="read-all-link" id="mark-notifications-read">全部设为已读</button>
                <button type="button" class="read-all-link" id="mark-notifications-unread">全部标为未读</button>
              </div>
            </div>
            <div class="card-note" id="notifications-panel-note">统一查看充值到账、余额提醒、活动提醒和功能更新。当前浏览器会保留你的已读状态，刷新页面不会重置。</div>
            <div id="notifications-meta" class="notification-meta">加载中…</div>
            <div style="height: 14px;"></div>
            <div id="notifications-body" class="notifications-list"></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 余额概览 -->
  <div id="page-balance" class="page">
    <div class="page-grid">
    <div class="card">
      <h2>积分概览</h2>
      <div class="card-note">明确区分总余额、月包余额、充值包余额和其他赠送余额。</div>
      <div class="kpi-row" id="kpi-row"></div>
    </div>
    </div>
  </div>

  <!-- 充值/赠送记录 -->
  <div id="page-topup" class="page">
    <div class="card">
      <h2>充值/赠送记录</h2>
      <div class="card-note">展示所有正向入账记录，包括新用户赠送、手工加额和充值到账。</div>
      <div class="subnav-tabs">
        <button type="button" class="sub-tab active" data-topup-view="records">到账记录</button>
        <button type="button" class="sub-tab" data-topup-view="invoice">发票管理</button>
      </div>
      <div id="topup-records-view" class="subview active">
        <div class="table-toolbar">
          <div><strong>正向入账账本</strong>，支持分页查看最近的充值和赠送。</div>
          <div id="topup-meta">加载中…</div>
        </div>
        <div class="table-wrap">
        <table>
          <thead><tr><th>时间</th><th>类型</th><th>变动</th><th>余额</th><th>说明</th></tr></thead>
          <tbody id="topup-body"></tbody>
        </table>
        </div>
        <div class="pager" id="topup-pager"></div>
      </div>
      <div id="topup-invoice-view" class="subview">
        <div class="invoice-grid">
          <div class="invoice-card">
            <div class="invoice-card-label">最近可开票订单数</div>
            <div class="invoice-card-value" id="invoice-paid-order-count">0</div>
          </div>
          <div class="invoice-card">
            <div class="invoice-card-label">最近已支付订单</div>
            <div class="invoice-card-value" id="invoice-latest-order">暂无</div>
          </div>
          <div class="invoice-card">
            <div class="invoice-card-label">当前开票状态</div>
            <div class="invoice-card-value">待接入</div>
          </div>
        </div>
        <div class="notification-card">
          <div class="notification-top">
            <div class="notification-title">发票管理二级页建议</div>
            <span class="notification-tag info">规划中</span>
          </div>
          <div class="notification-desc">这里已经先预留成“充值/赠送记录”的二级页。后续可以接企业抬头、邮箱收票、按订单申请开票、补开发票和开票状态跟踪，不需要再改导航结构。</div>
        </div>
      </div>
    </div>
  </div>

  <!-- 消费记录 -->
  <div id="page-billing" class="page">
    <div class="card">
      <h2>消费记录</h2>
      <div class="card-note">展示所有扣费账本记录，按事件类型和扣减积分追踪。</div>
      <div class="table-toolbar">
        <div><strong>扣费账本</strong>，翻页后仍保留当前位置，适合连续排查近期消费。</div>
        <div id="ledger-meta">加载中…</div>
      </div>
      <div class="table-wrap">
      <table>
        <thead><tr><th>时间</th><th>类型</th><th>事件</th><th>变动</th><th>余额</th><th>说明</th></tr></thead>
        <tbody id="ledger-body"></tbody>
      </table>
      </div>
      <div class="pager" id="ledger-pager"></div>
    </div>
  </div>

  <!-- 使用趋势 -->
  <div id="page-usage" class="page">
    <div class="card">
      <h2>消费趋势 (近 30 天)</h2>
      <div class="card-note">按天聚合积分消耗，便于观察近期使用节奏。</div>
      <div class="chart-row" id="usage-chart"></div>
      <div class="chart-labels" id="usage-labels"></div>
    </div>
  </div>

  <!-- 当前套餐 -->
  <div id="page-plan" class="page">
    <div class="split-grid">
      <div class="card">
        <h2>套餐信息</h2>
        <div class="card-note">展示当前套餐和最近生效的订阅信息。未开通订阅时直接显示无套餐。</div>
        <div id="plan-info"></div>
      </div>
      <div class="card">
        <h2>当前计价</h2>
        <div class="card-note">不同事件类型对应的积分成本。</div>
        <div class="pricing-row" id="pricing-row"></div>
      </div>
    </div>
  </div>
  </div>
</div>
</div>
</div>

<script>
(function() {
  var portalToken = new URLSearchParams(location.search).get("t") || "";
  var allowedPages = ["account", "notifications", "balance", "topup", "billing", "usage", "plan"];

  // ── Navigation ──
  const navItems = document.querySelectorAll(".nav-item[data-page]");
  const pages = document.querySelectorAll(".page");
  const pageTitle = document.getElementById("page-title");
  const notificationsNavBadge = document.getElementById("notifications-nav-badge");
  const pageTitles = {
    account: "账户信息", notifications: "通知中心", balance: "余额概览", topup: "充值/赠送记录",
    billing: "消费记录", usage: "使用趋势", plan: "当前套餐"
  };
  const notificationCategoryButtons = document.querySelectorAll("[data-notification-category]");
  const markNotificationsReadButton = document.getElementById("mark-notifications-read");
  const markNotificationsUnreadButton = document.getElementById("mark-notifications-unread");
  const sendVerificationCodeButton = document.getElementById("send-verification-code-button");
  const confirmVerificationButton = document.getElementById("confirm-verification-button");
  const verificationCodeInput = document.getElementById("verification-code-input");
  const verificationStatusValue = document.getElementById("email-verification-status");
  const verificationEmailValue = document.getElementById("verification-email");
  const verificationRequestMessage = document.getElementById("verification-request-message");
  const verificationConfirmMessage = document.getElementById("verification-confirm-message");
  const myInviteCodeValue = document.getElementById("my-invite-code");
  const inviteBindingStatusValue = document.getElementById("invite-binding-status");
  const inviteCodeInput = document.getElementById("invite-code-input");
  const bindInviteCodeButton = document.getElementById("bind-invite-code-button");
  const bindInviteCodeMessage = document.getElementById("bind-invite-code-message");
  const topupViewButtons = document.querySelectorAll("[data-topup-view]");
  const notificationsBody = document.getElementById("notifications-body");
  const notificationState = { category: "system", readMap: {}, storageKey: "" };
  var currentAccountData = null;
  var verificationGateState = { enforced: false, verified: false };

  navItems.forEach(function(item) {
    item.addEventListener("click", function() {
      setActivePage(item.getAttribute("data-page"), true);
    });
  });

  topupViewButtons.forEach(function(button) {
    button.addEventListener("click", function() {
      setTopupView(button.getAttribute("data-topup-view") || "records");
    });
  });

  notificationCategoryButtons.forEach(function(button) {
    button.addEventListener("click", function() {
      setNotificationCategory(button.getAttribute("data-notification-category") || "system");
      if (currentAccountData) {
        renderNotifications(currentAccountData);
      }
    });
  });

  if (markNotificationsReadButton) {
    markNotificationsReadButton.addEventListener("click", function() {
      updateNotificationReadStateForCategory(notificationState.category, true);
      renderNotifications(currentAccountData || {});
    });
  }

  if (markNotificationsUnreadButton) {
    markNotificationsUnreadButton.addEventListener("click", function() {
      updateNotificationReadStateForCategory(notificationState.category, false);
      renderNotifications(currentAccountData || {});
    });
  }

  if (notificationsBody) {
    notificationsBody.addEventListener("click", function(event) {
      var target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      var actionButton = target.closest("[data-notification-toggle-id]");
      if (!actionButton) {
        return;
      }
      var notificationId = actionButton.getAttribute("data-notification-toggle-id") || "";
      if (!notificationId) {
        return;
      }
      toggleNotificationRead(notificationId);
      renderNotifications(currentAccountData || {});
    });
  }

  if (sendVerificationCodeButton) {
    sendVerificationCodeButton.addEventListener("click", function() {
      verificationRequestMessage.textContent = "发送中…";
      apiPost("/portal/api/account/email-verification/request").then(function(data) {
        verificationRequestMessage.textContent = "验证码已发送到 " + (data.email || "当前邮箱") + "，请在邮箱中查收。";
      }).catch(function(error) {
        verificationRequestMessage.textContent = "发送失败：" + error.message;
      });
    });
  }

  if (confirmVerificationButton) {
    confirmVerificationButton.addEventListener("click", function() {
      var code = (verificationCodeInput && verificationCodeInput.value || "").trim();
      if (!code) {
        verificationConfirmMessage.textContent = "请先输入邮箱验证码。";
        return;
      }
      verificationConfirmMessage.textContent = "验证中…";
      apiPost("/portal/api/account/email-verification/confirm", { code: code }).then(function(data) {
        if (verificationCodeInput) verificationCodeInput.value = "";
        verificationConfirmMessage.textContent = "邮箱验证成功，注册已完成；新用户奖励已自动结算。";
        renderAccount(data);
      }).catch(function(error) {
        verificationConfirmMessage.textContent = "验证失败：" + error.message;
      });
    });
  }

  if (bindInviteCodeButton) {
    bindInviteCodeButton.addEventListener("click", function() {
      var inviteCode = (inviteCodeInput && inviteCodeInput.value || "").trim();
      if (!inviteCode) {
        bindInviteCodeMessage.textContent = "请先输入邀请码。";
        return;
      }
      bindInviteCodeMessage.textContent = "绑定中…";
      apiPost("/portal/api/account/referral/bind", { invite_code: inviteCode }).then(function(data) {
        if (inviteCodeInput) inviteCodeInput.value = "";
        bindInviteCodeMessage.textContent = "邀请码绑定成功。若你已完成邮箱验证，邀请奖励也已同步结算。";
        renderAccount(data);
      }).catch(function(error) {
        bindInviteCodeMessage.textContent = "绑定失败：" + error.message;
      });
    });
  }

  var usageLoaded = false, ledgerLoaded = false, topupLoaded = false;

  function setActivePage(target, syncHash) {
    if (verificationGateState.enforced && !verificationGateState.verified && target !== "account") {
      target = "account";
    }
    if (allowedPages.indexOf(target) === -1) {
      target = "account";
    }
    navItems.forEach(function(n) {
      n.classList.toggle("active", n.getAttribute("data-page") === target);
    });
    pages.forEach(function(p) {
      p.classList.toggle("active", p.id === "page-" + target);
    });
    pageTitle.textContent = pageTitles[target] || "";
    if (syncHash && location.hash !== "#" + target) {
      history.replaceState(null, "", location.pathname + location.search + "#" + target);
    }
    if (target === "usage" && !usageLoaded) { loadUsageChart(); usageLoaded = true; }
    if (target === "billing" && !ledgerLoaded) { loadLedger(1); ledgerLoaded = true; }
    if (target === "topup" && !topupLoaded) { loadTopup(1); topupLoaded = true; }
  }

  function applyVerificationGate(identityVerification) {
    var enforced = !!identityVerification.email_verification_required_before_portal_use;
    var verified = !!identityVerification.email_verified;
    verificationGateState.enforced = enforced;
    verificationGateState.verified = verified;
    navItems.forEach(function(item) {
      var page = item.getAttribute("data-page") || "account";
      var locked = enforced && !verified && page !== "account";
      item.classList.toggle("locked", locked);
      item.setAttribute("aria-disabled", locked ? "true" : "false");
      item.title = locked ? "完成邮箱验证后才能进入此页面" : "";
    });
    var banner = document.getElementById("verification-gate-banner");
    if (!banner) {
      return;
    }
    if (enforced && !verified) {
      banner.style.display = "block";
      banner.textContent = "当前已开启首次登录邮箱验证门槛。完成邮箱验证前，你只能停留在账户信息页并使用验证码验证入口，充值、消费、通知和套餐能力会被暂时锁定。";
      setActivePage("account", false);
      return;
    }
    banner.style.display = "none";
    banner.textContent = "";
  }

  // ── API helpers ──
  function showError(msg) {
    var el = document.getElementById("error-panel");
    el.textContent = msg;
    el.style.display = "block";
  }
  function renderEmptyRow(colSpan, text) {
    return '<tr class="empty-row"><td colspan="' + colSpan + '">' + esc(text) + '</td></tr>';
  }
  function fmtTime(ts) {
    if (!ts) return "-";
    var d = new Date(ts);
    if (isNaN(d.getTime())) return String(ts).slice(0, 19);
    var pad = function(n) { return String(n).padStart(2, "0"); };
    return pad(d.getMonth()+1) + "-" + pad(d.getDate()) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }
  function fmtTimeFull(ts) {
    if (!ts) return "-";
    var d = new Date(ts);
    if (isNaN(d.getTime())) return String(ts).slice(0, 19);
    var pad = function(n) { return String(n).padStart(2, "0"); };
    return d.getFullYear() + "-" + pad(d.getMonth()+1) + "-" + pad(d.getDate()) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }
  function fmtDay(ds) { return ds ? String(ds).slice(5) : ""; }
  function intVal(v) { return parseInt(v, 10) || 0; }
  function esc(s) { var el = document.createElement("span"); el.textContent = s; return el.innerHTML; }

  function withPortalToken(path) {
    if (!portalToken) return path;
    return path + (path.indexOf("?") === -1 ? "?" : "&") + "t=" + encodeURIComponent(portalToken);
  }

  document.getElementById("route-account-link").href = withPortalToken("/portal/account");
  document.getElementById("route-products-link").href = withPortalToken("/portal/products");
  document.getElementById("route-guide-link").href = withPortalToken("/portal/guide");
  document.getElementById("open-webui-home-link").href = "__OPENWEBUI_HOME_URL__";

  function buildNotificationStorageKey(userId) {
    return "xiamimate.portal.notifications:" + String(userId || "anonymous");
  }

  function loadNotificationState(userId) {
    notificationState.storageKey = buildNotificationStorageKey(userId);
    notificationState.readMap = {};
    try {
      var raw = window.localStorage.getItem(notificationState.storageKey);
      if (!raw) {
        return;
      }
      var parsed = JSON.parse(raw);
      var readIds = Array.isArray(parsed && parsed.readIds) ? parsed.readIds : [];
      readIds.forEach(function(notificationId) {
        if (notificationId) {
          notificationState.readMap[String(notificationId)] = true;
        }
      });
    } catch (error) {
      notificationState.readMap = {};
    }
  }

  function persistNotificationState() {
    if (!notificationState.storageKey) {
      return;
    }
    try {
      var readIds = Object.keys(notificationState.readMap).filter(function(notificationId) {
        return notificationState.readMap[notificationId];
      });
      window.localStorage.setItem(notificationState.storageKey, JSON.stringify({ readIds: readIds }));
    } catch (error) {
      // Ignore storage failures and keep the page usable.
    }
  }

  function isNotificationRead(notificationId) {
    return !!notificationState.readMap[String(notificationId || "")];
  }

  function setNotificationRead(notificationId, read) {
    var normalizedId = String(notificationId || "");
    if (!normalizedId) {
      return;
    }
    if (read) {
      notificationState.readMap[normalizedId] = true;
    } else {
      delete notificationState.readMap[normalizedId];
    }
    persistNotificationState();
  }

  function toggleNotificationRead(notificationId) {
    setNotificationRead(notificationId, !isNotificationRead(notificationId));
  }

  function applyNotificationReadState(groups) {
    Object.keys(groups).forEach(function(category) {
      groups[category] = (groups[category] || []).map(function(item) {
        return Object.assign({}, item, { unread: !isNotificationRead(item.id) });
      });
    });
    return groups;
  }

  function updateNotificationReadStateForCategory(category, read) {
    if (!currentAccountData) {
      return;
    }
    var groups = applyNotificationReadState(buildNotificationGroups(currentAccountData));
    (groups[category] || []).forEach(function(item) {
      setNotificationRead(item.id, read);
    });
  }

  function apiRequest(path, options) {
    var fetchOptions = Object.assign({ credentials: "same-origin" }, options || {});
    if (fetchOptions.body !== undefined && typeof fetchOptions.body !== "string") {
      fetchOptions.headers = Object.assign({ "Content-Type": "application/json" }, fetchOptions.headers || {});
      fetchOptions.body = JSON.stringify(fetchOptions.body);
    }
    return fetch(withPortalToken(path), fetchOptions).then(function(resp) {
      if (!resp.ok) {
        return resp.json().catch(function() { return {}; }).then(function(body) {
          throw new Error(body.detail || body.message || resp.statusText);
        });
      }
      return resp.json().then(function(json) {
        if (json.success !== true) throw new Error(json.message || "请求失败");
        return json.data;
      });
    });
  }

  function apiFetch(path) {
    return apiRequest(path);
  }

  function apiPost(path, body) {
    var options = { method: "POST" };
    if (body !== undefined) {
      options.body = body;
    }
    return apiRequest(path, options);
  }

  // ── Account page ──
  function loadAccount() {
    apiFetch("/portal/api/account").then(function(data) {
      renderAccount(data);
    }).catch(function(e) {
      showError("加载失败：" + e.message);
    });
  }

  function renderAccount(data) {
    currentAccountData = data;
    var user = data.user || {};
    var identityVerification = data.identity_verification || {};
    var emailVerified = !!identityVerification.email_verified;
    var invitedBy = identityVerification.invited_by || null;
    applyVerificationGate(identityVerification);
    loadNotificationState(user.user_id || user.email || "anonymous");
    var pa = data.points_account || {};
    var balanceBreakdown = data.balance_breakdown || {};
    var subs = data.subscriptions || [];
    var activeSubscription = findActiveSubscription(subs);
    var planTier = activeSubscription ? normalizePlanLabel(data.plan_tier || user.plan_tier || activeSubscription.package_code || "已开通") : "无套餐";
    var accountStatusText = emailVerified
      ? (user.email || user.user_id || "当前用户") + " 已完成邮箱验证"
      : (user.email || user.user_id || "当前用户") + " 待完成邮箱验证";

    document.getElementById("user-info").textContent =
      (user.display_name || user.user_id || "用户") + "  ·  " + (user.email || "");
    document.getElementById("hero-balance").textContent = intVal(pa.balance_points);

    // Account info
    var infoHtml = [
      infoRow("用户名", user.display_name || user.user_id || "-"),
      infoRow("邮箱", user.email || "-"),
      infoRow("邮箱验证", renderStatusBadge(emailVerified ? "已验证" : "待验证", emailVerified ? "ok" : "pending")),
      infoRow("用户 ID", user.user_id || "-"),
      infoRow("账号状态", esc(accountStatusText)),
      infoRow("当前套餐", renderPlanBadge(planTier, !activeSubscription)),
      infoRow("当前余额", '<strong>' + intVal(pa.balance_points) + '</strong> 积分'),
      infoRow("月包余额", '<strong>' + intVal(balanceBreakdown.subscription_balance_points) + '</strong> 积分'),
      infoRow("充值包余额", '<strong>' + intVal(balanceBreakdown.recharge_balance_points) + '</strong> 积分'),
    ];
    document.getElementById("account-info").innerHTML = infoHtml.join("");

    if (verificationStatusValue) {
      verificationStatusValue.innerHTML = renderStatusBadge(emailVerified ? "已验证" : "待验证", emailVerified ? "ok" : "pending");
    }
    if (verificationEmailValue) {
      verificationEmailValue.textContent = identityVerification.email || user.email || "-";
    }
    if (verificationRequestMessage) {
      verificationRequestMessage.textContent = emailVerified
        ? ("已于 " + fmtTimeFull(identityVerification.email_verified_at) + " 完成邮箱验证。")
        : (identityVerification.email_verification_required_before_portal_use
          ? "当前已开启首次登录强制邮箱验证；验证码会发送到当前登录邮箱，验证通过前其他账户能力会被锁定。"
          : "注册成功以邮箱验证通过为准；验证码会发送到当前登录邮箱。");
    }
    if (verificationConfirmMessage) {
      verificationConfirmMessage.textContent = emailVerified
        ? "新用户 500 积分已按注册成功规则处理。"
        : "验证成功后，新用户自动到账 500 积分。";
    }
    if (sendVerificationCodeButton) {
      sendVerificationCodeButton.disabled = emailVerified;
    }
    if (confirmVerificationButton) {
      confirmVerificationButton.disabled = emailVerified;
    }
    if (verificationCodeInput) {
      verificationCodeInput.disabled = emailVerified;
    }
    if (myInviteCodeValue) {
      myInviteCodeValue.textContent = identityVerification.invite_code || user.invite_code || "-";
    }
    if (inviteBindingStatusValue) {
      inviteBindingStatusValue.innerHTML = invitedBy
        ? ("已绑定邀请人 <strong>" + esc(invitedBy.inviter_display_name || invitedBy.inviter_user_id || "-") + "</strong>（邀请码 " + esc(invitedBy.invite_code || "-") + "）")
        : "暂未绑定邀请人，不影响你自己的新用户 500 积分。";
    }
    if (bindInviteCodeMessage) {
      bindInviteCodeMessage.textContent = invitedBy
        ? "当前账号已绑定邀请关系；若你已完成邮箱验证，邀请人奖励已同步处理。"
        : "如果你是被邀请来的，请先绑定邀请码，再完成邮箱验证。";
    }
    if (bindInviteCodeButton) {
      bindInviteCodeButton.disabled = !identityVerification.can_bind_invite_code;
    }
    if (inviteCodeInput) {
      inviteCodeInput.disabled = !identityVerification.can_bind_invite_code;
    }

    // KPIs (balance page)
    var kpis = [
      { label: "当前余额", value: intVal(balanceBreakdown.total_balance_points || pa.balance_points) },
      { label: "月包余额", value: intVal(balanceBreakdown.subscription_balance_points) },
      { label: "充值包余额", value: intVal(balanceBreakdown.recharge_balance_points) },
      { label: "其他赠送余额", value: intVal(balanceBreakdown.other_balance_points) },
      { label: "累计赠送", value: intVal(pa.lifetime_granted_points) },
      { label: "累计购买", value: intVal(pa.lifetime_purchased_points) },
      { label: "累计消费", value: intVal(pa.lifetime_spent_points) },
    ];
    document.getElementById("kpi-row").innerHTML = kpis.map(function(k) {
      return '<div class="kpi"><div class="value">' + k.value + '</div><div class="label">' + k.label + '</div></div>';
    }).join("");

    // Plan page
    var planRows = [
      infoRow("当前套餐", renderPlanBadge(planTier, !activeSubscription)),
    ];
    if (activeSubscription) {
      planRows.push(infoRow("订阅状态", esc(activeSubscription.status || "-")));
      planRows.push(infoRow("套餐代码", esc(activeSubscription.package_code || "-")));
      planRows.push(infoRow("套餐生效时间", esc(fmtTimeFull(activeSubscription.current_period_start))));
      planRows.push(infoRow("套餐有效至", esc(fmtTimeFull(activeSubscription.current_period_end))));
      planRows.push(infoRow("月度积分", activeSubscription.monthly_points || "-"));
      planRows.push(infoRow("积分有效期", "月包积分在当前套餐有效期结束后自动清零"));
      planRows.push(infoRow("消费顺序", "优先扣减月包余额，不足时再扣充值包余额"));
    }
    document.getElementById("plan-info").innerHTML = planRows.join("");

    // Pricing pills
    var costMap = data.point_cost_by_event || {};
    var displayMap = data.event_pricing_display || {};
    document.getElementById("pricing-row").innerHTML = Object.keys(costMap).map(function(et) {
      var label = displayMap[et] || et;
      return '<div class="pricing-pill"><span class="name">' + esc(label) + '</span><span class="cost">' + costMap[et] + ' 积分/次</span></div>';
    }).join("");

    renderNotifications(data);
    renderInvoiceSummary(data);
  }

  function infoRow(label, value) {
    return '<div class="info-row"><div class="info-label">' + esc(label) + '</div><div class="info-value">' + value + '</div></div>';
  }

  function renderPlanBadge(label, isEmpty) {
    return '<span class="plan-badge' + (isEmpty ? ' empty' : '') + '">' + esc(label) + '</span>';
  }

  function renderStatusBadge(text, type) {
    return '<span class="status-badge ' + esc(type || 'pending') + '">' + esc(text) + '</span>';
  }

  function normalizePlanLabel(label) {
    var normalized = String(label || "").trim().toLowerCase();
    if (!normalized || normalized === "free") return "无套餐";
    return normalized;
  }

  function findActiveSubscription(subscriptions) {
    var now = Date.now();
    for (var i = 0; i < subscriptions.length; i += 1) {
      var sub = subscriptions[i] || {};
      var endTime = sub.current_period_end ? new Date(sub.current_period_end).getTime() : null;
      if ((sub.status || "").toLowerCase() === "active" && (!endTime || endTime > now)) {
        return sub;
      }
    }
    return null;
  }

  function buildNotificationGroups(data) {
    var groups = { user: [], system: [] };
    var pointsAccount = data.points_account || {};
    var recentOrders = data.recent_orders || [];
    var activeSubscription = findActiveSubscription(data.subscriptions || []);
    var user = data.user || {};
    recentOrders.filter(function(order) {
      return order.status === "paid";
    }).slice(0, 4).forEach(function(order) {
      var isSubscription = order.product_type === "monthly_subscription";
      groups.system.push({
        id: (isSubscription ? "system:subscription-paid:" : "system:recharge-paid:") + String(order.order_id || order.provider_trade_no || order.created_at || "order"),
        tag: isSubscription ? "套餐开通" : "充值到账",
        level: "success",
        title: isSubscription ? "订阅已生效" : "充值已到账",
        desc: isSubscription
          ? (order.package_code || "当前套餐") + " 已开通，本次到账 " + intVal(order.points_amount) + " 积分。"
          : (order.package_code || "充值订单") + " 支付成功，本次到账 " + intVal(order.points_amount) + " 积分。",
        time: order.paid_at || order.created_at || "-",
      });
    });
    if (intVal(pointsAccount.balance_points) > 0 && intVal(pointsAccount.balance_points) <= 500) {
      groups.user.push({
        id: "user:low-balance:" + String(pointsAccount.updated_at || user.updated_at || user.user_id || "balance"),
        tag: "余额提醒",
        level: "warning",
        title: "账户余额偏低",
        desc: "当前可用积分低于 500，建议提前查看订阅与充值页，避免使用中断。",
        time: pointsAccount.updated_at || user.updated_at || "-",
      });
    }
    if (activeSubscription) {
      groups.system.push({
        id: "system:subscription-period:" + String(activeSubscription.subscription_id || activeSubscription.package_code || "subscription") + ":" + String(activeSubscription.current_period_end || ""),
        tag: "套餐有效期",
        level: "info",
        title: "当前套餐有效中",
        desc: "当前套餐自 " + fmtTimeFull(activeSubscription.current_period_start) + " 生效，至 " + fmtTimeFull(activeSubscription.current_period_end) + " 到期；月包积分将在有效期结束后自动清零。",
        time: activeSubscription.current_period_start || new Date().toISOString(),
      });
    }
    groups.system.push({
      id: "system:invoice-entry:2026-04-17",
      tag: "活动提醒",
      level: "info",
      title: "发票管理入口已预留",
      desc: "充值/赠送记录页已经预留发票管理二级页，后续可直接接企业抬头、邮箱收票、按订单申请开票和开票状态跟踪。",
      time: "2026-04-17T00:00:00Z",
    });
    groups.system.push({
      id: "system:notifications-persistence:2026-04-17",
      tag: "功能更新",
      level: "info",
      title: "通知中心已支持已读状态保留",
      desc: "通知中心支持系统通知和用户通知两类消息，并会在当前浏览器保留你的已读状态，刷新页面不会重置。",
      time: "2026-04-17T00:00:00Z",
    });
    return groups;
  }

  function setNotificationCategory(category) {
    notificationState.category = category === "user" ? "user" : "system";
    notificationCategoryButtons.forEach(function(button) {
      button.classList.toggle("active", button.getAttribute("data-notification-category") === notificationState.category);
    });
    var panelTitle = document.getElementById("notifications-panel-title");
    var panelNote = document.getElementById("notifications-panel-note");
    if (panelTitle) {
      panelTitle.textContent = notificationState.category === "user" ? "用户通知" : "系统通知";
    }
    if (panelNote) {
      panelNote.textContent = notificationState.category === "user"
        ? "用于查看与你账户直接相关的到账、余额和套餐提醒。"
        : "用于查看系统活动、功能更新和套餐有效期规则等平台通知，已读状态会在当前浏览器保留。";
    }
  }

  function renderNotifications(data) {
    var groups = applyNotificationReadState(buildNotificationGroups(data));
    var items = groups[notificationState.category] || [];
    var unreadCount = items.filter(function(item) { return item.unread; }).length;
    var totalUnread = Object.keys(groups).reduce(function(sum, key) {
      return sum + (groups[key] || []).filter(function(item) { return item.unread; }).length;
    }, 0);
    document.getElementById("notifications-meta").textContent = "共 " + items.length + " 条，未读 " + unreadCount + " 条";
    setNotificationCategory(notificationState.category);
    if (markNotificationsReadButton) {
      markNotificationsReadButton.textContent = unreadCount > 0 ? "全部设为已读" : "当前分类已全部读完";
      markNotificationsReadButton.disabled = unreadCount === 0;
    }
    if (markNotificationsUnreadButton) {
      markNotificationsUnreadButton.disabled = items.length === 0 || unreadCount === items.length;
    }
    if (notificationsNavBadge) {
      notificationsNavBadge.textContent = String(totalUnread);
      notificationsNavBadge.style.display = totalUnread > 0 ? "inline-flex" : "none";
    }
    document.getElementById("notifications-body").innerHTML = items.length ? items.map(function(item) {
      var unreadClass = item.unread ? ' unread' : '';
      var unreadDot = item.unread ? '<span class="notification-unread-dot"></span>' : '';
      var toggleLabel = item.unread ? '标为已读' : '标为未读';
      return '<div class="notification-card' + unreadClass + '">' +
        '<div class="notification-top"><div class="notification-title-row">' + unreadDot + '<div class="notification-title">' + esc(item.title) + '</div></div><span class="notification-tag ' + esc(item.level) + '">' + esc(item.tag) + '</span></div>' +
        '<div class="notification-desc">' + esc(item.desc) + '</div>' +
        '<div class="notification-footer"><div class="notification-meta">更新时间：' + esc(fmtTime(item.time)) + '</div><button type="button" class="notification-toggle-link" data-notification-toggle-id="' + esc(item.id) + '">' + toggleLabel + '</button></div>' +
      '</div>';
    }).join("") : '<div class="notification-card"><div class="notification-title">暂无通知</div><div class="notification-desc">当前没有需要提醒的充值到账、余额提醒或功能更新。</div></div>';
  }

  function renderInvoiceSummary(data) {
    var paidOrders = (data.recent_orders || []).filter(function(order) {
      return order.status === "paid";
    });
    document.getElementById("invoice-paid-order-count").textContent = String(paidOrders.length);
    document.getElementById("invoice-latest-order").textContent = paidOrders.length ? paidOrders[0].order_id : "暂无";
  }

  function setTopupView(target) {
    var nextTarget = target === "invoice" ? "invoice" : "records";
    topupViewButtons.forEach(function(button) {
      button.classList.toggle("active", button.getAttribute("data-topup-view") === nextTarget);
    });
    document.getElementById("topup-records-view").classList.toggle("active", nextTarget === "records");
    document.getElementById("topup-invoice-view").classList.toggle("active", nextTarget === "invoice");
  }

  // ── Usage chart ──
  function loadUsageChart() {
    if (verificationGateState.enforced && !verificationGateState.verified) {
      return;
    }
    apiFetch("/portal/api/usage-daily?days=30").then(function(data) {
      renderUsageChart(data.rows || []);
    }).catch(function() {});
  }

  function renderUsageChart(rows) {
    var byDay = {};
    rows.forEach(function(r) {
      var d = String(r.day || "").slice(0, 10);
      byDay[d] = (byDay[d] || 0) + intVal(r.total_units);
    });
    var days = [];
    var now = new Date();
    for (var i = 29; i >= 0; i--) {
      var d = new Date(now);
      d.setDate(d.getDate() - i);
      var key = d.toISOString().slice(0, 10);
      days.push({ day: key, units: byDay[key] || 0 });
    }
    var maxU = Math.max(1, Math.max.apply(null, days.map(function(d) { return d.units; })));
    document.getElementById("usage-chart").innerHTML = days.map(function(d) {
      var h = Math.max(2, (d.units / maxU) * 96);
      return '<div class="chart-bar" style="height:' + h + 'px" data-tip="' + fmtDay(d.day) + ': ' + d.units + '积分"></div>';
    }).join("");
    document.getElementById("usage-labels").innerHTML = days.map(function(d, i) {
      var show = i % 5 === 0 || i === days.length - 1;
      return '<span>' + (show ? fmtDay(d.day) : '') + '</span>';
    }).join("");
  }

  // ── Billing ledger (消费记录) ──
  var currentLedgerPage = 1;
  function loadLedger(page) {
    if (verificationGateState.enforced && !verificationGateState.verified) {
      return;
    }
    currentLedgerPage = page || 1;
    apiFetch("/portal/api/ledger?page=" + currentLedgerPage + "&page_size=20&filter=spend").then(function(data) {
      renderLedger(data);
    }).catch(function() {});
  }

  function renderLedger(data) {
    var rows = data.rows || [];
    var total = data.total || 0;
    var pageSize = data.page_size || 20;
    var totalPages = Math.max(1, Math.ceil(total / pageSize));
    document.getElementById("ledger-meta").textContent = "共 " + total + " 条，本页 " + rows.length + " 条";

    document.getElementById("ledger-body").innerHTML = rows.length ? rows.map(function(r) {
      var delta = intVal(r.points_delta);
      var cls = delta >= 0 ? "positive" : "negative";
      var sign = delta >= 0 ? "+" : "";
      return '<tr><td>' + fmtTime(r.created_at) + '</td><td>' + esc(r.entry_type || "") +
        '</td><td>' + esc(r.event_type || "") + '</td><td class="' + cls + '">' + sign + delta +
        '</td><td>' + intVal(r.balance_after_points) + '</td><td>' + esc(r.description || "") + '</td></tr>';
    }).join("") : renderEmptyRow(6, "暂无消费记录");

    document.getElementById("ledger-pager").innerHTML =
      '<button id="lg-prev" ' + (currentLedgerPage <= 1 ? 'disabled' : '') + '>上一页</button>' +
      '<span class="pager-status">第 ' + currentLedgerPage + ' / ' + totalPages + ' 页</span>' +
      '<button id="lg-next" ' + (currentLedgerPage >= totalPages ? 'disabled' : '') + '>下一页</button>';
    document.getElementById("lg-prev").onclick = function() { loadLedger(currentLedgerPage - 1); };
    document.getElementById("lg-next").onclick = function() { loadLedger(currentLedgerPage + 1); };
  }

  // ── Topup records (充值/赠送记录) ──
  var currentTopupPage = 1;
  function loadTopup(page) {
    if (verificationGateState.enforced && !verificationGateState.verified) {
      return;
    }
    currentTopupPage = page || 1;
    apiFetch("/portal/api/ledger?page=" + currentTopupPage + "&page_size=20&filter=topup").then(function(data) {
      renderTopup(data);
    }).catch(function() {});
  }

  function renderTopup(data) {
    var rows = data.rows || [];
    var total = data.total || 0;
    var pageSize = data.page_size || 20;
    var totalPages = Math.max(1, Math.ceil(total / pageSize));
    document.getElementById("topup-meta").textContent = "共 " + total + " 条，本页 " + rows.length + " 条";

    document.getElementById("topup-body").innerHTML = rows.length ? rows.map(function(r) {
      var delta = intVal(r.points_delta);
      return '<tr><td>' + fmtTime(r.created_at) + '</td><td>' + esc(r.entry_type || "") +
        '</td><td class="positive">+' + delta + '</td><td>' + intVal(r.balance_after_points) +
        '</td><td>' + esc(r.description || "") + '</td></tr>';
    }).join("") : renderEmptyRow(5, "暂无充值或赠送记录");

    document.getElementById("topup-pager").innerHTML =
      '<button id="tp-prev" ' + (currentTopupPage <= 1 ? 'disabled' : '') + '>上一页</button>' +
      '<span class="pager-status">第 ' + currentTopupPage + ' / ' + totalPages + ' 页</span>' +
      '<button id="tp-next" ' + (currentTopupPage >= totalPages ? 'disabled' : '') + '>下一页</button>';
    document.getElementById("tp-prev").onclick = function() { loadTopup(currentTopupPage - 1); };
    document.getElementById("tp-next").onclick = function() { loadTopup(currentTopupPage + 1); };
  }

  // ── Boot ──
  var initialPage = (location.hash || "").replace(/^#/, "");
  loadAccount();
  setActivePage(initialPage || "account", false);
})();
</script>
</body>
</html>""".replace("__OPENWEBUI_HOME_URL__", openwebui_home_url)
