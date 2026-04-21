from __future__ import annotations

import base64
import json
import os
from html import escape
from pathlib import Path
from typing import Any

from data_platform.chat_backend.domains.portal.service import _portal_public_base_url
from data_platform.chat_backend.domains.site_config import _get_contact_config
from data_platform.chat_backend.infra.postgres import _postgres_conn
from data_platform.chat_backend.infra.settings import (
    DEFAULT_BILLING_PACKAGES,
    DEFAULT_PROMOTION_RULES,
)


_BASE_CSS = """
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
    --shadow: 0 18px 48px rgba(30, 42, 47, 0.12);
    --sidebar-w: 228px;
    --content-w: 1220px;
  }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
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
  .brand {
    padding: 4px 18px 16px;
    font-size: 1.12rem;
    font-weight: 700;
    color: var(--ink);
    border-bottom: 1px solid var(--line);
    margin-bottom: 12px;
  }
  .brand-subtitle {
    display: block;
    margin-top: 6px;
    color: var(--muted);
    font-size: 0.78rem;
    font-weight: 500;
  }
  .nav-group {
    padding: 10px 10px 6px;
  }
  .nav-group-title {
    padding: 6px 10px;
    font-size: 0.76rem;
    font-weight: 600;
    color: var(--muted);
    letter-spacing: 0.04em;
  }
  .nav-item {
    display: block;
    padding: 10px 12px 10px 18px;
    font-size: 0.88rem;
    color: var(--ink);
    text-decoration: none;
    border-left: 3px solid transparent;
    border-radius: 10px;
    transition: background 0.15s, border-color 0.15s, color 0.15s;
  }
  .nav-item:hover,
  .nav-item.active {
    background: var(--accent-soft);
    border-left-color: var(--accent);
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
  .page-kicker {
    font-size: 0.78rem;
    color: var(--muted);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-bottom: 6px;
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
  .topbar-actions {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }
  .top-utility-actions {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .top-route-nav {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    justify-content: flex-end;
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
  }
  .top-route-link:hover,
  .top-route-link.active {
    background: var(--accent-soft);
    color: var(--accent);
    border-color: rgba(17, 75, 95, 0.18);
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
  }
  .top-home-link:hover {
    background: #0f3f50;
    border-color: #0f3f50;
  }
  .top-action-link {
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
    cursor: pointer;
    padding: 0;
  }
  .top-action-link:hover {
    background: var(--accent-soft);
    border-color: rgba(17, 75, 95, 0.18);
    color: var(--accent);
  }
  .top-action-link svg {
    width: 19px;
    height: 19px;
  }
  #dify-chatbot-bubble-button {
    background-color: #1C64F2 !important;
  }
  #dify-chatbot-bubble-window {
    position: fixed !important;
    right: var(--dify-chatbot-bubble-button-right, 1rem) !important;
    bottom: var(--dify-chatbot-bubble-button-bottom, 1rem) !important;
    left: auto !important;
    top: auto !important;
    width: 24rem !important;
    height: 40rem !important;
    max-width: calc(100vw - 24px) !important;
    max-height: calc(100vh - 24px) !important;
    z-index: 2147483646 !important;
    box-shadow: 0 24px 60px rgba(8, 10, 18, 0.28) !important;
    background: #ffffff !important;
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
  .section-block {
    scroll-margin-top: 110px;
  }
  .card {
    background: var(--paper);
    border-radius: 18px;
    border: 1px solid var(--line);
    box-shadow: var(--shadow);
    padding: 22px 24px;
  }
  .card h2 {
    font-size: 1.04rem;
    margin: 0 0 16px;
    color: var(--ink);
    border-bottom: 1px solid var(--line);
    padding-bottom: 12px;
  }
  .card-note {
    color: var(--muted);
    font-size: 0.86rem;
    margin: -6px 0 14px;
    line-height: 1.7;
  }
  .tip-banner {
    border-radius: 16px;
    border: 1px solid rgba(217, 119, 6, 0.2);
    background: linear-gradient(135deg, rgba(217, 119, 6, 0.12), rgba(255, 251, 245, 0.94));
    padding: 16px 18px;
    font-size: 0.9rem;
    line-height: 1.7;
  }
  .offer-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 18px;
  }
  .offer-card {
    border-radius: 20px;
    border: 1px solid var(--line);
    background: linear-gradient(180deg, rgba(255, 251, 245, 0.98), rgba(244, 236, 223, 0.9));
    padding: 20px;
    display: grid;
    gap: 14px;
  }
  .offer-actions,
  .checkout-actions,
  .payment-method-row {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }
  .offer-actions {
    margin-top: 2px;
  }
  .offer-cta,
  .ghost-button,
  .payment-method {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 42px;
    padding: 0 16px;
    border-radius: 12px;
    text-decoration: none;
    font-size: 0.84rem;
    font-weight: 600;
    transition: background 0.15s, color 0.15s, border-color 0.15s;
  }
  .offer-cta,
  .payment-method.active {
    background: var(--accent);
    color: #fff;
    border: 1px solid var(--accent);
  }
  .offer-cta:hover,
  .payment-method.active:hover {
    background: #0f3f50;
    border-color: #0f3f50;
  }
  .ghost-button,
  .payment-method {
    background: rgba(255, 251, 245, 0.78);
    color: var(--ink);
    border: 1px solid var(--line);
  }
  .ghost-button:hover,
  .payment-method:hover {
    background: var(--accent-soft);
    border-color: rgba(17, 75, 95, 0.18);
    color: var(--accent);
  }
  .form-grid {
    display: grid;
    gap: 18px;
  }
  .field-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 14px;
  }
  .field-group {
    display: grid;
    gap: 8px;
  }
  .field-label {
    font-size: 0.84rem;
    font-weight: 600;
    color: var(--ink);
  }
  .field-hint {
    color: var(--muted);
    font-size: 0.78rem;
    line-height: 1.6;
  }
  .text-field {
    width: 100%;
    min-height: 44px;
    border-radius: 12px;
    border: 1px solid var(--line);
    background: #fff;
    padding: 0 14px;
    color: var(--ink);
    font: inherit;
  }
  .text-field:focus {
    outline: none;
    border-color: rgba(17, 75, 95, 0.34);
    box-shadow: 0 0 0 4px rgba(17, 75, 95, 0.08);
  }
  .status-banner {
    display: none;
    border-radius: 14px;
    padding: 12px 14px;
    font-size: 0.84rem;
    line-height: 1.65;
  }
  .status-banner[data-state="info"] {
    display: block;
    background: rgba(17, 75, 95, 0.08);
    border: 1px solid rgba(17, 75, 95, 0.14);
    color: var(--accent);
  }
  .status-banner[data-state="success"] {
    display: block;
    background: rgba(22, 163, 74, 0.1);
    border: 1px solid rgba(22, 163, 74, 0.16);
    color: #166534;
  }
  .status-banner[data-state="error"] {
    display: block;
    background: rgba(220, 38, 38, 0.08);
    border: 1px solid rgba(220, 38, 38, 0.14);
    color: #b91c1c;
  }
  .support-inline-link {
    color: var(--accent);
    text-decoration: none;
    font-weight: 600;
  }
  .support-inline-link:hover {
    color: #0f3f50;
  }
  .cta-hint {
    color: var(--muted);
    font-size: 0.8rem;
  }
  .offer-card.featured {
    border-color: rgba(217, 119, 6, 0.26);
    box-shadow: 0 20px 42px rgba(217, 119, 6, 0.08);
  }
  .offer-top {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: 12px;
  }
  .offer-name {
    font-size: 1.2rem;
    font-weight: 700;
    line-height: 1.18;
  }
  .offer-tagline {
    color: var(--muted);
    font-size: 0.84rem;
    margin-top: 6px;
  }
  .offer-badge {
    padding: 6px 10px;
    border-radius: 999px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 0.74rem;
    font-weight: 700;
    white-space: nowrap;
  }
  .offer-price {
    display: flex;
    align-items: flex-end;
    gap: 10px;
    flex-wrap: wrap;
  }
  .offer-price-main {
    font-size: 2.08rem;
    font-weight: 700;
    letter-spacing: -0.03em;
  }
  .offer-points {
    color: var(--muted);
    font-size: 0.86rem;
  }
  .bullet-list,
  .guide-list,
  .timeline-list,
  .roadmap-grid,
  .mini-kpi-row {
    display: grid;
    gap: 12px;
  }
  .bullet-item,
  .guide-item,
  .timeline-item,
  .mini-kpi,
  .roadmap-card {
    border: 1px solid var(--line);
    border-radius: 14px;
    background: rgba(255, 251, 245, 0.84);
    padding: 14px 16px;
  }
  .bullet-item {
    display: flex;
    gap: 8px;
    align-items: start;
    font-size: 0.86rem;
    line-height: 1.6;
  }
  .bullet-item::before {
    content: "•";
    color: var(--accent-2);
    font-weight: 700;
  }
  .guide-title,
  .timeline-title {
    font-size: 0.9rem;
    font-weight: 700;
    margin-bottom: 6px;
  }
  .guide-grid,
  .example-grid,
  .demo-grid,
  .notice-grid {
    display: grid;
    gap: 14px;
  }
  .guide-grid,
  .example-grid,
  .demo-grid,
  .notice-grid {
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  }
  .example-card,
  .demo-card,
  .notice-card {
    border: 1px solid var(--line);
    border-radius: 16px;
    background: rgba(255, 251, 245, 0.88);
    padding: 16px 18px;
  }
  .example-card {
    display: grid;
    gap: 12px;
  }
  .example-card.highlight {
    background: linear-gradient(180deg, rgba(17, 75, 95, 0.08), rgba(255, 251, 245, 0.92));
  }
  .example-kicker {
    color: var(--muted);
    font-size: 0.76rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .example-title,
  .notice-title,
  .demo-title {
    font-size: 0.96rem;
    font-weight: 700;
    margin: 0;
  }
  .example-desc,
  .notice-desc,
  .demo-desc,
  .demo-caption {
    color: var(--muted);
    font-size: 0.84rem;
    line-height: 1.7;
    margin: 0;
  }
  .command-block {
    border-radius: 14px;
    background: #182126;
    color: #f8fafc;
    padding: 14px 16px;
    font-family: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
    font-size: 0.8rem;
    line-height: 1.7;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .example-meta {
    display: grid;
    gap: 6px;
  }
  .example-meta-item {
    color: var(--muted);
    font-size: 0.8rem;
    line-height: 1.6;
  }
  .notice-card.accent {
    background: linear-gradient(180deg, rgba(217, 119, 6, 0.12), rgba(255, 251, 245, 0.94));
  }
  .notice-card.service {
    background: linear-gradient(180deg, rgba(15, 118, 110, 0.12), rgba(255, 251, 245, 0.94));
  }
  .demo-media {
    border: 1px dashed rgba(17, 75, 95, 0.28);
    border-radius: 16px;
    min-height: 220px;
    background:
      linear-gradient(135deg, rgba(17, 75, 95, 0.08), rgba(255, 251, 245, 0.92)),
      repeating-linear-gradient(135deg, rgba(17, 75, 95, 0.06) 0, rgba(17, 75, 95, 0.06) 12px, transparent 12px, transparent 24px);
    display: grid;
    place-items: center;
    padding: 18px;
    text-align: center;
  }
  .demo-placeholder-title {
    font-size: 1rem;
    font-weight: 700;
    margin-bottom: 8px;
  }
  .demo-placeholder-note {
    color: var(--muted);
    font-size: 0.82rem;
    line-height: 1.7;
    max-width: 280px;
    margin: 0 auto;
  }
  .guide-desc,
  .timeline-desc,
  .roadmap-card p {
    color: var(--muted);
    font-size: 0.84rem;
    line-height: 1.7;
    margin: 0;
  }
  .status-pill {
    display: inline-flex;
    align-items: center;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 0.74rem;
    font-weight: 700;
  }
  .status-pill.done {
    background: rgba(17, 75, 95, 0.12);
    color: var(--accent);
  }
  .status-pill.pending {
    background: rgba(217, 119, 6, 0.12);
    color: #9a6700;
  }
  .status-pill.success {
    background: rgba(15, 118, 110, 0.12);
    color: #0f766e;
  }
  .mini-kpi-row {
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  }
  .mini-kpi-value {
    font-size: 1.2rem;
    font-weight: 700;
    margin-bottom: 4px;
  }
  .mini-kpi-label {
    color: var(--muted);
    font-size: 0.78rem;
  }
  .roadmap-grid {
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  }
  .roadmap-card h3 {
    margin: 0 0 8px;
    font-size: 1rem;
  }
  .checkout-summary {
    display: grid;
    gap: 16px;
  }
  .checkout-package-name {
    font-size: 1.22rem;
    font-weight: 700;
    line-height: 1.2;
  }
  .checkout-package-subtitle,
  .checkout-muted,
  .checkout-note {
    color: var(--muted);
    font-size: 0.86rem;
    line-height: 1.7;
  }
  .checkout-price-row,
  .status-grid {
    display: grid;
    gap: 12px;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  }
  .checkout-price-card,
  .status-card {
    border: 1px solid var(--line);
    border-radius: 16px;
    background: rgba(255, 251, 245, 0.86);
    padding: 14px 16px;
  }
  .checkout-price-label,
  .status-card-label {
    color: var(--muted);
    font-size: 0.78rem;
    margin-bottom: 6px;
  }
  .checkout-price-value,
  .status-card-value {
    font-size: 1.08rem;
    font-weight: 700;
  }
  .checkout-price-value.emphasis {
    color: var(--accent-2);
  }
  .promo-list {
    display: grid;
    gap: 10px;
  }
  .promo-item {
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 12px 14px;
    background: rgba(255, 251, 245, 0.78);
  }
  .promo-item strong {
    display: block;
    margin-bottom: 4px;
  }
  .order-status-panel {
    display: grid;
    gap: 16px;
  }
  .status-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 32px;
    padding: 0 12px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 700;
  }
  .status-badge.pending {
    background: rgba(217, 119, 6, 0.12);
    color: #9a6700;
  }
  .status-badge.paid {
    background: rgba(15, 118, 110, 0.12);
    color: #0f766e;
  }
  .status-badge.other {
    background: rgba(17, 75, 95, 0.1);
    color: var(--accent);
  }
  @media (max-width: 900px) {
    .workspace-topbar-inner {
      align-items: flex-start;
    }
    .topbar-actions,
    .top-route-nav {
      justify-content: flex-start;
    }
  }
  @media (max-width: 760px) {
    .portal-shell { flex-direction: column; }
    body { overflow: auto; }
    .sidebar {
      width: 100%;
      min-height: auto;
      position: static;
      border-right: none;
      border-bottom: 1px solid var(--line);
    }
    .portal-shell, .workspace, .sidebar { height: auto; }
    .workspace { overflow: visible; }
    .workspace-topbar-inner,
    .main {
      width: calc(100% - 24px);
    }
    .workspace-topbar-inner {
      min-height: 80px;
      padding: 10px 0;
    }
    .page-title-row h1 { font-size: 1.5rem; }
    .main { margin: 16px auto 28px; }
  }
"""

def _portal_chatbot_base_url() -> str:
  return f"{_portal_public_base_url()}/_dify"


def _portal_chatbot_token() -> str:
  return (
    os.environ.get("DIFY_CHATBOT_TOKEN")
    or os.environ.get("DIFY_CHATBOT_SHARE_CODE")
    or "QmSaZ6H42s0ZdaxM"
  ).strip()


def _render_portal_chatbot_snippet() -> str:
  chatbot_base_url = _portal_chatbot_base_url()
  chatbot_token = _portal_chatbot_token()
  chatbot_base_url_json = json.dumps(chatbot_base_url)
  chatbot_embed_src_json = json.dumps(f"{chatbot_base_url}/embed.min.js")
  chatbot_page_src_json = json.dumps(f"{chatbot_base_url}/chatbot/{chatbot_token}")
  chatbot_token_json = json.dumps(chatbot_token)
  return f"""
<script>
 (function() {{
  const config = {{
   token: {chatbot_token_json},
   baseUrl: {chatbot_base_url_json},
    dynamicScript: true,
   inputs: {{}},
   systemVariables: {{}},
   userVariables: {{}},
  }};
  const passportStorageKey = `passport-${{config.token}}`;
  const chatbotPageUrl = {chatbot_page_src_json};
  let hasScheduledWarmup = false;
  const appendHintLink = (rel, href, as) => {{
    if (!href || document.head.querySelector(`link[rel="${{rel}}"][data-dify-href="${{href}}"]`)) {{
    return;
   }}
   const link = document.createElement('link');
   link.rel = rel;
   link.href = href;
   if (as) {{
    link.as = as;
   }}
   link.dataset.difyHref = href;
   document.head.appendChild(link);
  }};
  const scheduleIdleWork = (callback) => {{
   if ('requestIdleCallback' in window) {{
    window.requestIdleCallback(callback, {{ timeout: 2500 }});
    return;
   }}
   window.setTimeout(callback, 1200);
  }};
  const warmupChatbot = () => {{
   if (hasScheduledWarmup) {{
    return;
   }}
   const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
   if (connection && (connection.saveData || /(^|-)2g$/.test(connection.effectiveType || ''))) {{
    return;
   }}
   hasScheduledWarmup = true;
   scheduleIdleWork(async () => {{
    try {{
     appendHintLink('prefetch', chatbotPageUrl, 'document');
     const response = await fetch(chatbotPageUrl, {{
      credentials: 'include',
     }});
     if (!response.ok) {{
      throw new Error(`chatbot warmup failed: ${{response.status}}`);
     }}
     const html = await response.text();
     const assetMatches = Array.from(
      html.matchAll(/(?:src|href)=\"([^\"]*\/_dify\/_next\/static\/[^\"]+)\"/g),
      (match) => match[1],
     );
     const uniqueAssets = [...new Set(assetMatches)].slice(0, 24);
     uniqueAssets.forEach((assetUrl) => {{
      appendHintLink(
       'prefetch',
       assetUrl,
       assetUrl.endsWith('.css') ? 'style' : 'script',
      );
     }});
    }} catch (error) {{
     console.debug('portal chatbot warmup skipped', error);
    }}
   }});
  }};
  const loadEmbedScript = () => {{
   window.difyChatbotConfig = config;
   if (document.getElementById(config.token)) {{
    return;
   }}
   const script = document.createElement('script');
   script.src = {chatbot_embed_src_json};
   script.id = config.token;
   script.defer = true;
   document.head.appendChild(script);
  }};
  const decodeJwtPayload = (token) => {{
   try {{
    const parts = String(token || '').split('.');
    if (parts.length < 2) {{
     return null;
    }}
    const normalized = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized + '='.repeat((4 - normalized.length % 4) % 4);
    return JSON.parse(window.atob(padded));
   }} catch (error) {{
    return null;
   }}
  }};
  const getConversationInfo = () => {{
   try {{
    return JSON.parse(window.localStorage.getItem('conversationIdInfo') || 'null');
   }} catch (error) {{
    return null;
   }}
  }};
  const getStoredConversationId = (passportToken) => {{
   const payload = decodeJwtPayload(passportToken);
   const appId = payload && payload.app_id;
   if (!appId) {{
    return '';
   }}
   const conversationInfo = getConversationInfo();
   return String(conversationInfo?.[appId]?.DEFAULT || '').trim();
  }};
  const clearStoredConversationId = (passportToken) => {{
   const payload = decodeJwtPayload(passportToken);
   const appId = payload && payload.app_id;
   if (!appId) {{
    window.localStorage.removeItem('conversationIdInfo');
    return;
   }}
   const conversationInfo = getConversationInfo();
   if (!conversationInfo || typeof conversationInfo !== 'object') {{
    window.localStorage.removeItem('conversationIdInfo');
    return;
   }}
   if (conversationInfo[appId]) {{
    delete conversationInfo[appId];
   }}
   if (Object.keys(conversationInfo).length === 0) {{
    window.localStorage.removeItem('conversationIdInfo');
    return;
   }}
   window.localStorage.setItem('conversationIdInfo', JSON.stringify(conversationInfo));
  }};
  const validateStoredConversation = async (passportToken) => {{
   const conversationId = getStoredConversationId(passportToken);
   if (!conversationId) {{
    return 'ok';
   }}
   try {{
    const response = await fetch(
     `${{config.baseUrl}}/api/messages?conversation_id=${{encodeURIComponent(conversationId)}}&limit=1&last_id=`,
     {{
      headers: {{
       'X-App-Code': config.token,
       'X-App-Passport': passportToken,
      }},
      credentials: 'include',
     }},
    );
    if (response.ok) {{
     return 'ok';
    }}
    if (response.status === 404) {{
     clearStoredConversationId(passportToken);
     return 'ok';
    }}
    if (response.status === 401 || response.status === 403) {{
     return 'refresh-passport';
    }}
   }} catch (error) {{
    console.debug('portal chatbot stored conversation validation skipped', error);
   }}
   return 'ok';
  }};
  const bootstrapPassport = async () => {{
   const existingPassport = String(window.localStorage.getItem(passportStorageKey) || '').trim();
   if (existingPassport) {{
    const validationResult = await validateStoredConversation(existingPassport);
    if (validationResult === 'ok') {{
     loadEmbedScript();
     warmupChatbot();
     return;
    }}
    window.localStorage.removeItem(passportStorageKey);
   }}
   try {{
    const response = await fetch(`${{config.baseUrl}}/api/passport`, {{
     headers: {{
      'X-App-Code': config.token,
     }},
     credentials: 'include',
    }});
    if (!response.ok) {{
     throw new Error(`passport bootstrap failed: ${{response.status}}`);
    }}
    const payload = await response.json();
    if (payload && payload.access_token) {{
     window.localStorage.setItem(passportStorageKey, payload.access_token);
      clearStoredConversationId(payload.access_token);
    }}
   }} catch (error) {{
    console.error('portal chatbot passport bootstrap failed', error);
   }} finally {{
    loadEmbedScript();
    warmupChatbot();
   }}
  }};
  bootstrapPassport();
 }})();
</script>
"""


def _wechat_qr_data_url() -> str:
  """Fallback: load from file if DB has no value."""
  qr_path = Path(__file__).resolve().parents[2] / "微信二维码.jpg"
  if not qr_path.exists():
    return ""
  encoded = base64.b64encode(qr_path.read_bytes()).decode("ascii")
  return f"data:image/jpeg;base64,{encoded}"


def _load_contact_config() -> dict[str, str]:
  """Load contact config from DB (cached), with file fallback for QR."""
  with _postgres_conn() as conn:
    cfg = _get_contact_config(conn)
  if not cfg.get("wechat_qr_base64"):
    cfg["wechat_qr_base64"] = _wechat_qr_data_url()
  return cfg


def _cny(cents: int) -> str:
    amount = cents / 100
    if cents % 100 == 0:
        return f"{int(amount)}元"
    return f"{amount:.2f}元"


def _split_catalog() -> tuple[list[dict], list[dict], dict, dict, list[dict]]:
    monthly_packages = sorted(
        [pkg for pkg in DEFAULT_BILLING_PACKAGES if pkg.get("product_type") == "monthly_subscription"],
        key=lambda item: int(item.get("display_order") or 0),
    )
    recharge_packages = sorted(
        [pkg for pkg in DEFAULT_BILLING_PACKAGES if pkg.get("product_type") == "credit_pack"],
        key=lambda item: int(item.get("display_order") or 0),
    )
    signup_rule = next((rule for rule in DEFAULT_PROMOTION_RULES if rule.get("rule_code") == "signup_bonus_500"), {})
    first_discount_rule = next((rule for rule in DEFAULT_PROMOTION_RULES if rule.get("rule_code") == "first_subscription_monthly_90_off"), {})
    cumulative_rules = sorted(
        [rule for rule in DEFAULT_PROMOTION_RULES if rule.get("rule_type") == "recharge_bonus_cumulative"],
        key=lambda item: int((item.get("criteria_json") or {}).get("threshold_paid_amount_cents") or 0),
    )
    single_bonus_by_package: dict[str, dict] = {}
    for rule in DEFAULT_PROMOTION_RULES:
        if rule.get("rule_type") != "recharge_bonus_single":
            continue
        for package_code in rule.get("target_package_codes") or []:
            single_bonus_by_package[package_code] = rule
    return monthly_packages, recharge_packages, signup_rule, first_discount_rule, cumulative_rules, single_bonus_by_package


def _top_nav(active: str) -> str:
    items = [
        ("account", "账户管理", "/portal/account", "data-account-link"),
        ("products", "订阅与充值", "/portal/products", ""),
        ("guide", "使用指南", "/portal/guide", ""),
    ]
    html = []
    for key, label, href, extra in items:
        classes = "top-route-link active" if key == active else "top-route-link"
        extra_attr = f" {extra}=\"1\"" if extra else ""
        html.append(f'<a class="{classes}" href="{href}"{extra_attr}>{escape(label)}</a>')
    return "".join(html)


def _sidebar(groups: list[tuple[str, list[tuple[str, str]]]]) -> str:
    return "".join(
        '<div class="nav-group"><div class="nav-group-title">{}</div>{}</div>'.format(
            escape(group_title),
            "".join(
                f'<a class="nav-item" href="#{escape(anchor)}">{escape(label)}</a>'
                for anchor, label in items
            ),
        )
        for group_title, items in groups
    )


def _layout(*, active: str, kicker: str, title: str, subtitle: str, sidebar_html: str, body_html: str) -> str:
    openwebui_home_url = escape(_portal_public_base_url())
    chatbot_snippet = _render_portal_chatbot_snippet()
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>虾密小助手 - {escape(title)}</title>
  <style>{_BASE_CSS}</style>
</head>
<body>
<div class="portal-shell">
  <nav class="sidebar">
    <div class="brand">🦐 虾密小助手<span class="brand-subtitle">公开产品页与使用指南</span></div>
    {sidebar_html}
  </nav>
  <div class="workspace">
    <div class="workspace-topbar">
      <div class="workspace-topbar-inner">
        <div>
          <div class="page-title-row"><h1>{escape(title)}</h1></div>
          <div class="subtitle">{escape(subtitle)}</div>
        </div>
        <div class="topbar-actions">
          <div class="top-route-nav">{_top_nav(active)}</div>
          <div class="top-utility-actions">
            <a class="top-home-link" id="open-webui-home-link" href="{openwebui_home_url}">回到首要</a>
          </div>
        </div>
      </div>
    </div>
    <div class="main">
      <div class="main-stack">{body_html}</div>
    </div>
  </div>
</div>
<script>
(function() {{
  var token = new URLSearchParams(location.search).get("t") || "";
  var sectionLinks = document.querySelectorAll(".sidebar .nav-item[href^='#']");
  function withPortalToken(href) {{
    if (!token || !href || href.indexOf("/portal/") !== 0 || /[?&]t=/.test(href)) {{
      return href;
    }}
    return href + (href.indexOf("?") === -1 ? "?" : "&") + "t=" + encodeURIComponent(token);
  }}
  if (token) {{
    document.querySelectorAll('a[href^="/portal/"]').forEach(function(el) {{
      el.href = withPortalToken(el.getAttribute("href") || "");
    }});
  }}
  function markActiveSection() {{
    var current = location.hash || (sectionLinks[0] ? sectionLinks[0].getAttribute("href") : "");
    sectionLinks.forEach(function(link) {{
      link.classList.toggle("active", link.getAttribute("href") === current);
    }});
  }}
  sectionLinks.forEach(function(link) {{
    link.addEventListener("click", function() {{
      setTimeout(markActiveSection, 0);
    }});
  }});
  markActiveSection();
}})();
</script>
{chatbot_snippet}
</body>
</html>"""


def render_portal_products_html() -> str:
    monthly_packages, recharge_packages, signup_rule, first_discount_rule, cumulative_rules, single_bonus_by_package = _split_catalog()

    monthly_cards = []
    for package in monthly_packages:
        meta = package.get("meta_json") or {}
        display_name = meta.get("display_name") or package.get("package_name") or package.get("package_code")
        renewal_label = meta.get("renewal_price_label") or _cny(int(package.get("price_cents") or 0))
        package_code = escape(str(package.get("package_code") or ""))
        monthly_cards.append(
            f'''
            <div class="offer-card{' featured' if package.get('package_code') == 'monthly_pro' else ''}">
              <div class="offer-top">
                <div>
                  <div class="offer-name">{escape(str(display_name))}</div>
                  <div class="offer-tagline">{escape(str(meta.get('display_tagline') or '适合不同强度的持续使用场景'))}</div>
                </div>
                <div class="offer-badge">按月订阅</div>
              </div>
              <div class="offer-price"><div class="offer-price-main">{escape(str(meta.get('renewal_price_label') or renewal_label))}</div></div>
              <div class="offer-points">{escape(str(meta.get('display_points') or f"{int(package.get('points_amount') or 0)} 积分 / 月"))}</div>
              <div class="bullet-list">
                <div class="bullet-item">月度积分：{int(package.get('points_amount') or 0)} 积分</div>
                <div class="bullet-item">计费周期：{int(package.get('period_days') or 30)} 天</div>
                <div class="bullet-item">扣减顺序：优先消耗当前月包剩余积分</div>
                <div class="bullet-item">续费说明：按标准月费续费，当前标价 {escape(str(renewal_label))}</div>
                <div class="bullet-item">首月促销：{escape(str((first_discount_rule.get('meta_json') or {}).get('display_text') or '首次订阅月包首月 1 折'))}</div>
              </div>
              <div class="offer-actions">
                <a class="offer-cta" data-checkout-link="1" href="/portal/checkout?package_code={package_code}">立即下单</a>
                <span class="cta-hint">登录后进入受保护结算页，支持支付宝与微信支付。</span>
              </div>
            </div>
            '''
        )

    recharge_cards = []
    for package in recharge_packages:
        meta = package.get("meta_json") or {}
        bonus_rule = single_bonus_by_package.get(str(package.get("package_code") or ""), {})
        bonus_points = int(bonus_rule.get("benefit_value") or 0)
        total_points = int(package.get("points_amount") or 0) + bonus_points
        package_code = escape(str(package.get("package_code") or ""))
        recharge_cards.append(
            f'''
            <div class="offer-card">
              <div class="offer-top">
                <div>
                  <div class="offer-name">{escape(str(meta.get('display_name') or package.get('package_name') or package.get('package_code')))}</div>
                  <div class="offer-tagline">{escape(str(meta.get('display_tagline') or '按基础比例充值，可叠加单笔赠送'))}</div>
                </div>
                <div class="offer-badge">灵活补量</div>
              </div>
              <div class="offer-price"><div class="offer-price-main">{escape(_cny(int(package.get('price_cents') or 0)))}</div></div>
              <div class="offer-points">基础到账 {int(package.get('points_amount') or 0)} 积分</div>
              <div class="bullet-list">
                <div class="bullet-item">有效期：永久有效</div>
                <div class="bullet-item">单笔赠送：{bonus_points} 积分</div>
                <div class="bullet-item">实付后总到账：{total_points} 积分</div>
                <div class="bullet-item">活动说明：{escape(str((bonus_rule.get('meta_json') or {}).get('display_text') or '按单笔充值活动赠送'))}</div>
              </div>
              <div class="offer-actions">
                <a class="offer-cta" data-checkout-link="1" href="/portal/checkout?package_code={package_code}">立即下单</a>
                <span class="cta-hint">下单后可在同页查看支付状态与到账结果。</span>
              </div>
            </div>
            '''
        )

    newcomer_cards = f'''
      <div class="offer-card featured">
        <div class="offer-top">
          <div>
            <div class="offer-name">新注册赠送</div>
            <div class="offer-tagline">用于降低首次进入产品时的试用门槛。</div>
          </div>
          <div class="offer-badge">新用户区</div>
        </div>
        <div class="offer-price"><div class="offer-price-main">{int(signup_rule.get('benefit_value') or 0)} 积分</div></div>
        <div class="bullet-list">
          <div class="bullet-item">活动说明：{escape(str((signup_rule.get('meta_json') or {}).get('display_text') or signup_rule.get('rule_name') or '新注册即送积分'))}</div>
          <div class="bullet-item">到账方式：邮箱验证成功后记入账户。</div>
        </div>
      </div>
      <div class="offer-card">
        <div class="offer-top">
          <div>
            <div class="offer-name">首次订阅首月 1 折</div>
            <div class="offer-tagline">适合首次尝试月包的用户。</div>
          </div>
          <div class="offer-badge">首单转化</div>
        </div>
        <div class="offer-price"><div class="offer-price-main">首月 1 折</div></div>
        <div class="bullet-list">
          <div class="bullet-item">活动说明：{escape(str((first_discount_rule.get('meta_json') or {}).get('display_text') or first_discount_rule.get('rule_name') or '首次订阅月包首月 1 折'))}</div>
          <div class="bullet-item">适用范围：仅首次订阅月包时可用。</div>
        </div>
      </div>
    '''

    cumulative_reward_cards = "".join(
        f'''
        <div class="timeline-item">
          <div class="timeline-title">累计充值满 {escape(_cny(int((rule.get('criteria_json') or {}).get('threshold_paid_amount_cents') or 0)))}</div>
          <div class="timeline-desc">额外赠送 {int(rule.get('benefit_value') or 0)} 积分。{escape(str((rule.get('meta_json') or {}).get('display_text') or rule.get('rule_name') or '按累计充值门槛赠送'))}</div>
        </div>
        '''
        for rule in cumulative_rules
    )

    body_html = f'''
      <section id="monthly" class="section-block card">
        <h2>月包区</h2>
        <div class="card-note">适合持续稳定使用。月包积分会在当前套餐有效期内优先扣减，到期后自动清零。</div>
        <div class="offer-grid">{"".join(monthly_cards)}</div>
      </section>
      <section id="recharge" class="section-block card">
        <h2>充值区</h2>
        <div class="card-note">适合临时补量。充值包积分永久有效，只有在月包余额不足时才会继续扣减充值包积分。</div>
        <div class="mini-kpi-row">
          <div class="mini-kpi"><div class="mini-kpi-value">100 : 1</div><div class="mini-kpi-label">积分 : 元</div></div>
          <div class="mini-kpi"><div class="mini-kpi-value">{len(recharge_packages)}</div><div class="mini-kpi-label">充值包数量</div></div>
          <div class="mini-kpi"><div class="mini-kpi-value">{len(cumulative_rules)}</div><div class="mini-kpi-label">累计奖励档位</div></div>
        </div>
        <div style="height:16px"></div>
        <div class="offer-grid">{"".join(recharge_cards)}</div>
        <div style="height:18px"></div>
        <div class="card-note">累计充值奖励按实付金额分档触发，达到门槛后会额外到账奖励积分。当前累计口径只统计充值包实付金额，月包实付金额现在不计入累计充值奖励。</div>
        <div class="timeline-list">{cumulative_reward_cards}</div>
      </section>
      <section id="newcomer" class="section-block card">
        <h2>新用户区</h2>
        <div class="card-note">首次使用时可查看新用户赠送和首单订阅优惠，便于快速开始体验。</div>
        <div class="offer-grid">{newcomer_cards}</div>
      </section>
    '''

    sidebar_html = _sidebar([
        ("订阅方案", [("monthly", "月包区"), ("recharge", "充值区"), ("newcomer", "新用户区")]),
    ])
    return _layout(
        active="products",
        kicker="订阅与充值",
        title="产品方案与充值说明",
        subtitle="说明不同方案的积分额度、有效期和到账方式，便于按使用强度选择合适的订阅或充值方案。",
        sidebar_html=sidebar_html,
        body_html=body_html,
    )


def render_portal_guide_html() -> str:
    body_html = '''
      <section id="start" class="section-block card">
        <h2>新手上手路径</h2>
        <div class="card-note">第一次使用时，不建议一上来就跑很大的任务。先按下面这条路径走一遍，通常 5 分钟内就能完成第一次有效体验。</div>
        <div class="guide-list">
          <div class="guide-item"><div class="guide-title">1. 先登录，再确认账户可用</div><div class="guide-desc">从 Open WebUI 首页进入产品，首次登录后系统会自动初始化账户。建议先用 /me 或 /points 看一下当前套餐、积分余额和是否已经完成邮箱验证。</div></div>
          <div class="guide-item"><div class="guide-title">2. 有完整任务时优先用 /workflow</div><div class="guide-desc">如果你已经知道目标市场、类目和问题，直接用 /workflow 最省事。它适合输出一份相对完整的分析结果，而不是只查一个局部指标。</div></div>
          <div class="guide-item"><div class="guide-title">3. 只是验证一个点时用 /tool 或 /web</div><div class="guide-desc">如果你只想先验证趋势、规则或某个市场变化，不要急着跑完整 workflow。先用 /tool 做局部分析，或者用 /web 查最新外部信息，会更稳也更省积分。</div></div>
          <div class="guide-item"><div class="guide-title">4. 看结果时先看结论，再看证据</div><div class="guide-desc">优先关注结论、关键指标、风险提示；如果结果和预期不一致，再回看工具返回、知识库引用和输入条件，判断是不是问题范围太大或条件不够明确。</div></div>
          <div class="guide-item"><div class="guide-title">5. 用完回到账户页核对消费</div><div class="guide-desc">每次使用后，都可以回到账户管理页看消费记录、扣减来源和使用趋势。系统会优先扣减月包积分，月包不足时再扣充值包积分。</div></div>
        </div>
      </section>
      <section id="commands" class="section-block card">
        <h2>常用命令示例</h2>
        <div class="card-note">下面这些命令可以直接复制后再替换商品、市场和时间范围。对于新手来说，先照着示例改，比从零组织问题更容易成功。</div>
        <div class="example-grid">
          <div class="example-card highlight">
            <div class="example-kicker">完整分析</div>
            <h3 class="example-title">/workflow：拿一份完整的选品分析</h3>
            <p class="example-desc">适合已经有目标商品或类目，希望系统自动调工具、拉数据、形成结论的场景。</p>
            <div class="command-block">/workflow 帮我调研一下 portable blender 在 Amazon 美国站近 90 天的需求、竞争和进入机会，重点看价格带、销量趋势和风险点</div>
            <div class="example-meta">
              <div class="example-meta-item">适合：第一次做完整市场判断、要拿结构化结论时。</div>
              <div class="example-meta-item">提示：问题里尽量带上市场、类目、时间范围和你最关心的输出。</div>
            </div>
          </div>
          <div class="example-card">
            <div class="example-kicker">局部验证</div>
            <h3 class="example-title">/tool：先查一个点，再决定要不要跑大任务</h3>
            <p class="example-desc">适合你已经有一个猜想，只想先验证趋势、竞争强度或类目情况。</p>
            <div class="command-block">/tool 帮我先判断 pet grooming vacuum 在 TikTok 美国市场最近是否明显升温，并告诉我下一步最值得调用哪些工具验证</div>
            <div class="example-meta">
              <div class="example-meta-item">适合：快速试水、缩小问题范围、减少无效消耗。</div>
              <div class="example-meta-item">提示：如果只是查一个指标或一个判断，不要一开始就跑完整 workflow。</div>
            </div>
          </div>
          <div class="example-card">
            <div class="example-kicker">最新信息</div>
            <h3 class="example-title">/web：查最新政策、站外情报和外部变化</h3>
            <p class="example-desc">适合政策变化、平台动态、行业新闻这类需要最新外部信息的问题。</p>
            <div class="command-block">/web 帮我搜索并总结 2026 年 TikTok Shop 美国站最近的入驻政策和合规变化，重点列出卖家最容易踩坑的点</div>
            <div class="example-meta">
              <div class="example-meta-item">适合：知识库不一定覆盖、你又需要最新信息的时候。</div>
              <div class="example-meta-item">提示：实时外部变化优先用 /web，不要只靠知识库回答。</div>
            </div>
          </div>
          <div class="example-card">
            <div class="example-kicker">账户自查</div>
            <h3 class="example-title">/points 和 /usage：看余额、消费和使用趋势</h3>
            <p class="example-desc">适合你做完几轮分析之后，快速确认积分是否够用、最近主要消耗在哪类请求上。</p>
            <div class="command-block">/points
/usage</div>
            <div class="example-meta">
              <div class="example-meta-item">适合：复盘最近消耗、判断是否需要月包或充值包。</div>
              <div class="example-meta-item">提示：账户页会展示更完整的消费记录、扣减来源和中文解释。</div>
            </div>
          </div>
        </div>
      </section>
      <section id="scenes" class="section-block card">
        <h2>什么时候用哪种模式</h2>
        <div class="card-note">如果你不知道该用哪个命令，先按下面的判断来，通常不会错。</div>
        <div class="notice-grid">
          <div class="notice-card accent"><h3 class="notice-title">我有完整问题，想一次拿到结论</h3><p class="notice-desc">优先用 /workflow。它更适合做“某商品在某市场是否值得做”这类完整分析。</p></div>
          <div class="notice-card"><h3 class="notice-title">我只想先验证一个局部判断</h3><p class="notice-desc">优先用 /tool。它更适合先做小范围验证，再决定要不要继续扩大任务。</p></div>
          <div class="notice-card"><h3 class="notice-title">我需要最新外部信息</h3><p class="notice-desc">优先用 /web。平台政策、行业新闻、外部舆情和近期变化都更适合走联网搜索。</p></div>
          <div class="notice-card"><h3 class="notice-title">我想知道余额和最近消耗</h3><p class="notice-desc">优先用 /points、/usage，或者直接去账户页看消费记录、使用趋势和扣减来源。</p></div>
        </div>
      </section>
      <section id="support" class="section-block card">
        <h2>遇到问题先这样处理</h2>
        <div class="card-note">新手最容易卡在“不知道怎么提问”或者“结果看不懂”。先用下面这套办法排查，通常比反复重跑更有效。</div>
        <div class="guide-list">
          <div class="guide-item"><div class="guide-title">先把问题说完整</div><div class="guide-desc">尽量一次写清楚市场、类目、时间范围、目标用户和你想要的输出，避免系统反复追问或跑偏。</div></div>
          <div class="guide-item"><div class="guide-title">第一次先小范围试跑</div><div class="guide-desc">如果任务很大，先从单市场、单类目开始。确认方向对了，再扩大到更多国家或更多商品段。</div></div>
          <div class="guide-item"><div class="guide-title">右下角智能客服可以直接问</div><div class="guide-desc">如果你不知道命令怎么写、套餐怎么选、消费为什么这样扣，或者某个页面怎么用，可以直接问右下角的智能客服。它更适合回答操作问题和产品规则。</div></div>
          <div class="guide-item"><div class="guide-title">结果异常时先看证据和工具返回</div><div class="guide-desc">不要只盯最终一句结论。优先检查输入条件是否过宽、是否用了错误市场，以及工具返回的数据是不是不完整。</div></div>
        </div>
      </section>
      <section id="demo" class="section-block card">
        <h2>演示区预留</h2>
        <div class="card-note">这里已经预留好后续演示位。等你准备好实际操作 GIF 或截图后，可以直接替换，不需要再改导航结构。</div>
        <div class="demo-grid">
          <div class="demo-card">
            <h3 class="demo-title">演示 1：如何发起一次 /workflow</h3>
            <p class="demo-desc">建议后续放一张或一段演示“输入命令 -> 等待执行 -> 查看结论”的 GIF 或截图。</p>
            <div class="demo-media" data-demo-slot="workflow">
              <div>
                <div class="demo-placeholder-title">预留 GIF / 截图区</div>
                <p class="demo-placeholder-note">后续可替换成实际使用虾米选品智能体的演示 GIF；如果暂时没有 GIF，也可以先放一张实操截图。</p>
              </div>
            </div>
            <p class="demo-caption">建议内容：输入 /workflow 命令、等待进度、查看最终结果。</p>
          </div>
          <div class="demo-card">
            <h3 class="demo-title">演示 2：如何查看消费记录和扣减来源</h3>
            <p class="demo-desc">建议后续放一张账户页截图，让新手理解“为什么扣费”和“月包/充值包是怎么被扣的”。</p>
            <div class="demo-media" data-demo-slot="billing">
              <div>
                <div class="demo-placeholder-title">预留 GIF / 截图区</div>
                <p class="demo-placeholder-note">后续可替换成账户页实操截图，例如消费记录页、使用趋势页或积分概览页。</p>
              </div>
            </div>
            <p class="demo-caption">建议内容：消费记录、扣减来源、当前余额与使用趋势。</p>
          </div>
        </div>
      </section>
    '''

    sidebar_html = _sidebar([
        ("使用说明", [("start", "新手上手"), ("commands", "命令示例"), ("scenes", "模式选择"), ("support", "常见卡点"), ("demo", "演示区预留")]),
    ])
    return _layout(
        active="guide",
        kicker="使用指南",
        title="产品使用指南",
        subtitle="把新手最常见的使用路径、命令示例和操作提醒整理成一页，方便你快速开始并少走弯路。",
        sidebar_html=sidebar_html,
        body_html=body_html,
    )


def render_portal_password_reset_html() -> str:
    openwebui_home_url = escape(_portal_public_base_url())
    body_html = f'''
      <section id="request" class="section-block card">
        <h2>第一步：发送验证码</h2>
        <div class="form-grid">
          <div class="field-grid">
            <label class="field-group">
              <span class="field-label">注册邮箱</span>
              <input id="password-reset-email" class="text-field" type="email" autocomplete="email" placeholder="请输入登录邮箱" />
              <span class="field-hint">如果该邮箱对应 Open WebUI 账户，验证码会发送到该邮箱。</span>
            </label>
          </div>
          <div class="checkout-actions">
            <button type="button" class="offer-cta" id="password-reset-request-button">发送验证码</button>
            <a class="ghost-button" href="{openwebui_home_url}">回到登录页</a>
          </div>
          <div id="password-reset-request-status" class="status-banner"></div>
        </div>
      </section>
      <section id="confirm" class="section-block card">
        <h2>第二步：设置新密码</h2>
        <div class="card-note">验证码校验通过后，系统会直接回写 Open WebUI 账号库中的密码。重置成功后，请返回登录页重新登录。</div>
        <div class="form-grid">
          <div class="field-grid">
            <label class="field-group">
              <span class="field-label">验证码</span>
              <input id="password-reset-code" class="text-field" type="text" inputmode="numeric" maxlength="8" placeholder="输入邮箱验证码" />
            </label>
            <label class="field-group">
              <span class="field-label">新密码</span>
              <input id="password-reset-new-password" class="text-field" type="password" autocomplete="new-password" placeholder="至少 8 位" />
            </label>
            <label class="field-group">
              <span class="field-label">确认新密码</span>
              <input id="password-reset-confirm-password" class="text-field" type="password" autocomplete="new-password" placeholder="再次输入新密码" />
            </label>
          </div>
          <div class="card-note">建议使用字母、数字和符号组合；长度不要超过 72 字节。</div>
          <div class="checkout-actions">
            <button type="button" class="offer-cta" id="password-reset-confirm-button">确认重置密码</button>
            <a class="ghost-button" href="{openwebui_home_url}">返回登录</a>
          </div>
          <div id="password-reset-confirm-status" class="status-banner"></div>
        </div>
      </section>
      <section id="support" class="section-block card">
        <h2>常见说明</h2>
        <div class="guide-list">
          <div class="guide-item"><div class="guide-title">为什么我没收到邮件？</div><div class="guide-desc">先检查垃圾邮箱和退信箱。如果多次点击发送，可能触发了频率限制。你也可以等一分钟后再试一次。</div></div>
          <div class="guide-item"><div class="guide-title">重置后原有登录态会怎样？</div><div class="guide-desc">第一版会要求你手动重新登录。若你当前浏览器仍保留旧登录态，建议主动退出再重新登录，以确保凭据完全切换。</div></div>
          <div class="guide-item"><div class="guide-title">邮箱不存在时会提示吗？</div><div class="guide-desc">会。当前邮箱如果尚未注册，页面会直接提示“当前邮箱尚未注册，无法找回密码”。</div></div>
        </div>
      </section>
    '''

    sidebar_html = _sidebar([
        ("密码找回", [("request", "发送验证码"), ("confirm", "设置新密码"), ("support", "常见说明")]),
    ])

    page = _layout(
        active="recover",
        kicker="账户恢复",
        title="邮箱验证码找回密码",
        subtitle="用于在忘记 Open WebUI 登录密码时，通过注册邮箱完成验证并设置新密码。",
        sidebar_html=sidebar_html,
        body_html=body_html,
    )
    script = '''
<script>
(function() {
  var requestBtn = document.getElementById("password-reset-request-button");
  var confirmBtn = document.getElementById("password-reset-confirm-button");
  var emailInput = document.getElementById("password-reset-email");
  var codeInput = document.getElementById("password-reset-code");
  var newPasswordInput = document.getElementById("password-reset-new-password");
  var confirmPasswordInput = document.getElementById("password-reset-confirm-password");
  var requestStatus = document.getElementById("password-reset-request-status");
  var confirmStatus = document.getElementById("password-reset-confirm-status");

  function setStatus(el, text, state) {
    if (!el) return;
    el.textContent = text || "";
    if (!text) {
      el.removeAttribute("data-state");
      return;
    }
    el.setAttribute("data-state", state || "info");
  }

  async function postJson(url, payload) {
    var response = await fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      credentials: "same-origin",
      body: JSON.stringify(payload || {})
    });
    var data = null;
    try {
      data = await response.json();
    } catch (error) {
      data = null;
    }
    if (!response.ok || !data || !data.success) {
      var message = data && data.message
        ? data.message
        : (data && data.error && data.error.message ? data.error.message : "请求失败，请稍后重试");
      throw new Error(message);
    }
    return data.data || {};
  }

  if (requestBtn) {
    requestBtn.addEventListener("click", async function() {
      var email = (emailInput && emailInput.value || "").trim();
      setStatus(requestStatus, "", "info");
      if (!email) {
        setStatus(requestStatus, "请先输入邮箱地址。", "error");
        return;
      }
      requestBtn.disabled = true;
      setStatus(requestStatus, "正在发送验证码，请稍候...", "info");
      try {
        await postJson("/portal/api/public/password-reset/request", {email: email});
        setStatus(requestStatus, "验证码已发送，请去邮箱查收后继续下一步。", "success");
      } catch (error) {
        setStatus(requestStatus, error.message || "发送验证码失败，请稍后重试。", "error");
      } finally {
        requestBtn.disabled = false;
      }
    });
  }

  if (confirmBtn) {
    confirmBtn.addEventListener("click", async function() {
      var email = (emailInput && emailInput.value || "").trim();
      var code = (codeInput && codeInput.value || "").trim();
      var newPassword = newPasswordInput && newPasswordInput.value || "";
      var confirmPassword = confirmPasswordInput && confirmPasswordInput.value || "";
      setStatus(confirmStatus, "", "info");
      if (!email) {
        setStatus(confirmStatus, "请先填写邮箱地址。", "error");
        return;
      }
      if (!code) {
        setStatus(confirmStatus, "请先输入邮箱验证码。", "error");
        return;
      }
      if (!newPassword) {
        setStatus(confirmStatus, "请先输入新密码。", "error");
        return;
      }
      if (newPassword !== confirmPassword) {
        setStatus(confirmStatus, "两次输入的新密码不一致。", "error");
        return;
      }
      confirmBtn.disabled = true;
      setStatus(confirmStatus, "正在校验验证码并重置密码...", "info");
      try {
        await postJson("/portal/api/public/password-reset/confirm", {
          email: email,
          code: code,
          new_password: newPassword
        });
        if (newPasswordInput) newPasswordInput.value = "";
        if (confirmPasswordInput) confirmPasswordInput.value = "";
        if (codeInput) codeInput.value = "";
        setStatus(confirmStatus, "密码已重置成功，请返回登录页重新登录。", "success");
        window.setTimeout(function() {
          window.location.href = "''' + openwebui_home_url + '''";
        }, 1200);
      } catch (error) {
        setStatus(confirmStatus, error.message || "重置密码失败，请稍后重试。", "error");
      } finally {
        confirmBtn.disabled = false;
      }
    });
  }
})();
</script>'''
    return page.replace("</body>", script + "</body>")


def render_portal_checkout_html(
    *,
    selected_package: dict[str, Any] | None = None,
    pricing_preview: dict[str, Any] | None = None,
    mock_payment_enabled: bool = False,
) -> str:
    package_meta = (selected_package or {}).get("meta_json") or {}
    pricing = (pricing_preview or {}).get("pricing") or {}
    applied_promotions = pricing_preview.get("applied_promotions") or [] if pricing_preview else []
    reward_promotions = pricing_preview.get("reward_promotions") or [] if pricing_preview else []

    if selected_package:
        package_name = escape(
            str(
                package_meta.get("display_name")
                or selected_package.get("package_name")
                or selected_package.get("package_code")
                or "未命名套餐"
            )
        )
        package_subtitle = escape(
            str(
                package_meta.get("display_tagline")
                or ("持续月度权益" if selected_package.get("product_type") == "monthly_subscription" else "灵活补量方案")
            )
        )
        total_points = int(pricing.get("points_amount") or selected_package.get("points_amount") or 0)
        summary_html = f'''
          <div class="checkout-package-name">{package_name}</div>
          <div class="checkout-package-subtitle">{package_subtitle}</div>
          <div class="checkout-price-row">
            <div class="checkout-price-card"><div class="checkout-price-label">原价</div><div class="checkout-price-value">{escape(_cny(int(pricing.get('list_amount_cents') or selected_package.get('price_cents') or 0)))}</div></div>
            <div class="checkout-price-card"><div class="checkout-price-label">优惠</div><div class="checkout-price-value">{escape(_cny(int(pricing.get('discount_amount_cents') or 0)))}</div></div>
            <div class="checkout-price-card"><div class="checkout-price-label">当前应付</div><div class="checkout-price-value emphasis">{escape(_cny(int(pricing.get('payable_amount_cents') or selected_package.get('price_cents') or 0)))}</div></div>
            <div class="checkout-price-card"><div class="checkout-price-label">到账权益</div><div class="checkout-price-value">{total_points} 积分</div></div>
          </div>
        '''
    else:
        summary_html = '''
          <div class="checkout-package-name">未选择套餐</div>
          <div class="checkout-package-subtitle">请先回到订阅与充值页，从具体月包或充值包进入下单页。</div>
        '''

    promo_items = []
    for item in applied_promotions:
        promo_items.append(
            '<div class="promo-item"><strong>{}</strong><div class="checkout-muted">{}</div></div>'.format(
                escape(str(item.get("display_text") or item.get("rule_name") or item.get("rule_code") or "优惠活动")),
                escape(str(item.get("rule_type") or "下单时直接抵扣")),
            )
        )
    for item in reward_promotions:
        reward_points = int(item.get("reward_points") or item.get("benefit_value") or 0)
        promo_items.append(
            '<div class="promo-item"><strong>{}</strong><div class="checkout-muted">支付成功后额外到账 {} 积分。</div></div>'.format(
                escape(str(item.get("display_text") or item.get("rule_name") or item.get("rule_code") or "到账奖励")),
                reward_points,
            )
        )
    promo_html = "".join(promo_items) if promo_items else '<div class="checkout-note">当前套餐没有叠加中的促销，支付成功后将按基础权益到账。</div>'
    selected_package_name_js = escape(str(package_meta.get("display_name") or (selected_package or {}).get("package_name") or ""))

    body_html = '''
      <section id="summary" class="section-block card">
        <h2>订单确认</h2>
        <div class="card-note">下单前先确认套餐、应付金额与支付后到账权益。当前页只处理单次订单，不直接修改账户余额。</div>
        <div class="checkout-summary" id="checkout-summary">__CHECKOUT_SUMMARY__</div>
      </section>
      <section id="payment" class="section-block card">
        <h2>支付方式</h2>
        <div class="card-note">MVP 阶段先把结算页、订单状态和到账联动打通。真实支付宝与微信下单通道后续接入，当前页面已经按两种支付方式组织。</div>
        <div class="payment-method-row" id="payment-method-row">
          <button type="button" class="payment-method active" data-provider="alipay">支付宝</button>
          <button type="button" class="payment-method" data-provider="wechat">微信支付</button>
        </div>
        <div style="height:16px"></div>
        <div class="checkout-actions">
          <button type="button" id="create-order-btn">创建支付订单</button>
          <button type="button" id="simulate-paid-btn" style="display:none;">模拟支付成功</button>
          <a class="ghost-button" id="back-products-link" href="/portal/products">回到套餐页</a>
        </div>
        <div style="height:14px"></div>
        <div class="checkout-note" id="payment-note">创建订单后会进入待支付状态；如果当前是本地联调环境，可以直接触发模拟支付成功，验证到账链路。</div>
      </section>
      <section id="status" class="section-block card">
        <h2>订单状态</h2>
        <div class="card-note">支付成功后，这里的状态会更新为已支付，并可以直接跳到账户页核对余额、账本和套餐状态。</div>
        <div class="order-status-panel" id="order-status-panel">
          <div class="checkout-note">还没有创建订单。请选择支付方式后点击“创建支付订单”。</div>
        </div>
      </section>
      <section id="help" class="section-block card">
        <h2>促销与到账说明</h2>
        <div class="card-note">订单在创建时会固化 pricing snapshot。即使之后活动规则发生变化，这一笔订单仍按下单当刻的优惠和奖励执行。</div>
        <div class="promo-list">__PROMO_ITEMS__</div>
      </section>
      <script>
      (function() {
        var params = new URLSearchParams(location.search);
        var portalToken = params.get("t") || "";
        var packageCode = params.get("package_code") || "";
        var currentOrderId = params.get("order_id") || "";
        var mockPaymentEnabled = __MOCK_PAYMENT_ENABLED__;
        var selectedProvider = "alipay";
        var selectedPackageName = __SELECTED_PACKAGE_NAME__;
        var orderPanel = document.getElementById("order-status-panel");
        var noteEl = document.getElementById("payment-note");
        var createButton = document.getElementById("create-order-btn");
        var simulateButton = document.getElementById("simulate-paid-btn");
        var backProductsLink = document.getElementById("back-products-link");
        var pollTimer = null;

        function esc(s) {
          var el = document.createElement("span");
          el.textContent = s == null ? "" : String(s);
          return el.innerHTML;
        }
        function toCny(cents) {
          var amount = parseInt(cents, 10) || 0;
          return amount % 100 === 0 ? (amount / 100) + "元" : (amount / 100).toFixed(2) + "元";
        }
        function fmtTime(ts) {
          if (!ts) return "-";
          var d = new Date(ts);
          if (isNaN(d.getTime())) return String(ts).slice(0, 19);
          return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0") + " " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
        }
        function withPortalToken(path) {
          if (!portalToken || !path || /[?&]t=/.test(path)) return path;
          return path + (path.indexOf("?") === -1 ? "?" : "&") + "t=" + encodeURIComponent(portalToken);
        }
        function updateSearchParams(nextOrderId) {
          var updated = new URLSearchParams(location.search);
          if (portalToken) updated.set("t", portalToken);
          if (packageCode) updated.set("package_code", packageCode);
          if (nextOrderId) updated.set("order_id", nextOrderId);
          else updated.delete("order_id");
          history.replaceState(null, "", location.pathname + "?" + updated.toString() + location.hash);
        }
        function apiFetch(path, options) {
          options = options || {};
          options.credentials = "same-origin";
          options.headers = Object.assign({}, options.headers || {});
          if (options.body && !options.headers["Content-Type"]) {
            options.headers["Content-Type"] = "application/json";
          }
          return fetch(withPortalToken(path), options).then(function(resp) {
            return resp.json().catch(function() { return {}; }).then(function(body) {
              if (!resp.ok || body.success !== true) {
                throw new Error(body.detail || body.message || resp.statusText || "请求失败");
              }
              return body.data;
            });
          });
        }
        function setLoading(loading) {
          createButton.disabled = loading;
          createButton.textContent = loading ? "创建中..." : "创建支付订单";
        }
        function setSelectedProvider(provider) {
          selectedProvider = provider;
          document.querySelectorAll(".payment-method[data-provider]").forEach(function(button) {
            button.classList.toggle("active", button.getAttribute("data-provider") === provider);
          });
          noteEl.textContent = provider === "wechat"
            ? "当前选择微信支付。真实通道接入后，这里会展示微信 Native 下单二维码。"
            : "当前选择支付宝。真实通道接入后，这里会展示支付宝扫码下单信息。";
        }
        function statusClass(status) {
          if (status === "paid") return "paid";
          if (status === "pending") return "pending";
          return "other";
        }
        function maybeToggleSimulate(order) {
          simulateButton.style.display = mockPaymentEnabled && order && order.status === "pending" ? "inline-flex" : "none";
          simulateButton.disabled = !(mockPaymentEnabled && order && order.status === "pending");
        }
        function renderOrderState(payload) {
          var order = payload && payload.order ? payload.order : null;
          var packageData = payload && payload.package ? payload.package : null;
          var pricingSnapshot = payload && payload.pricing_snapshot ? payload.pricing_snapshot : null;
          if (!order) {
            orderPanel.innerHTML = '<div class="checkout-note">还没有创建订单。请选择支付方式后点击“创建支付订单”。</div>';
            maybeToggleSimulate(null);
            return;
          }
          var pricing = pricingSnapshot && pricingSnapshot.pricing ? pricingSnapshot.pricing : null;
          var packageName = packageData && ((packageData.meta_json || {}).display_name || packageData.package_name || packageData.package_code) || selectedPackageName || order.package_code || "当前套餐";
          var actionHtml = order.status === "paid"
            ? '<div class="checkout-actions"><a class="offer-cta" href="' + esc(withPortalToken('/portal/account#balance')) + '">到账户页查看余额</a><a class="ghost-button" href="' + esc(withPortalToken('/portal/account#topup')) + '">查看到账记录</a></div>'
            : '<div class="checkout-note">订单已创建，等待支付结果。真实支付接入后这里将展示二维码或跳转支付链接。</div>';
          orderPanel.innerHTML = '' +
            '<div><span class="status-badge ' + statusClass(order.status) + '">' + esc(order.status === 'paid' ? '已支付' : (order.status === 'pending' ? '待支付' : order.status || '未知状态')) + '</span></div>' +
            '<div class="status-grid">' +
              '<div class="status-card"><div class="status-card-label">订单号</div><div class="status-card-value">' + esc(order.order_id || '-') + '</div></div>' +
              '<div class="status-card"><div class="status-card-label">支付方式</div><div class="status-card-value">' + esc(order.provider === 'wechat' ? '微信支付' : (order.provider === 'alipay' ? '支付宝' : (order.provider || '-'))) + '</div></div>' +
              '<div class="status-card"><div class="status-card-label">应付金额</div><div class="status-card-value">' + esc(toCny(pricing ? pricing.payable_amount_cents : order.amount_cents)) + '</div></div>' +
              '<div class="status-card"><div class="status-card-label">套餐权益</div><div class="status-card-value">' + esc(String(pricing ? (pricing.points_amount || 0) : (order.points_amount || 0))) + ' 积分</div></div>' +
            '</div>' +
            '<div class="checkout-note">套餐：' + esc(packageName) + '；创建时间：' + esc(fmtTime(order.created_at)) + '；支付时间：' + esc(fmtTime(order.paid_at)) + '。</div>' +
            actionHtml;
          maybeToggleSimulate(order);
        }
        function clearPolling() {
          if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
          }
        }
        function startPolling() {
          clearPolling();
          if (!currentOrderId) return;
          pollTimer = setInterval(function() {
            loadOrder(currentOrderId, true);
          }, 2500);
        }
        function loadOrder(orderId, silent) {
          return apiFetch('/portal/api/payments/orders/' + encodeURIComponent(orderId)).then(function(data) {
            currentOrderId = data.order && data.order.order_id ? data.order.order_id : orderId;
            renderOrderState(data);
            if (data.order && data.order.status === 'pending') {
              startPolling();
            } else {
              clearPolling();
            }
          }).catch(function(err) {
            clearPolling();
            if (!silent) {
              orderPanel.innerHTML = '<div class="checkout-note">加载订单失败：' + esc(err.message) + '</div>';
            }
          });
        }

        document.querySelectorAll('.payment-method[data-provider]').forEach(function(button) {
          button.addEventListener('click', function() {
            setSelectedProvider(button.getAttribute('data-provider') || 'alipay');
          });
        });
        backProductsLink.href = withPortalToken('/portal/products');
        setSelectedProvider(selectedProvider);

        createButton.addEventListener('click', function() {
          if (!packageCode) {
            orderPanel.innerHTML = '<div class="checkout-note">缺少 package_code，请回到套餐页重新进入下单页。</div>';
            return;
          }
          setLoading(true);
          apiFetch('/portal/api/payments/orders', {
            method: 'POST',
            body: JSON.stringify({ package_code: packageCode, provider: selectedProvider })
          }).then(function(data) {
            currentOrderId = data.order && data.order.order_id ? data.order.order_id : '';
            updateSearchParams(currentOrderId);
            renderOrderState(data);
            if (data.order && data.order.status === 'pending') {
              startPolling();
            }
          }).catch(function(err) {
            orderPanel.innerHTML = '<div class="checkout-note">创建订单失败：' + esc(err.message) + '</div>';
          }).finally(function() {
            setLoading(false);
          });
        });

        simulateButton.addEventListener('click', function() {
          if (!currentOrderId) return;
          simulateButton.disabled = true;
          simulateButton.textContent = '处理中...';
          apiFetch('/portal/api/payments/orders/' + encodeURIComponent(currentOrderId) + '/simulate-paid', {
            method: 'POST'
          }).then(function(data) {
            renderOrderState(data);
            clearPolling();
          }).catch(function(err) {
            orderPanel.innerHTML = '<div class="checkout-note">模拟支付失败：' + esc(err.message) + '</div>';
          }).finally(function() {
            simulateButton.textContent = '模拟支付成功';
          });
        });

        if (currentOrderId) {
          loadOrder(currentOrderId, false);
        }
      })();
      </script>
    '''

    body_html = body_html.replace("__CHECKOUT_SUMMARY__", summary_html)
    body_html = body_html.replace("__PROMO_ITEMS__", promo_html)
    body_html = body_html.replace("__MOCK_PAYMENT_ENABLED__", "true" if mock_payment_enabled else "false")
    body_html = body_html.replace("__SELECTED_PACKAGE_NAME__", '"{}"'.format(selected_package_name_js.replace('"', '\\"')))

    sidebar_html = _sidebar([
        ("结算流程", [("summary", "订单确认"), ("payment", "支付方式"), ("status", "订单状态"), ("help", "促销与到账说明")]),
    ])
    return _layout(
        active="products",
        kicker="订阅与充值",
        title="结算与支付",
        subtitle="先把用户下单、查单、支付结果和账户到账联通起来，后续再将真实支付宝与微信通道接进同一页面。",
        sidebar_html=sidebar_html,
        body_html=body_html,
    )