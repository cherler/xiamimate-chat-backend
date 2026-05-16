from __future__ import annotations

import base64
import json
import os
from html import escape
from pathlib import Path
from typing import Any

from data_platform.chat_backend.domains.portal.service import _portal_public_base_url
from data_platform.chat_backend.domains.site_config import _get_contact_config
from data_platform.chat_backend.infra.postgres import _postgres_conn, _run_pg_dict_query
from data_platform.chat_backend.infra.settings import (
    DEFAULT_BILLING_PACKAGES,
    DEFAULT_PROMOTION_RULES,
  _resolve_promotion_rule_seed_status,
)


_BASE_CSS = """
  :root {
    --bg: #f7f8fb;
    --paper: rgba(255, 255, 255, 0.97);
    --panel: rgba(255, 255, 255, 0.94);
    --ink: #172033;
    --muted: #64748b;
    --accent: #2563eb;
    --accent-soft: rgba(37, 99, 235, 0.08);
    --accent-2: #0f766e;
    --line: rgba(23, 32, 51, 0.12);
    --shadow: 0 18px 48px rgba(15, 23, 42, 0.08);
    --sidebar-w: 228px;
    --content-w: 1220px;
  }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body {
    margin: 0;
    font-family: "IBM Plex Sans", "Helvetica Neue", "PingFang SC", sans-serif;
    color: var(--ink);
    background: linear-gradient(180deg, #ffffff 0%, var(--bg) 100%);
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
    background: rgba(255, 255, 255, 0.86);
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
    background: rgba(255, 255, 255, 0.84);
    color: var(--muted);
    text-decoration: none;
    font-size: 0.84rem;
    font-weight: 600;
  }
  .top-route-link:hover,
  .top-route-link.active {
    background: var(--accent-soft);
    color: var(--accent);
    border-color: rgba(37, 99, 235, 0.18);
  }
  .top-home-link {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 40px;
    padding: 0 16px;
    border-radius: 12px;
    border: 1px solid rgba(37, 99, 235, 0.18);
    background: var(--accent);
    color: #fff;
    text-decoration: none;
    font-size: 0.84rem;
    font-weight: 600;
  }
  .top-home-link:hover {
    background: #1d4ed8;
    border-color: #1d4ed8;
  }
  .top-action-link {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border-radius: 12px;
    border: 1px solid var(--line);
    background: rgba(255, 255, 255, 0.86);
    color: var(--ink);
    text-decoration: none;
    cursor: pointer;
    padding: 0;
  }
  .top-action-link:hover {
    background: var(--accent-soft);
    border-color: rgba(37, 99, 235, 0.18);
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
    border: 1px solid rgba(37, 99, 235, 0.16);
    background: linear-gradient(135deg, rgba(37, 99, 235, 0.08), rgba(255, 255, 255, 0.96));
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
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.94));
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
    background: #1d4ed8;
    border-color: #1d4ed8;
  }
  .offer-cta.disabled,
  .offer-cta[aria-disabled="true"] {
    background: rgba(37, 99, 235, 0.1);
    color: var(--muted);
    border: 1px solid rgba(17, 75, 95, 0.12);
    pointer-events: none;
  }
  .ghost-button,
  .payment-method {
    background: rgba(255, 255, 255, 0.88);
    color: var(--ink);
    border: 1px solid var(--line);
  }
  .ghost-button:hover,
  .payment-method:hover {
    background: var(--accent-soft);
    border-color: rgba(37, 99, 235, 0.18);
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
    color: #1d4ed8;
  }
  .cta-hint {
    color: var(--muted);
    font-size: 0.8rem;
  }
  .offer-card.featured {
    border-color: rgba(37, 99, 235, 0.24);
    box-shadow: 0 20px 42px rgba(37, 99, 235, 0.08);
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
    background: rgba(255, 255, 255, 0.9);
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
    background: rgba(255, 255, 255, 0.92);
    padding: 16px 18px;
  }
  .example-card {
    display: grid;
    gap: 12px;
  }
  .example-card.highlight {
    background: linear-gradient(180deg, rgba(37, 99, 235, 0.08), rgba(255, 255, 255, 0.94));
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
    background: linear-gradient(180deg, rgba(37, 99, 235, 0.08), rgba(255, 255, 255, 0.94));
  }
  .notice-card.service {
    background: linear-gradient(180deg, rgba(15, 118, 110, 0.1), rgba(255, 255, 255, 0.94));
  }
  .demo-media {
    border: 1px dashed rgba(17, 75, 95, 0.28);
    border-radius: 16px;
    min-height: 220px;
    background:
      linear-gradient(135deg, rgba(37, 99, 235, 0.08), rgba(255, 255, 255, 0.94)),
      repeating-linear-gradient(135deg, rgba(37, 99, 235, 0.05) 0, rgba(37, 99, 235, 0.05) 12px, transparent 12px, transparent 24px);
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
    background: rgba(37, 99, 235, 0.12);
    color: var(--accent);
  }
  .status-pill.pending {
    background: rgba(100, 116, 139, 0.12);
    color: #475569;
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
    background: rgba(255, 255, 255, 0.9);
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
    background: rgba(255, 255, 255, 0.88);
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
    background: rgba(100, 116, 139, 0.12);
    color: #475569;
  }
  .status-badge.paid {
    background: rgba(15, 118, 110, 0.12);
    color: #0f766e;
  }
  .status-badge.other {
    background: rgba(37, 99, 235, 0.1);
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
  chatbot_cache_revision = "20260423-dify-chatbot-v3"
  chatbot_base_url_json = json.dumps(chatbot_base_url)
  chatbot_embed_src_json = json.dumps(f"{chatbot_base_url}/embed.min.js?v={chatbot_cache_revision}")
  chatbot_page_src_json = json.dumps(f"{chatbot_base_url}/chatbot/{chatbot_token}?v={chatbot_cache_revision}")
  chatbot_token_json = json.dumps(chatbot_token)
  chatbot_cache_revision_json = json.dumps(chatbot_cache_revision)
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
  const chatbotCacheRevision = {chatbot_cache_revision_json};
  const passportStorageKey = `passport-${{config.token}}`;
  const chatbotStateRevisionKey = `xm_dify_chatbot_revision:${{config.token}}`;
  const chatbotEmbedUrl = {chatbot_embed_src_json};
  const chatbotPageUrl = {chatbot_page_src_json};
  let hasScheduledWarmup = false;
  let hasScheduledApiWarmup = false;
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
  const purgeDifyCacheStorage = async () => {{
   if (!('caches' in window)) {{
    return;
   }}
   try {{
    const cacheNames = await window.caches.keys();
    await Promise.all(cacheNames.map(async (cacheName) => {{
     const cache = await window.caches.open(cacheName);
     const requests = await cache.keys();
     await Promise.all(
      requests
       .filter((request) => request.url.includes('/_dify/'))
       .map((request) => cache.delete(request)),
     );
    }}));
   }} catch (error) {{
    console.debug('portal chatbot cache storage purge skipped', error);
   }}
  }};
  const resetLegacyChatbotState = () => {{
   try {{
    window.localStorage.removeItem(passportStorageKey);
    window.localStorage.removeItem('conversationIdInfo');
    window.localStorage.setItem(chatbotStateRevisionKey, chatbotCacheRevision);
   }} catch (error) {{}}
   purgeDifyCacheStorage();
  }};
  const ensureChatbotStateRevision = () => {{
   try {{
    const storedRevision = String(window.localStorage.getItem(chatbotStateRevisionKey) || '').trim();
    if (storedRevision === chatbotCacheRevision) {{
     return;
    }}
   }} catch (error) {{}}
   resetLegacyChatbotState();
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
    appendHintLink('preload', chatbotEmbedUrl, 'script');
    fetch(chatbotEmbedUrl, {{
    credentials: 'include',
    cache: 'reload',
    }}).catch((error) => {{
    console.debug('portal chatbot embed reload skipped', error);
    }});
     appendHintLink('prefetch', chatbotPageUrl, 'document');
     const response = await fetch(chatbotPageUrl, {{
      credentials: 'include',
    cache: 'reload',
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
       uniqueAssets.forEach((assetUrl, index) => {{
        appendHintLink(
         index < 6 ? 'preload' : 'prefetch',
         assetUrl,
         assetUrl.endsWith('.css') ? 'style' : 'script',
        );
      if (index < 6) {{
       fetch(assetUrl, {{
        credentials: 'include',
        cache: 'reload',
       }}).catch((error) => {{
        console.debug('portal chatbot asset reload skipped', assetUrl, error);
       }});
      }}
     }});
    }} catch (error) {{
     console.debug('portal chatbot warmup skipped', error);
    }}
   }});
  }};
      const warmupChatbotApis = (passportToken) => {{
       if (hasScheduledApiWarmup) {{
      return;
       }}
       hasScheduledApiWarmup = true;
       scheduleIdleWork(() => {{
      const headers = {{
       'X-App-Code': config.token,
      }};
      if (passportToken) {{
       headers['X-App-Passport'] = passportToken;
      }}
      [
       `${{config.baseUrl}}/api/site`,
       `${{config.baseUrl}}/api/meta`,
       `${{config.baseUrl}}/api/parameters`,
       `${{config.baseUrl}}/api/webapp/access-mode`,
       `${{config.baseUrl}}/api/login/status`,
      ].forEach((url) => {{
       fetch(url, {{
        headers,
        credentials: 'include',
        cache: 'force-cache',
       }}).catch((error) => {{
        console.debug('portal chatbot api warmup skipped', url, error);
       }});
      }});
       }});
      }};
  const loadEmbedScript = () => {{
   window.difyChatbotConfig = config;
   if (document.getElementById(config.token)) {{
    return;
   }}
       appendHintLink('preload', chatbotEmbedUrl, 'script');
   const script = document.createElement('script');
       script.src = chatbotEmbedUrl;
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
      warmupChatbotApis(existingPassport);
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
     warmupChatbotApis(payload.access_token);
    }}
   }} catch (error) {{
    console.error('portal chatbot passport bootstrap failed', error);
   }} finally {{
    loadEmbedScript();
   }}
  }};
  ensureChatbotStateRevision();
  warmupChatbot();
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


def _fallback_catalog_promotion_rules() -> list[dict[str, Any]]:
    return [
        rule
        for rule in DEFAULT_PROMOTION_RULES
        if _resolve_promotion_rule_seed_status(rule) == "active"
    ]


def _load_catalog_promotion_rules() -> list[dict[str, Any]]:
    try:
        with _postgres_conn() as conn:
            return _run_pg_dict_query(
                conn,
                """
                SELECT rule_code, rule_name, rule_type, status, target_product_type,
                       target_package_codes, benefit_type, benefit_value, criteria_json,
                       meta_json, display_order, start_at, end_at, created_at, updated_at
                FROM app.promotion_rule
                WHERE status = 'active'
                  AND (start_at IS NULL OR start_at <= NOW())
                  AND (end_at IS NULL OR end_at >= NOW())
                ORDER BY display_order ASC, rule_code ASC
                """,
                [],
            )
    except Exception:
        return _fallback_catalog_promotion_rules()


def _split_catalog() -> tuple[list[dict], list[dict], dict, dict, list[dict]]:
    promotion_rules = _load_catalog_promotion_rules()
    monthly_packages = sorted(
        [pkg for pkg in DEFAULT_BILLING_PACKAGES if pkg.get("product_type") == "monthly_subscription"],
        key=lambda item: int(item.get("display_order") or 0),
    )
    recharge_packages = sorted(
        [pkg for pkg in DEFAULT_BILLING_PACKAGES if pkg.get("product_type") == "credit_pack"],
        key=lambda item: int(item.get("display_order") or 0),
    )
    signup_rule = next((rule for rule in promotion_rules if rule.get("rule_code") == "signup_bonus_500"), {})
    first_discount_rule = next((rule for rule in promotion_rules if rule.get("rule_code") == "first_subscription_monthly_90_off"), {})
    cumulative_rules = sorted(
      [rule for rule in promotion_rules if rule.get("rule_type") == "recharge_bonus_cumulative"],
        key=lambda item: int((item.get("criteria_json") or {}).get("threshold_paid_amount_cents") or 0),
    )
    single_bonus_by_package: dict[str, dict] = {}
    for rule in promotion_rules:
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
  <title>虾米选品 - {escape(title)}</title>
  <style>{_BASE_CSS}</style>
</head>
<body>
<div class="portal-shell">
  <nav class="sidebar">
    <div class="brand">🦐 虾米选品<span class="brand-subtitle">公开产品页与使用指南</span></div>
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
    first_discount_text = escape(str((first_discount_rule.get("meta_json") or {}).get("display_text") or first_discount_rule.get("rule_name") or ""))

    monthly_cards = []
    for package in monthly_packages:
        meta = package.get("meta_json") or {}
        display_name = meta.get("display_name") or package.get("package_name") or package.get("package_code")
        renewal_label = meta.get("renewal_price_label") or _cny(int(package.get("price_cents") or 0))
        package_code = escape(str(package.get("package_code") or ""))
        first_discount_bullet = ""
        if first_discount_rule:
            first_discount_bullet = f'<div class="bullet-item">当前活动：{first_discount_text}</div>'
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
                <div class="bullet-item">续费说明：当前按单月购买，不自动续费；如需继续使用，到期后再手动续购</div>
                {first_discount_bullet}
              </div>
              <div class="offer-actions">
                <a class="offer-cta" data-checkout-link="1" data-package-code="{package_code}" data-product-type="monthly_subscription" href="/portal/checkout?package_code={package_code}">立即下单</a>
                <span class="cta-hint" data-cta-hint="{package_code}">登录后进入受保护结算页，当前阶段按单月购买，不自动续费。</span>
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
                  <a class="offer-cta" data-checkout-link="1" data-package-code="{package_code}" data-product-type="recharge" href="/portal/checkout?package_code={package_code}">立即下单</a>
                  <span class="cta-hint" data-cta-hint="{package_code}">下单后可在同页查看支付状态与到账结果。</span>
              </div>
            </div>
            '''
        )

    first_discount_card = ""
    if first_discount_rule:
        first_discount_card = f'''
      <div class="offer-card">
        <div class="offer-top">
          <div>
            <div class="offer-name">首次订阅优惠</div>
            <div class="offer-tagline">适合首次尝试月包的用户。</div>
          </div>
          <div class="offer-badge">首单转化</div>
        </div>
        <div class="offer-price"><div class="offer-price-main">限时活动</div></div>
        <div class="bullet-list">
          <div class="bullet-item">活动说明：{first_discount_text}</div>
          <div class="bullet-item">适用范围：仅首次订阅月包时可用。</div>
        </div>
      </div>
        '''

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
      {first_discount_card}
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
    ).replace("</body>", '''
<script>
(function() {
  function readStoredToken() {
    try {
      var stored = localStorage.getItem('token');
      if (!stored || stored === '""') return '';
      if (stored.charAt(0) === '"' && stored.charAt(stored.length - 1) === '"') {
        stored = stored.slice(1, -1);
      }
      return stored || '';
    } catch (error) {
      return '';
    }
  }

  function authHeaders() {
    var headers = {};
    var token = readStoredToken();
    if (token) {
      headers.Authorization = 'Bearer ' + token;
    }
    return headers;
  }

  function withPortalToken(path) {
    var token = readStoredToken();
    if (!token || !path || /[?&]t=/.test(path)) {
      return path;
    }
    return path + (path.indexOf('?') === -1 ? '?' : '&') + 't=' + encodeURIComponent(token);
  }

  function findActiveMonthlySubscription(subscriptions) {
    var rows = Array.isArray(subscriptions) ? subscriptions.slice() : [];
    var now = Date.now();
    rows = rows.filter(function(sub) {
      if (!sub || String(sub.status || '').toLowerCase() !== 'active') {
        return false;
      }
      if (!sub.current_period_end) {
        return true;
      }
      var endTime = new Date(sub.current_period_end).getTime();
      return !isNaN(endTime) && endTime > now;
    });
    if (!rows.length) {
      return null;
    }
    rows.sort(function(left, right) {
      var leftTime = left && left.current_period_end ? new Date(left.current_period_end).getTime() : 0;
      var rightTime = right && right.current_period_end ? new Date(right.current_period_end).getTime() : 0;
      return rightTime - leftTime;
    });
    return rows[0] || null;
  }

  function setCheckoutLinkState(link, text, hint, disabled) {
    if (!link) {
      return;
    }
    var packageCode = link.getAttribute('data-package-code') || '';
    var hintEl = packageCode ? document.querySelector('[data-cta-hint="' + packageCode + '"]') : null;
    link.textContent = text;
    if (hintEl && hint) {
      hintEl.textContent = hint;
    }
    if (disabled) {
      link.setAttribute('aria-disabled', 'true');
      link.classList.add('disabled');
      link.removeAttribute('href');
    } else {
      link.setAttribute('href', withPortalToken('/portal/checkout?package_code=' + encodeURIComponent(packageCode)));
      link.removeAttribute('aria-disabled');
      link.classList.remove('disabled');
    }
  }

  function applyProductsCheckoutState(account) {
    var activeSubscription = findActiveMonthlySubscription((account || {}).subscriptions || []);
    document.querySelectorAll('[data-checkout-link="1"]').forEach(function(link) {
      var packageCode = link.getAttribute('data-package-code') || '';
      var productType = link.getAttribute('data-product-type') || '';
      if (productType !== 'monthly_subscription') {
        setCheckoutLinkState(link, '立即下单', '下单后可在同页查看支付状态与到账结果。', false);
        return;
      }
      if (!activeSubscription) {
        setCheckoutLinkState(link, '立即下单', '登录后进入受保护结算页，当前阶段按单月购买，不自动续费。', false);
        return;
      }
      if (String(activeSubscription.package_code || '') === packageCode) {
        setCheckoutLinkState(link, '当前订阅', '当前月包已生效；本阶段不支持重复购买同一套餐。', true);
        return;
      }
      setCheckoutLinkState(link, '套餐切换待上线', '当前账号已有生效中的月包；升降级切换后续再开放。', true);
    });
  }

  fetch(withPortalToken('/portal/api/account'), {
    method: 'GET',
    credentials: 'same-origin',
    cache: 'no-store',
    headers: authHeaders(),
  }).then(function(resp) {
    return resp.json().catch(function() { return {}; }).then(function(body) {
      if (!resp.ok || !body || body.success !== true) {
        throw new Error('not_logged_in');
      }
      return body.data || {};
    });
  }).then(function(account) {
    applyProductsCheckoutState(account || {});
  }).catch(function() {
    applyProductsCheckoutState(null);
  });
})();
</script>
</body>''')


def render_portal_guide_html() -> str:
    body_html = '''
      <section id="start" class="section-block card">
        <h2>新手上手路径</h2>
        <div class="card-note">第一次使用时，不建议一上来就跑很大的任务。先按下面这条路径走一遍，通常 5 分钟内就能完成第一次有效体验。</div>
        <div class="guide-list">
          <div class="guide-item"><div class="guide-title">1. 先登录，再确认账户可用</div><div class="guide-desc">从 Open WebUI 首页进入产品，首次登录后系统会自动初始化账户。建议先用 /me 或 /points 看一下当前套餐、积分余额和是否已经完成邮箱验证。</div></div>
          <div class="guide-item"><div class="guide-title">2. 有完整任务时优先用 /report</div><div class="guide-desc">如果你已经知道目标市场、类目和问题，直接用 /report 最省事。它适合输出一份相对完整的分析结果，并且可以按 quick、standard、deep、research 选择报告深度；旧命令 /workflow 当前仍兼容保留。</div></div>
          <div class="guide-item"><div class="guide-title">3. 不知道怎么提问时，先查提示词知识库</div><div class="guide-desc">如果你还不知道该怎么开口，直接输入“新手卖家提示词”“决策层提示词”或“客服常用提示词”这类短句。系统会先检索提示词知识库，返回可直接复制的示例和对应使用说明。</div></div>
          <div class="guide-item"><div class="guide-title">4. 只是验证一个点时用 /tool 或 /web</div><div class="guide-desc">如果你只想先验证趋势、规则或某个市场变化，不要急着跑完整报告。先用 /tool 做局部分析，或者用 /web 查最新外部信息，会更稳也更省积分。</div></div>
          <div class="guide-item"><div class="guide-title">5. 看结果时先看结论，再看证据</div><div class="guide-desc">优先关注结论、关键指标、风险提示；如果结果和预期不一致，再回看工具返回、知识库引用和输入条件，判断是不是问题范围太大或条件不够明确。</div></div>
          <div class="guide-item"><div class="guide-title">6. 用完回到账户页核对消费</div><div class="guide-desc">每次使用后，都可以回到账户管理页看消费记录、扣减来源和使用趋势。系统会优先扣减月包积分，月包不足时再扣充值包积分。</div></div>
        </div>
      </section>
      <section id="commands" class="section-block card">
        <h2>常用命令示例</h2>
        <div class="card-note">下面这些命令可以直接复制后再替换商品、市场和时间范围。对于新手来说，先照着示例改，比从零组织问题更容易成功。</div>
        <div class="example-grid">
          <div class="example-card highlight">
            <div class="example-kicker">报告编排</div>
            <h3 class="example-title">/report：拿一份完整的选品分析报告</h3>
            <p class="example-desc">适合已经有目标商品或类目，希望系统自动调工具、拉数据、形成结论，并按报告深度选择 quick、standard、deep、research 的场景。</p>
            <div class="command-block">/report standard 帮我调研一下 portable blender 在 Amazon 美国站近 90 天的需求、竞争和进入机会，重点看价格带、销量趋势和风险点</div>
            <div class="example-meta">
              <div class="example-meta-item">适合：第一次做完整市场判断、要拿结构化结论时。</div>
              <div class="example-meta-item">提示：问题里尽量带上市场、类目、时间范围和你最关心的输出；旧入口 /workflow 当前兼容保留，默认可理解为标准完整分析。</div>
            </div>
          </div>
          <div class="example-card">
            <div class="example-kicker">局部验证</div>
            <h3 class="example-title">/tool：先查一个点，再决定要不要跑大任务</h3>
            <p class="example-desc">适合你已经有一个猜想，只想先验证趋势、竞争强度或类目情况。</p>
            <div class="command-block">/tool 帮我先判断 pet grooming vacuum 在 TikTok 美国市场最近是否明显升温，并告诉我下一步最值得调用哪些工具验证</div>
            <div class="example-meta">
              <div class="example-meta-item">适合：快速试水、缩小问题范围、减少无效消耗。</div>
              <div class="example-meta-item">提示：如果只是查一个指标或一个判断，不要一开始就跑完整报告。</div>
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
            <div class="example-kicker">提示词知识库</div>
            <h3 class="example-title">先查提示词：不会提问时先拿一批可复制示例</h3>
            <p class="example-desc">适合你刚打开产品，还不知道应该先用 /report、/tool 还是 /web，或者想先看系统已经整理好的典型问法。</p>
            <div class="command-block">新手卖家提示词</div>
            <div class="example-meta">
              <div class="example-meta-item">适合：刚上手、不知道怎么组织问题、想先找可直接复制命令的时候。</div>
              <div class="example-meta-item">提示：也可以直接输入“决策层提示词”“客服常用提示词”，系统会优先检索知识库并返回示例和使用指南。</div>
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
          <div class="notice-card accent"><h3 class="notice-title">我有完整问题，想一次拿到结论</h3><p class="notice-desc">优先用 /report。它更适合做“某商品在某市场是否值得做”这类完整分析；如果你还习惯旧命令，/workflow 当前仍可作为兼容入口使用。</p></div>
          <div class="notice-card"><h3 class="notice-title">我还不知道怎么提问</h3><p class="notice-desc">先直接输入“新手卖家提示词”“决策层提示词”这类短句。系统会先查提示词知识库，给你可直接复制的示例和怎么用的说明。</p></div>
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
            <h3 class="demo-title">演示 1：如何发起一次 /report</h3>
            <p class="demo-desc">建议后续放一张或一段演示“输入命令 -> 等待执行 -> 查看结论”的 GIF 或截图。</p>
            <div class="demo-media" data-demo-slot="workflow">
              <div>
                <div class="demo-placeholder-title">预留 GIF / 截图区</div>
                <p class="demo-placeholder-note">后续可替换成实际使用虾米选品智能体的演示 GIF；如果暂时没有 GIF，也可以先放一张实操截图。</p>
              </div>
            </div>
            <p class="demo-caption">建议内容：输入 /report 命令、等待进度、查看最终结果；如需说明兼容关系，可补一张 /workflow 仍可用的过渡提示图。</p>
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


def render_portal_invite_html() -> str:
    openwebui_home_url = escape(_portal_public_base_url())
    body_html = '''
      <section id="invite" class="section-block card">
        <h2>邀请注册</h2>
        <div class="card-note" id="invite-card-note">通过专属邀请链接进入后，完成注册或登录，系统会自动绑定邀请关系。</div>
        <div class="form-grid">
          <div class="field-grid">
            <label class="field-group">
              <span class="field-label">邀请码</span>
              <input id="invite-code-input" class="text-field" type="text" maxlength="32" placeholder="正在从邀请链接读取邀请码" />
              <span class="field-hint" id="invite-code-hint">邀请码会自动从链接中读取；如果你是手动打开页面，也可以在这里直接输入。</span>
            </label>
          </div>
          <div id="invite-preview-card" class="checkout-note">正在校验邀请码，请稍候...</div>
          <div class="checkout-actions">
            <button type="button" class="offer-cta" id="invite-continue-button">保存邀请码并去注册/登录</button>
            <a class="ghost-button" id="invite-secondary-link" href="'''+ openwebui_home_url + '''">返回首页</a>
          </div>
          <div id="invite-status" class="status-banner"></div>
        </div>
      </section>
      <section id="product" class="section-block card">
        <h2>你将注册的是什么产品</h2>
        <div class="card-note">虾米选品（XiaMimate）是面向跨境电商卖家的选品智能体，融合 Amazon\TikTok Shop\Temu 知识库、Keepa 商品数据、Google Trends 趋势信号、实时联网查询、商品预测与主题分析能力，帮助用户快速完成选品分析与决策。</div>
        <div class="tip-banner">它不是泛聊天工具，而是一套围绕跨境电商选品、测品和市场调研的分析工作台，重点帮助你判断“这个方向值不值得做、风险在哪里、下一步该怎么继续”。</div>
        <div style="height:18px"></div>
        <div class="mini-kpi-row">
          <div class="mini-kpi"><div class="mini-kpi-value">市场扫描</div><div class="mini-kpi-label">从模糊商品词拆出可分析候选池</div></div>
          <div class="mini-kpi"><div class="mini-kpi-value">趋势验证</div><div class="mini-kpi-label">结合数据、趋势和外部信号交叉判断</div></div>
          <div class="mini-kpi"><div class="mini-kpi-value">选品报告</div><div class="mini-kpi-label">输出结论、依据、风险和下一步动作</div></div>
        </div>
        <div style="height:18px"></div>
        <div class="notice-grid">
          <div class="notice-card accent"><h3 class="notice-title">多平台知识整合</h3><p class="notice-desc">不只是 Amazon，还覆盖 TikTok Shop、Temu 的平台规则、类目特点、履约与合规知识。</p></div>
          <div class="notice-card"><h3 class="notice-title">实时外部信号验证</h3><p class="notice-desc">可以联网补充政策变化、社媒热点、搜索趋势、节庆季节性等外部信息，不只看静态数据库。</p></div>
          <div class="notice-card"><h3 class="notice-title">候选池解析与机会发现</h3><p class="notice-desc">能先帮用户把模糊商品词拆成可分析的候选池，再筛出值得继续看的方向。</p></div>
          <div class="notice-card"><h3 class="notice-title">竞品与价格带分析</h3><p class="notice-desc">支持头部商品特征、价格区间、销量表现、评论规模、竞争密度的综合判断。</p></div>
          <div class="notice-card"><h3 class="notice-title">风险识别能力</h3><p class="notice-desc">识别合规风险、侵权风险、季节性风险、履约风险和过热竞争风险。</p></div>
          <div class="notice-card"><h3 class="notice-title">主题分析分层报告能力</h3><p class="notice-desc">支持 quick / standard / deep 不同深度的分析路径，满足“先快速判断，再深入研究”的工作流。</p></div>
        </div>
        <div style="height:18px"></div>
        <h2 style="margin-top:0">核心能力链路</h2>
        <div class="card-note">它不是单点工具，而是把一次完整分析拆成更容易落地的四个环节，让你从“想到一个方向”走到“知道下一步该怎么做”。</div>
        <div class="timeline-list">
          <div class="timeline-item"><div class="timeline-title">1. 智能问答：先把问题问清楚</div><div class="timeline-desc">适合先澄清某个市场、某个类目、某个商品方向值不值得继续看，避免一开始就跑大任务。</div></div>
          <div class="timeline-item"><div class="timeline-title">2. /report：把目标变成完整报告</div><div class="timeline-desc">当你已经有明确目标时，直接输出趋势、竞争、风险和进入建议，并可按 quick、standard、deep、research 选择报告深度；/workflow 当前仍作为兼容入口保留。</div></div>
          <div class="timeline-item"><div class="timeline-title">3. 提示词知识库：先拿可直接复制的问法</div><div class="timeline-desc">如果你还不知道应该怎么提问，可以直接输入“新手卖家提示词”“决策层提示词”等短句，先拿一批系统整理好的示例和使用方式。</div></div>
          <div class="timeline-item"><div class="timeline-title">4. 知识库：补规则和方法依据</div><div class="timeline-desc">需要看平台规则、SOP、产品说明和标准答复时，不再到处翻资料，直接回到统一入口检索。</div></div>
          <div class="timeline-item"><div class="timeline-title">5. 账户页：回看成本和奖励结果</div><div class="timeline-desc">分析完成后，可以回到账户页看积分消耗、账本变化、邀请奖励和整体使用趋势。</div></div>
        </div>
        <div style="height:18px"></div>
        <div class="offer-grid">
          <div class="offer-card featured">
            <div class="offer-top">
              <div>
                <div class="offer-name">智能问答</div>
                <div class="offer-tagline">适合先澄清问题、判断方向、快速问规则。</div>
              </div>
              <div class="offer-badge">快速开始</div>
            </div>
            <div class="bullet-list">
              <div class="bullet-item">先问某个市场或品类值不值得进入</div>
              <div class="bullet-item">先确认平台规则、常见风险和切入思路</div>
            </div>
          </div>
          <div class="offer-card">
            <div class="offer-top">
              <div>
                <div class="offer-name">/report 报告编排</div>
                <div class="offer-tagline">适合已经有目标商品或市场时，直接拿完整分析结果，并按报告深度选择输出。</div>
              </div>
              <div class="offer-badge">完整任务</div>
            </div>
            <div class="bullet-list">
              <div class="bullet-item">输出趋势、竞争、风险和进入建议</div>
              <div class="bullet-item">适合做一份结构化选品分析；/workflow 当前作为兼容入口保留</div>
            </div>
          </div>
          <div class="offer-card">
            <div class="offer-top">
              <div>
                <div class="offer-name">知识库与账户页</div>
                <div class="offer-tagline">适合看规则说明、套餐积分和消费记录，方便复盘成本。</div>
              </div>
              <div class="offer-badge">长期使用</div>
            </div>
            <div class="bullet-list">
              <div class="bullet-item">查看产品规则、SOP 和常见问题</div>
              <div class="bullet-item">直接问“新手卖家提示词”“客服常用提示词”拿可复制示例</div>
              <div class="bullet-item">查看余额、账本、趋势和奖励到账结果</div>
            </div>
          </div>
        </div>
      </section>
    '''

    sidebar_html = _sidebar([
        ("邀请页面", [("invite", "邀请注册"), ("product", "产品介绍")]),
    ])

    page = _layout(
        active="invite",
        kicker="邀请注册",
        title="通过邀请链接开始使用",
        subtitle="先确认邀请码有效，再进入产品；如果你还没注册，完成注册或登录后系统会自动绑定邀请关系。",
        sidebar_html=sidebar_html,
        body_html=body_html,
    )
    script = '''
<script>
(function() {
  var params = new URLSearchParams(location.search);
  var inviteCodeFromUrl = (params.get("code") || params.get("invite_code") || "").trim().toUpperCase();
  var input = document.getElementById("invite-code-input");
  var previewCard = document.getElementById("invite-preview-card");
  var continueButton = document.getElementById("invite-continue-button");
  var secondaryLink = document.getElementById("invite-secondary-link");
  var statusEl = document.getElementById("invite-status");
  var inviteCardNote = document.getElementById("invite-card-note");
  var inviteCodeHint = document.getElementById("invite-code-hint");
  var pendingInviteCodeKey = "xm_pending_invite_code";
  var pendingInvitePreviewKey = "xm_pending_invite_preview";
  var invitePreview = null;
  var loggedIn = false;

  function readStoredToken() {
    try {
      var stored = localStorage.getItem('token');
      if (!stored || stored === '""') return '';
      if (stored.charAt(0) === '"' && stored.charAt(stored.length - 1) === '"') {
        stored = stored.slice(1, -1);
      }
      return stored || '';
    } catch (error) {
      return '';
    }
  }

  function authHeaders() {
    var headers = {};
    var token = readStoredToken();
    if (token) {
      headers.Authorization = 'Bearer ' + token;
    }
    return headers;
  }

  function withPortalToken(path) {
    var token = readStoredToken();
    if (!token || !path || /[?&]t=/.test(path)) {
      return path;
    }
    return path + (path.indexOf('?') === -1 ? '?' : '&') + 't=' + encodeURIComponent(token);
  }

  function setStatus(text, state) {
    if (!statusEl) return;
    statusEl.textContent = text || "";
    if (!text) {
      statusEl.removeAttribute("data-state");
      return;
    }
    statusEl.setAttribute("data-state", state || "info");
  }

  function renderPreview(preview) {
    if (!previewCard) return;
    if (!preview) {
      previewCard.innerHTML = '未找到可用的邀请码，请检查链接是否完整。';
      return;
    }
    invitePreview = preview;
    previewCard.innerHTML = '' +
      '<div><strong>邀请人：</strong>' + (preview.inviter_display_name || preview.inviter_user_id || '-') + '</div>' +
      '<div><strong>邀请码：</strong>' + (preview.invite_code || '-') + '</div>' +
      '<div><strong>注册赠送：</strong>' + String(preview.signup_reward_points || 0) + ' 积分</div>' +
      '<div><strong>绑定奖励：</strong>' + String(preview.bind_reward_points || 0) + ' 积分</div>';
  }

  function applyLoggedInMode(account) {
    loggedIn = true;
    if (input) {
      input.disabled = true;
    }
    if (inviteCardNote) {
      inviteCardNote.textContent = '当前浏览器已登录。这个专属邀请链接主要用于邀请新用户注册；如果你刚完成注册，系统会自动处理邀请绑定。';
    }
    if (inviteCodeHint) {
      inviteCodeHint.textContent = '已登录状态下不需要再手动输入邀请码；如需查看绑定结果，请前往账户管理页。';
    }
    if (continueButton) {
      continueButton.textContent = '前往账户管理';
      continueButton.disabled = false;
    }
    if (secondaryLink) {
      secondaryLink.textContent = '返回首页';
      secondaryLink.href = ''' + json.dumps(_portal_public_base_url()) + ''';
    }
    if (account && account.identity_verification && account.identity_verification.invited_by) {
      var invitedBy = account.identity_verification.invited_by;
      setStatus('当前账号已绑定邀请人 ' + (invitedBy.inviter_display_name || invitedBy.inviter_user_id || '-') + '，可以直接去账户页查看结果。', 'success');
      return;
    }
    if (account && account.identity_verification && account.identity_verification.can_bind_invite_code === true) {
      setStatus('当前账号已登录。如果你刚注册完成，系统会自动尝试绑定邀请码；可直接去账户页确认结果。', 'info');
      return;
    }
    setStatus('当前账号已登录。该邀请链接更适合发送给尚未注册的新用户使用。', 'info');
  }

  function detectLoggedInAccount() {
    return fetch(withPortalToken('/portal/api/account'), {
      method: 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: authHeaders()
    }).then(function(resp) {
      return resp.json().catch(function() { return {}; }).then(function(body) {
        if (!resp.ok || !body || body.success !== true) {
          throw new Error('not_logged_in');
        }
        return body.data || {};
      });
    });
  }

  function loadPreview(inviteCode) {
    if (!inviteCode) {
      renderPreview(null);
      if (continueButton && !loggedIn) continueButton.disabled = true;
      setStatus("邀请链接里没有邀请码，请确认链接参数。", "error");
      return;
    }
    if (continueButton && !loggedIn) continueButton.disabled = true;
    setStatus("正在校验邀请码...", "info");
    fetch('/portal/api/public/referral/preview?invite_code=' + encodeURIComponent(inviteCode), {
      method: 'GET',
      credentials: 'same-origin',
      cache: 'no-store'
    }).then(function(resp) {
      return resp.json().catch(function() { return {}; }).then(function(body) {
        if (!resp.ok || !body || body.success !== true) {
          throw new Error(body.detail || body.message || '邀请码校验失败');
        }
        return body.data || {};
      });
    }).then(function(data) {
      if (input) input.value = inviteCode;
      renderPreview(data);
      localStorage.setItem(pendingInvitePreviewKey, JSON.stringify(data));
      if (continueButton && !loggedIn) continueButton.disabled = false;
      if (!loggedIn) {
        setStatus("邀请码校验通过。点击按钮后，系统会记住这次邀请关系并引导你去注册或登录。", "success");
      }
    }).catch(function(error) {
      renderPreview(null);
      if (continueButton && !loggedIn) continueButton.disabled = true;
      setStatus(error.message || '邀请码校验失败', 'error');
    });
  }

  if (input) {
    input.value = inviteCodeFromUrl;
    input.addEventListener('change', function() {
      loadPreview((input.value || '').trim().toUpperCase());
    });
  }

  continueButton.addEventListener('click', function() {
    if (loggedIn) {
      window.location.href = withPortalToken('/portal/account');
      return;
    }
    var inviteCode = ((input && input.value) || inviteCodeFromUrl || '').trim().toUpperCase();
    if (!inviteCode) {
      setStatus('请先输入有效邀请码。', 'error');
      return;
    }
    localStorage.setItem(pendingInviteCodeKey, inviteCode);
    setStatus('邀请码已保存。完成注册或登录后，系统会自动绑定邀请关系。', 'success');
    window.setTimeout(function() {
      window.location.href = ''' + json.dumps(_portal_public_base_url()) + ''';
    }, 250);
  });

  detectLoggedInAccount().then(function(account) {
    applyLoggedInMode(account || {});
    loadPreview(inviteCodeFromUrl);
  }).catch(function() {
    loadPreview(inviteCodeFromUrl);
  });
})();
</script>'''
    return page.replace("</body>", script + "</body>")


def render_portal_password_reset_html() -> str:
    openwebui_home_url = escape(_portal_public_base_url())
    body_html = f'''
      <section id="request" class="section-block card">
        <h2>第一步：发送验证邮件</h2>
        <div class="form-grid">
          <div class="field-grid">
            <label class="field-group">
              <span class="field-label">注册邮箱</span>
              <input id="password-reset-email" class="text-field" type="email" autocomplete="email" placeholder="请输入登录邮箱" />
              <span class="field-hint">如果该邮箱对应 Open WebUI 账户，系统会发送用于找回密码的验证邮件。</span>
            </label>
          </div>
          <div class="checkout-actions">
            <button type="button" class="offer-cta" id="password-reset-request-button">发送验证邮件</button>
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
        ("密码找回", [("request", "发送邮件"), ("confirm", "设置新密码"), ("support", "常见说明")]),
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
      setStatus(requestStatus, "正在发送验证邮件，请稍候...", "info");
      try {
        await postJson("/portal/api/public/password-reset/request", {email: email});
        setStatus(requestStatus, "验证邮件已发送，请去邮箱查看找回密码验证码后继续下一步。", "success");
      } catch (error) {
        setStatus(requestStatus, error.message || "发送验证邮件失败，请稍后重试。", "error");
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


def render_portal_email_verification_result_html(
    *,
    success: bool,
    title: str,
    message: str,
    email: str | None = None,
) -> str:
    openwebui_home_url = escape(_portal_public_base_url())
    account_url = "/portal/account"
    state = "success" if success else "error"
    detail_items = []
    if email:
        detail_items.append(
            f'<div class="guide-item"><div class="guide-title">验证邮箱</div><div class="guide-desc">{escape(email)}</div></div>'
        )
    detail_items.append(
        '<div class="guide-item"><div class="guide-title">下一步</div>'
        '<div class="guide-desc">返回账户管理页查看邮箱验证状态和新用户权益到账情况。</div></div>'
    )
    body_html = f'''
      <section id="result" class="section-block card">
        <h2>{escape(title)}</h2>
        <div class="status-banner" data-state="{state}">{escape(message)}</div>
        <div class="guide-list" style="margin-top:18px;">{''.join(detail_items)}</div>
        <div class="checkout-actions" style="margin-top:18px;">
          <a class="offer-cta" href="{account_url}">打开账户管理</a>
          <a class="ghost-button" href="{openwebui_home_url}">回到 Open WebUI</a>
        </div>
      </section>
    '''
    sidebar_html = _sidebar([
        ("邮箱验证", [("result", "验证结果")]),
    ])
    return _layout(
        active="account",
        kicker="账户验证",
        title="邮箱验证结果",
        subtitle="用于确认注册邮箱并激活账户权益。",
        sidebar_html=sidebar_html,
        body_html=body_html,
    )


def render_portal_checkout_html(
    *,
    selected_package: dict[str, Any] | None = None,
    pricing_preview: dict[str, Any] | None = None,
    mock_payment_enabled: bool = False,
  subscription_purchase_guard: dict[str, Any] | None = None,
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
    purchase_guard_button_label_js = escape(str((subscription_purchase_guard or {}).get("button_label") or "创建支付订单"))
    purchase_guard_message_js = escape(str((subscription_purchase_guard or {}).get("message") or ""))

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
        var subscriptionPurchaseBlocked = __SUBSCRIPTION_PURCHASE_BLOCKED__;
        var purchaseGuardButtonLabel = __SUBSCRIPTION_PURCHASE_BLOCK_LABEL__;
        var purchaseGuardMessage = __SUBSCRIPTION_PURCHASE_BLOCK_MESSAGE__;
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
          if (subscriptionPurchaseBlocked) {
            createButton.disabled = true;
            createButton.textContent = purchaseGuardButtonLabel || '当前不可下单';
            return;
          }
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
        if (subscriptionPurchaseBlocked) {
          noteEl.textContent = purchaseGuardMessage || '当前月包暂不可重复购买。';
          createButton.disabled = true;
          createButton.textContent = purchaseGuardButtonLabel || '当前不可下单';
          simulateButton.style.display = 'none';
          orderPanel.innerHTML = '<div class="checkout-note">' + esc(purchaseGuardMessage || '当前月包暂不可重复购买。') + '</div>';
        }

        createButton.addEventListener('click', function() {
          if (subscriptionPurchaseBlocked) {
            orderPanel.innerHTML = '<div class="checkout-note">' + esc(purchaseGuardMessage || '当前月包暂不可重复购买。') + '</div>';
            return;
          }
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
    body_html = body_html.replace("__SUBSCRIPTION_PURCHASE_BLOCKED__", "true" if subscription_purchase_guard else "false")
    body_html = body_html.replace("__SUBSCRIPTION_PURCHASE_BLOCK_LABEL__", '"{}"'.format(purchase_guard_button_label_js.replace('"', '\\"')))
    body_html = body_html.replace("__SUBSCRIPTION_PURCHASE_BLOCK_MESSAGE__", '"{}"'.format(purchase_guard_message_js.replace('"', '\\"')))
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