from __future__ import annotations

from html import escape

from data_platform.api.chat_backend_portal_public_html import _load_contact_config
from data_platform.chat_backend.domains.portal.service import _portal_base_url


def render_portal_html() -> str:
  openwebui_home_url = escape(_portal_base_url())
  contact = _load_contact_config()
  contact_email = escape(contact.get("contact_email") or "")
  feedback_url = escape(contact.get("feedback_url") or "")
  wechat_qr_data_url = contact.get("wechat_qr_base64") or ""
  wechat_qr_html = (
    f'<div class="wechat-qr-wrap"><img class="wechat-qr-image" src="{wechat_qr_data_url}" alt="企微二维码" /></div>'
    if wechat_qr_data_url
    else '<div class="contact-modal-note">当前未找到企微二维码图片，请联系管理员上传。</div>'
  )
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
      .top-secondary-link {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 40px;
        padding: 0 16px;
        border-radius: 12px;
        border: 1px solid rgba(17, 75, 95, 0.18);
        background: rgba(255, 251, 245, 0.82);
        color: var(--accent);
        text-decoration: none;
        font-size: 0.84rem;
        font-weight: 600;
        cursor: pointer;
        transition: background 0.15s, border-color 0.15s, color 0.15s;
      }
      .top-secondary-link:hover {
        background: rgba(17, 75, 95, 0.08);
        border-color: rgba(17, 75, 95, 0.3);
        color: #0f3f50;
      }
    .top-route-link.active {
      background: var(--accent-soft);
      color: var(--accent);
      border-color: rgba(17, 75, 95, 0.18);
    }
      .gate-banner-actions {
        margin-top: 12px;
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
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
    .top-icon-link svg {
      width: 19px;
      height: 19px;
    }
    .top-icon-link.mail-link {
      color: var(--accent);
    }
    .top-icon-link.wechat-link {
      color: #0f766e;
    }
    .top-icon-link.feedback-link {
      color: var(--accent-2);
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
    .contact-modal {
      position: fixed;
      inset: 0;
      z-index: 1200;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
      background: rgba(30, 42, 47, 0.38);
      backdrop-filter: blur(8px);
    }
    .contact-modal[hidden] {
      display: none;
    }
    .contact-modal-card {
      width: min(420px, calc(100vw - 32px));
      background: rgba(255, 251, 245, 0.98);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: var(--shadow);
      padding: 22px;
      display: grid;
      gap: 14px;
    }
    .contact-modal-top {
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 12px;
    }
    .contact-modal-title {
      font-size: 1.08rem;
      font-weight: 700;
      margin: 0;
    }
    .contact-modal-close {
      width: 36px;
      height: 36px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: rgba(255, 251, 245, 0.92);
      color: var(--muted);
      cursor: pointer;
    }
    .contact-modal-close:hover {
      color: var(--accent);
      background: var(--accent-soft);
    }
    .contact-modal-note {
      color: var(--muted);
      font-size: 0.84rem;
      line-height: 1.7;
    }
    .wechat-id-box {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: linear-gradient(180deg, rgba(255, 251, 245, 0.98), rgba(244, 236, 223, 0.9));
      padding: 16px 18px;
    }
    .wechat-id-label {
      color: var(--muted);
      font-size: 0.78rem;
      margin-bottom: 6px;
    }
    .wechat-id-value {
      font-size: 1.24rem;
      font-weight: 700;
      letter-spacing: 0.01em;
    }
    .wechat-qr-wrap {
      display: flex;
      justify-content: center;
      padding: 4px 0 2px;
    }
    .wechat-qr-image {
      width: min(100%, 320px);
      border-radius: 18px;
      border: 1px solid rgba(17, 75, 95, 0.12);
      background: #fff;
      box-shadow: 0 14px 34px rgba(30, 42, 47, 0.1);
    }
    .contact-modal-actions {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .contact-action-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 42px;
      padding: 0 16px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(255, 251, 245, 0.82);
      color: var(--accent);
      text-decoration: none;
      cursor: pointer;
      font-size: 0.84rem;
      font-weight: 600;
    }
    .contact-action-btn:hover {
      background: var(--accent-soft);
      border-color: rgba(17, 75, 95, 0.18);
    }
    .contact-inline-status {
      color: var(--muted);
      font-size: 0.8rem;
    }
    .contact-inline-status:empty {
      display: none;
    }
    #dify-chatbot-bubble-button {
      background-color: #1C64F2 !important;
    }
    #dify-chatbot-bubble-window {
      width: 24rem !important;
      height: 40rem !important;
      max-width: calc(100vw - 24px) !important;
      max-height: calc(100vh - 24px) !important;
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
    .table-main-text {
      color: var(--ink);
      font-weight: 600;
      line-height: 1.5;
    }
    .table-sub-text {
      margin-top: 4px;
      color: var(--muted);
      font-size: 0.76rem;
      line-height: 1.6;
    }
    .ledger-policy-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      margin-bottom: 16px;
    }
    .ledger-policy-card {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255, 251, 245, 0.86);
      padding: 16px 18px;
    }
    .source-chip-row {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .source-chip {
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.74rem;
      font-weight: 700;
      white-space: nowrap;
    }
    .source-chip.subscription {
      background: rgba(17, 75, 95, 0.12);
      color: var(--accent);
    }
    .source-chip.recharge {
      background: rgba(15, 118, 110, 0.12);
      color: var(--ok);
    }
    .source-chip.other {
      background: rgba(217, 119, 6, 0.12);
      color: #9a6700;
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
          <button type="button" class="top-secondary-link" id="portal-logout-button">退出登录</button>
          <a class="top-icon-link mail-link" href="mailto:__CONTACT_EMAIL__" aria-label="邮件联系" title="邮件联系">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M3.75 6.75h16.5v10.5H3.75z" />
              <path d="m4.5 7.5 7.5 6 7.5-6" />
            </svg>
          </a>
          <button type="button" class="top-icon-link wechat-link" id="wechat-contact-trigger" aria-label="企微联系" title="企微联系">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M9.2 5.5c-3.5 0-6.2 2.2-6.2 5.1 0 1.6.8 3 2.2 4l-.6 2.4 2.6-1.3c.6.1 1.3.2 2 .2 3.5 0 6.2-2.2 6.2-5.1S12.7 5.5 9.2 5.5Z" />
              <path d="M15.5 10.2c3 0 5.5 1.9 5.5 4.5 0 1.3-.7 2.5-1.8 3.3l.5 2-2.2-1.1c-.6.1-1.2.2-1.9.2-3 0-5.5-1.9-5.5-4.5s2.5-4.4 5.4-4.4Z" />
              <circle cx="7.2" cy="10.5" r=".8" fill="currentColor" stroke="none" />
              <circle cx="11.2" cy="10.5" r=".8" fill="currentColor" stroke="none" />
              <circle cx="13.8" cy="14.6" r=".8" fill="currentColor" stroke="none" />
              <circle cx="17.2" cy="14.6" r=".8" fill="currentColor" stroke="none" />
            </svg>
          </button>
          <a class="top-icon-link feedback-link" href="__FEEDBACK_URL__" target="_blank" rel="noreferrer" aria-label="意见反馈" title="意见反馈">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M12 3.75 4.75 8v8L12 20.25 19.25 16V8L12 3.75Z" />
              <path d="M12 7.75v5.25" />
              <circle cx="12" cy="15.8" r=".9" fill="currentColor" stroke="none" />
            </svg>
          </a>
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
            <div id="hero-metric-balance">
              <div class="hero-metric-label">当前积分余额</div>
              <div class="hero-metric-value" id="hero-balance">0</div>
              <div class="hero-metric-subtitle" id="hero-balance-policy">消费时优先扣减月包积分；充值包积分永久有效。</div>
            </div>
            <div id="hero-metric-verify" style="display:none;">
              <div class="hero-metric-label" style="color:var(--accent-2);font-size:1.05rem;">📧 完成邮箱验证</div>
              <div class="hero-metric-subtitle" style="margin:8px 0 14px;">验证通过后解锁全部功能，新用户自动到账 <strong>500 积分</strong>。</div>
              <div class="action-stack">
                <div class="inline-form">
                  <button type="button" id="hero-send-code-btn">发送邮箱验证码</button>
                  <span class="helper-text" id="hero-send-msg"></span>
                </div>
                <div class="inline-form">
                  <input id="hero-code-input" class="text-input" type="text" inputmode="numeric" maxlength="8" placeholder="输入邮箱验证码" />
                  <button type="button" id="hero-confirm-btn">确认验证</button>
                </div>
                <div class="helper-text" id="hero-confirm-msg"></div>
              </div>
            </div>
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
              <div class="helper-text">新用户绑定邀请码，新老用户均额外赠送500积分</div>
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
            <div class="card-note" id="notifications-panel-note">统一查看充值到账、邀请奖励、余额提醒和套餐状态，已读状态会随账号保存在数据库。</div>
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
      <div class="card-note">这里只展示实际扣费记录，并把扣减顺序、扣减来源和常见计费规则翻成用户容易理解的中文。</div>
      <div class="ledger-policy-grid" id="billing-policy-grid"></div>
      <div class="table-toolbar">
        <div><strong>实际扣费账本</strong>，每条记录都会展示消费项目、扣减来源和原因说明，方便你快速判断为什么会扣费。</div>
        <div id="ledger-meta">加载中…</div>
      </div>
      <div class="table-wrap">
      <table>
        <thead><tr><th>时间</th><th>消费项目</th><th>本次扣减</th><th>扣减来源</th><th>扣后余额</th><th>说明</th></tr></thead>
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

<div class="contact-modal" id="wechat-contact-modal" hidden>
  <div class="contact-modal-card" role="dialog" aria-modal="true" aria-labelledby="wechat-contact-title">
    <div class="contact-modal-top">
      <div>
        <div class="contact-modal-title" id="wechat-contact-title">企微联系</div>
        <div class="contact-modal-note">扫码即可添加企业微信。</div>
      </div>
      <button type="button" class="contact-modal-close" id="wechat-contact-close" aria-label="关闭">×</button>
    </div>
    <div id="wechat-contact-body">__WECHAT_QR_HTML__</div>
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
  const portalLogoutButton = document.getElementById("portal-logout-button");
  const wechatContactTrigger = document.getElementById("wechat-contact-trigger");
  const wechatContactModal = document.getElementById("wechat-contact-modal");
  const wechatContactClose = document.getElementById("wechat-contact-close");
  const contactMailLink = document.querySelector(".mail-link");
  const contactFeedbackLink = document.querySelector(".feedback-link");
  const wechatContactBody = document.getElementById("wechat-contact-body");
  const topupViewButtons = document.querySelectorAll("[data-topup-view]");
  const notificationsBody = document.getElementById("notifications-body");
  const notificationState = { category: "system", items: [] };
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
      updateNotificationReadStateForCategory(notificationState.category, true).then(function() {
        renderNotifications(currentAccountData || {});
      }).catch(function(error) {
        showError("更新通知状态失败：" + error.message);
      });
    });
  }

  if (markNotificationsUnreadButton) {
    markNotificationsUnreadButton.addEventListener("click", function() {
      updateNotificationReadStateForCategory(notificationState.category, false).then(function() {
        renderNotifications(currentAccountData || {});
      }).catch(function(error) {
        showError("更新通知状态失败：" + error.message);
      });
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
      var currentNotification = findNotificationById(notificationId);
      updateNotificationReadState([notificationId], !currentNotification || !currentNotification.read_at).then(function() {
        renderNotifications(currentAccountData || {});
      }).catch(function(error) {
        showError("更新通知状态失败：" + error.message);
      });
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
        bindInviteCodeMessage.textContent = "邀请码绑定成功，额外 500 积分已到账。完成邮箱验证后，邀请人也会获得奖励。";
        renderAccount(data);
      }).catch(function(error) {
        bindInviteCodeMessage.textContent = "绑定失败：" + error.message;
      });
    });
  }

  if (portalLogoutButton) {
    portalLogoutButton.addEventListener("click", function() {
      signOutOpenWebUI();
    });
  }

  function renderWechatQr(contact) {
    if (!wechatContactBody) return;
    wechatContactBody.innerHTML = "";
    var qr = contact && contact.wechat_qr_base64 ? String(contact.wechat_qr_base64) : "";
    if (!qr) {
      var note = document.createElement("div");
      note.className = "contact-modal-note";
      note.textContent = "当前未找到企微二维码图片，请联系管理员上传。";
      wechatContactBody.appendChild(note);
      return;
    }
    var wrap = document.createElement("div");
    wrap.className = "wechat-qr-wrap";
    var img = document.createElement("img");
    img.className = "wechat-qr-image";
    img.alt = "企微二维码";
    img.src = qr;
    wrap.appendChild(img);
    wechatContactBody.appendChild(wrap);
  }

  function applyContactConfig(contact) {
    if (!contact) return;
    if (contactMailLink) {
      contactMailLink.href = contact.contact_email ? ("mailto:" + String(contact.contact_email)) : "#";
    }
    if (contactFeedbackLink && contact.feedback_url) {
      contactFeedbackLink.href = String(contact.feedback_url);
    }
    renderWechatQr(contact);
  }

  async function refreshContactConfig() {
    try {
      var response = await fetch(withPortalToken("/portal/api/public/site-contact-config"), {
        cache: "no-store",
        credentials: "same-origin"
      });
      if (!response.ok) return null;
      var payload = await response.json();
      var contact = payload && payload.data ? payload.data.contact : null;
      applyContactConfig(contact);
      return contact;
    } catch (error) {
      return null;
    }
  }

  function openWechatModal() {
    if (!wechatContactModal) return;
    wechatContactModal.hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeWechatModal() {
    if (!wechatContactModal) return;
    wechatContactModal.hidden = true;
    document.body.style.overflow = "";
  }

  if (wechatContactTrigger) {
    wechatContactTrigger.addEventListener("click", async function() {
      await refreshContactConfig();
      openWechatModal();
    });
  }

  if (contactMailLink) {
    contactMailLink.addEventListener("click", async function(event) {
      event.preventDefault();
      var contact = await refreshContactConfig();
      var target = contact && contact.contact_email ? ("mailto:" + String(contact.contact_email)) : (contactMailLink.getAttribute("href") || "#");
      window.location.href = target;
    });
  }

  if (contactFeedbackLink) {
    contactFeedbackLink.addEventListener("click", async function(event) {
      event.preventDefault();
      var contact = await refreshContactConfig();
      var target = contact && contact.feedback_url ? String(contact.feedback_url) : (contactFeedbackLink.getAttribute("href") || "");
      if (target) {
        window.open(target, "_blank", "noopener,noreferrer");
      }
    });
  }

  if (wechatContactClose) {
    wechatContactClose.addEventListener("click", closeWechatModal);
  }

  if (wechatContactModal) {
    wechatContactModal.addEventListener("click", function(event) {
      if (event.target === wechatContactModal) {
        closeWechatModal();
      }
    });
  }

  document.addEventListener("keydown", function(event) {
    if (event.key === "Escape" && wechatContactModal && !wechatContactModal.hidden) {
      closeWechatModal();
    }
  });

  refreshContactConfig();

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

    // ── Hero metric: show verification form or balance ──
    var heroBalance = document.getElementById("hero-metric-balance");
    var heroVerify = document.getElementById("hero-metric-verify");
    if (heroBalance && heroVerify) {
      if (enforced && !verified) {
        heroBalance.style.display = "none";
        heroVerify.style.display = "";
        // Wire up hero verification buttons (idempotent)
        var heroSendBtn = document.getElementById("hero-send-code-btn");
        var heroConfirmBtn = document.getElementById("hero-confirm-btn");
        var heroCodeInput = document.getElementById("hero-code-input");
        var heroSendMsg = document.getElementById("hero-send-msg");
        var heroConfirmMsg = document.getElementById("hero-confirm-msg");
        if (heroSendBtn && !heroSendBtn._wired) {
          heroSendBtn._wired = true;
          heroSendBtn.addEventListener("click", function() {
            heroSendMsg.textContent = "发送中…";
            apiPost("/portal/api/account/email-verification/request").then(function(data) {
              heroSendMsg.textContent = "验证码已发送到 " + (data.email || "当前邮箱") + "，请查收邮箱。";
              if (verificationRequestMessage) verificationRequestMessage.textContent = heroSendMsg.textContent;
            }).catch(function(err) {
              heroSendMsg.textContent = "发送失败：" + err.message;
            });
          });
        }
        if (heroConfirmBtn && !heroConfirmBtn._wired) {
          heroConfirmBtn._wired = true;
          heroConfirmBtn.addEventListener("click", function() {
            var code = (heroCodeInput && heroCodeInput.value || "").trim();
            if (!code) { heroConfirmMsg.textContent = "请先输入邮箱验证码。"; return; }
            heroConfirmMsg.textContent = "验证中…";
            apiPost("/portal/api/account/email-verification/confirm", { code: code }).then(function(data) {
              if (heroCodeInput) heroCodeInput.value = "";
              heroConfirmMsg.textContent = "邮箱验证成功！注册已完成，新用户奖励已自动结算。";
              renderAccount(data);
            }).catch(function(err) {
              heroConfirmMsg.textContent = "验证失败：" + err.message;
            });
          });
        }
      } else {
        heroBalance.style.display = "";
        heroVerify.style.display = "none";
      }
    }

    var banner = document.getElementById("verification-gate-banner");
    if (!banner) {
      return;
    }
    if (enforced && !verified) {
      banner.style.display = "block";
      banner.innerHTML = [
        '<div>当前已开启首次登录邮箱验证门槛。完成邮箱验证前，你只能停留在账户信息页并使用验证码验证入口，充值、消费、通知和套餐能力会被暂时锁定。</div>',
        '<div class="gate-banner-actions">',
        '<button type="button" class="top-secondary-link" id="verification-gate-logout-button">退出当前登录</button>',
        '</div>'
      ].join('');
      var gateLogoutButton = document.getElementById("verification-gate-logout-button");
      if (gateLogoutButton) {
        gateLogoutButton.addEventListener("click", function() {
          signOutOpenWebUI();
        });
      }
      setActivePage("account", false);
      return;
    }
    banner.style.display = "none";
    banner.innerHTML = "";
  }

  function clearOpenWebUICookies() {
    ["token", "oui-session", "oauth_id_token"].forEach(function(name) {
      document.cookie = name + '=; Max-Age=0; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Lax';
    });
  }

  function signOutOpenWebUI() {
    var signoutUrl = "/api/v1/auths/signout";
    fetch(signoutUrl, {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store"
    }).catch(function() {
      return null;
    }).finally(function() {
      clearOpenWebUICookies();
      try { localStorage.removeItem('token'); } catch(e) {}
      window.location.href = "/";
    });
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

  function syncNotificationItems(items) {
    notificationState.items = Array.isArray(items) ? items.slice() : [];
    if (currentAccountData) {
      currentAccountData.notifications = notificationState.items.slice();
    }
  }

  function findNotificationById(notificationId) {
    var normalizedId = String(notificationId || "");
    for (var i = 0; i < notificationState.items.length; i += 1) {
      var item = notificationState.items[i] || {};
      if (String(item.notification_id || item.id || "") === normalizedId) {
        return item;
      }
    }
    return null;
  }

  function updateNotificationReadState(notificationIds, read) {
    return apiPost("/portal/api/notifications/read-state", {
      notification_ids: notificationIds,
      read: !!read,
    }).then(function(data) {
      syncNotificationItems(data.notifications || []);
      return data;
    });
  }

  function updateNotificationReadStateForCategory(category, read) {
    return apiPost("/portal/api/notifications/read-state", {
      category: category === "user" ? "user" : "system",
      read: !!read,
    }).then(function(data) {
      syncNotificationItems(data.notifications || []);
      return data;
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
    syncNotificationItems(data.notifications || []);
    var pa = data.points_account || {};
    var balanceBreakdown = data.balance_breakdown || {};
    var policyText = balanceBreakdown.consumption_policy_text || "消费时优先扣减月包积分；充值包积分永久有效。";
    var subs = data.subscriptions || [];
    var activeSubscription = findActiveSubscription(subs);
    var planTier = activeSubscription ? normalizePlanLabel(data.plan_tier || user.plan_tier || activeSubscription.package_code || "已开通") : "无套餐";
    var accountStatusText = emailVerified
      ? (user.email || user.user_id || "当前用户") + " 已完成邮箱验证"
      : (user.email || user.user_id || "当前用户") + " 待完成邮箱验证";

    document.getElementById("user-info").textContent =
      (user.display_name || user.user_id || "用户") + "  ·  " + (user.email || "");
    document.getElementById("hero-balance").textContent = intVal(pa.balance_points);
    document.getElementById("hero-balance-policy").textContent = policyText;

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
        : (emailVerified
          ? "当前账号已完成邮箱验证，不能再绑定邀请人。"
          : "暂未绑定邀请人；绑定邀请码后可额外获得 500 积分。");
    }
    if (bindInviteCodeMessage) {
      bindInviteCodeMessage.textContent = invitedBy
        ? "当前账号已绑定邀请关系；你已获得绑定奖励，完成邮箱验证后邀请人奖励会继续自动处理。"
        : (emailVerified
          ? "当前账号已完成邮箱验证，邀请码绑定入口已关闭。"
          : "如果你是被邀请来的，请先绑定邀请码，可额外获得 500 积分；完成邮箱验证后邀请人也会得到奖励。");
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
      planRows.push(infoRow("消费顺序", esc(policyText)));
    }
    document.getElementById("plan-info").innerHTML = planRows.join("");

    // Pricing pills
    var costMap = data.point_cost_by_event || {};
    var displayMap = data.event_pricing_display || {};
    document.getElementById("pricing-row").innerHTML = Object.keys(costMap).map(function(et) {
      var label = displayMap[et] || et;
      return '<div class="pricing-pill"><span class="name">' + esc(label) + '</span><span class="cost">' + costMap[et] + ' 积分/次</span></div>';
    }).join("");

    renderBillingPolicy(balanceBreakdown, costMap, displayMap);

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
    syncNotificationItems((data && data.notifications) || notificationState.items || []);
    var groups = { user: [], system: [] };
    (notificationState.items || []).forEach(function(item) {
      var category = item.category === "user" ? "user" : "system";
      groups[category].push({
        id: String(item.notification_id || item.id || ""),
        tag: item.tag || "通知",
        level: item.level || "info",
        title: item.title || "新通知",
        desc: item.body || item.desc || "",
        time: item.occurred_at || item.created_at || item.updated_at || "-",
        unread: !item.read_at,
      });
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
        ? "用于查看与你账户直接相关的邀请奖励、余额提醒等消息，已读状态会随账号保存在数据库。"
        : "用于查看充值到账、套餐状态等平台通知，已读状态会随账号保存在数据库。";
    }
  }

  function renderNotifications(data) {
    var groups = buildNotificationGroups(data);
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
    }).join("") : '<div class="notification-card"><div class="notification-title">暂无通知</div><div class="notification-desc">当前没有需要提醒的账户消息。</div></div>';
  }

  function localizeLedgerDescription(row) {
    var description = String((row && row.description) || "").trim();
    var entryType = String((row && row.entry_type) || "").trim().toLowerCase();
    var eventType = String((row && row.event_type) || "").trim().toLowerCase();
    var mapping = {
      "inviter reward points": "邀请新用户注册成功奖励积分",
      "signup gift points": "新用户注册赠送积分",
      "promotion reward": "活动赠送积分",
      "MiniMax agent request": "按 LLM 请求次数计费。",
      "MiniMax agent request failed": "LLM 请求失败，系统已自动退款。",
      "Dify workflow run": "一次 Workflow 固定计费 8 积分，内部步骤只保留审计记录，不重复收费。",
      "Dify workflow request failed": "Workflow 请求失败，系统已自动退款。",
      "expired subscription points removed": "当前订阅周期结束后，未使用完的月包积分会自动清零。"
    };
    if (mapping[description]) {
      return mapping[description];
    }
    if (description) {
      return description;
    }
    if (entryType === "consume") {
      if (eventType === "workflow_run") {
        return "一次 Workflow 固定计费 8 积分，内部检索和调用只保留审计记录，不重复收费。";
      }
      if (eventType === "llm_request") {
        return "按 LLM 请求次数计费。";
      }
      if (eventType === "kb_retrieve" || eventType === "dify_knowledge_retrieve") {
        return "按知识库检索次数计费。";
      }
      if (eventType === "product_api_call") {
        return "按商品 API 检索次数计费。";
      }
      if (eventType === "web_search") {
        return "按网络搜索次数计费。";
      }
    }
    if (eventType === "referral_invited_reward") {
      return "绑定邀请码额外奖励积分";
    }
    if (eventType === "referral_inviter_reward") {
      return "邀请新用户注册成功奖励积分";
    }
    if (eventType === "signup_gift") {
      return "新用户注册赠送积分";
    }
    if (entryType === "subscription_expire") {
      return "当前订阅周期结束后，未使用完的月包积分会自动清零。";
    }
    if (entryType === "daily_quota_reset") {
      return "游客账户会按每日额度上限自动重置余额。";
    }
    return "";
  }

  function localizeLedgerEntryType(entryType, eventType) {
    var mapping = {
      consume: "消费",
      refund: "退款",
      grant: "赠送",
      recharge: "充值到账",
      signup_gift: "注册赠送",
      admin_grant: "后台加积分",
      subscription_grant: "订阅发放",
      promotion_reward: "活动奖励",
      subscription_expire: "套餐到期清零",
      daily_quota_reset: "每日额度重置"
    };
    var normalized = String(entryType || "").trim().toLowerCase();
    if (mapping[normalized]) {
      return mapping[normalized];
    }
    return localizeLedgerEventType(eventType);
  }

  function localizeLedgerEventType(eventType) {
    var normalized = String(eventType || "").trim().toLowerCase();
    var displayMap = (currentAccountData && currentAccountData.event_pricing_display) || {};
    if (displayMap[normalized]) {
      return displayMap[normalized];
    }
    var mapping = {
      llm_request: "LLM 请求",
      workflow_run: "Workflow 请求",
      kb_retrieve: "知识库检索",
      dify_knowledge_retrieve: "知识库检索",
      product_api_call: "商品 API 检索",
      web_search: "网络搜索",
      recharge: "充值到账",
      signup_gift: "新用户注册赠送",
      referral_invited_reward: "绑定邀请码奖励",
      referral_inviter_reward: "邀请新用户注册奖励",
      subscription_grant: "订阅积分发放",
      subscription_expire: "套餐到期清零",
      daily_quota_reset: "每日额度重置",
      admin_grant: "后台加积分",
      promotion_reward: "活动奖励"
    };
    return mapping[normalized] || String(eventType || "");
  }

  function getLedgerEventPointCost(eventType) {
    var costMap = (currentAccountData && currentAccountData.point_cost_by_event) || {};
    return intVal(costMap[String(eventType || "").trim().toLowerCase()]);
  }

  function localizeLedgerSource(source) {
    var mapping = {
      subscription: "月包积分",
      recharge: "充值包积分",
      other: "其他赠送积分"
    };
    var normalized = String(source || "").trim().toLowerCase();
    return mapping[normalized] || "其他赠送积分";
  }

  function summarizeLedgerSources(row) {
    if (Array.isArray(row && row.source_summary) && row.source_summary.length) {
      return row.source_summary.map(function(item) {
        return {
          source: String(item.source || "other").trim().toLowerCase() || "other",
          label: item.label || localizeLedgerSource(item.source),
          points: intVal(item.points)
        };
      }).filter(function(item) {
        return item.points > 0;
      });
    }
    var meta = (row && row.meta_json) || {};
    var allocations = Array.isArray(meta.balance_source_allocations) ? meta.balance_source_allocations : [];
    var totals = {};
    allocations.forEach(function(item) {
      var source = String((item && item.source) || "other").trim().toLowerCase() || "other";
      var points = intVal(item && item.points);
      if (points <= 0) {
        return;
      }
      totals[source] = (totals[source] || 0) + points;
    });
    if (!Object.keys(totals).length && String((row && row.entry_type) || "").trim().toLowerCase() === "subscription_expire") {
      totals.subscription = Math.abs(intVal(row && row.points_delta));
    }
    return ["subscription", "recharge", "other"].filter(function(source) {
      return intVal(totals[source]) > 0;
    }).map(function(source) {
      return {
        source: source,
        label: localizeLedgerSource(source),
        points: intVal(totals[source])
      };
    });
  }

  function renderLedgerSourceChip(item) {
    var source = String((item && item.source) || "other").trim().toLowerCase() || "other";
    var label = item && item.label ? String(item.label) : localizeLedgerSource(source);
    return '<span class="source-chip ' + esc(source) + '">' + esc(label) + ' ' + intVal(item && item.points) + '</span>';
  }

  function renderLedgerItemCell(row) {
    var entryType = String((row && row.entry_type) || "").trim().toLowerCase();
    var title = entryType === "consume"
      ? (localizeLedgerEventType(row.event_type) || localizeLedgerEntryType(row.entry_type, row.event_type) || "消费")
      : localizeLedgerEntryType(row.entry_type, row.event_type);
    var points = Math.abs(intVal(row && row.points_delta));
    var units = intVal(row && row.units);
    var unitCost = getLedgerEventPointCost(row && row.event_type);
    var detailParts = [];
    if (entryType === "consume") {
      if (units > 0) {
        detailParts.push(units + " 次");
      }
      if (unitCost > 0) {
        detailParts.push(unitCost + " 积分/次");
      }
      detailParts.push("合计 " + points + " 积分");
    } else if (entryType === "subscription_expire") {
      detailParts.push("到期清零 " + points + " 积分");
    } else if (points > 0) {
      detailParts.push("本次变动 " + points + " 积分");
    }
    return '<div class="table-main-text">' + esc(title) + '</div>' +
      (detailParts.length ? '<div class="table-sub-text">' + esc(detailParts.join(' · ')) + '</div>' : '');
  }

  function renderLedgerSourceCell(row) {
    var sources = summarizeLedgerSources(row);
    if (!sources.length) {
      return '<div class="table-sub-text">按系统默认顺序扣减</div>';
    }
    return '<div class="source-chip-row">' + sources.map(renderLedgerSourceChip).join("") + '</div>';
  }

  function renderLedgerDescriptionCell(row) {
    var description = localizeLedgerDescription(row);
    var sourceSummaryText = String((row && row.source_summary_text) || "").trim();
    var extraLines = [];
    if (sourceSummaryText) {
      extraLines.push('实际扣减：' + sourceSummaryText);
    }
    return '<div class="table-main-text">' + esc(description || "-") + '</div>' +
      extraLines.map(function(line) {
        return '<div class="table-sub-text">' + esc(line) + '</div>';
      }).join('');
  }

  function formatConsumptionPriority(priority) {
    var labels = (Array.isArray(priority) ? priority : ["subscription", "recharge", "other"]).map(localizeLedgerSource);
    return labels.join(" -> ");
  }

  function renderBillingPolicy(balanceBreakdown, costMap, displayMap) {
    var container = document.getElementById("billing-policy-grid");
    if (!container) {
      return;
    }
    var priorityText = formatConsumptionPriority(balanceBreakdown.consumption_priority || ["subscription", "recharge", "other"]);
    var policyText = balanceBreakdown.consumption_policy_text || "系统会优先扣减月包积分；月包不足时再扣充值包积分。";
    var examples = ["workflow_run", "llm_request", "kb_retrieve", "product_api_call", "web_search"].filter(function(eventType) {
      return intVal(costMap[eventType]) > 0;
    }).map(function(eventType) {
      return (displayMap[eventType] || localizeLedgerEventType(eventType) || eventType) + '：' + intVal(costMap[eventType]) + ' 积分/次';
    });
    container.innerHTML = '' +
      '<div class="ledger-policy-card"><div class="table-main-text">扣减顺序</div><div class="table-sub-text">' + esc(priorityText) + '</div><div class="table-sub-text">' + esc(policyText) + '</div></div>' +
      '<div class="ledger-policy-card"><div class="table-main-text">有效期规则</div><div class="table-sub-text">月包积分只在当前订阅周期内有效，到期后自动清零。</div><div class="table-sub-text">充值包积分永久有效，通常在月包不足时才会继续扣减。</div></div>' +
      '<div class="ledger-policy-card"><div class="table-main-text">常见单次扣费</div>' +
        (examples.length
          ? examples.map(function(line) { return '<div class="table-sub-text">' + esc(line) + '</div>'; }).join('')
          : '<div class="table-sub-text">按后台最新计价规则实时结算。</div>') +
      '</div>';
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
    document.getElementById("ledger-meta").textContent = "共 " + total + " 条实际扣费记录，本页 " + rows.length + " 条";

    document.getElementById("ledger-body").innerHTML = rows.length ? rows.map(function(r) {
      var delta = intVal(r.points_delta);
      var cls = delta >= 0 ? "positive" : "negative";
      var sign = delta >= 0 ? "+" : "";
      return '<tr><td>' + fmtTime(r.created_at) + '</td><td>' + renderLedgerItemCell(r) +
        '</td><td class="' + cls + '">' + sign + delta + '</td><td>' + renderLedgerSourceCell(r) +
        '</td><td>' + intVal(r.balance_after_points) + '</td><td>' + renderLedgerDescriptionCell(r) + '</td></tr>';
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
      return '<tr><td>' + fmtTime(r.created_at) + '</td><td>' + esc(localizeLedgerEntryType(r.entry_type, r.event_type)) +
        '</td><td class="positive">+' + delta + '</td><td>' + intVal(r.balance_after_points) +
        '</td><td>' + esc(localizeLedgerDescription(r)) + '</td></tr>';
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
<script>
 window.difyChatbotConfig = {
  token: 'QmSaZ6H42s0ZdaxM',
  baseUrl: 'http://localhost',
  inputs: {},
  systemVariables: {},
  userVariables: {},
 }
</script>
<script
 src="http://localhost/embed.min.js"
 id="QmSaZ6H42s0ZdaxM"
 defer>
</script>
</body>
</html>""".replace("__OPENWEBUI_HOME_URL__", openwebui_home_url).replace("__WECHAT_QR_HTML__", wechat_qr_html).replace("__CONTACT_EMAIL__", contact_email).replace("__FEEDBACK_URL__", feedback_url)
