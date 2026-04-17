from __future__ import annotations

import base64
from html import escape
from pathlib import Path
from typing import Any

from data_platform.chat_backend.domains.portal.service import _portal_base_url
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
  .top-action-link.mail-link {
    color: var(--accent);
  }
  .top-action-link.wechat-link {
    color: #0f766e;
  }
  .top-action-link.feedback-link {
    color: var(--accent-2);
  }
  .top-action-link svg {
    width: 19px;
    height: 19px;
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

_PORTAL_CONTACT_ACTIONS_HTML = """
<a class="top-action-link mail-link" href="mailto:xiamijun88@qq.com" aria-label="邮件联系" title="邮件联系">
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M3.75 6.75h16.5v10.5H3.75z" />
    <path d="m4.5 7.5 7.5 6 7.5-6" />
  </svg>
</a>
<button type="button" class="top-action-link wechat-link" id="wechat-contact-trigger" aria-label="微信联系" title="微信联系">
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M9.2 5.5c-3.5 0-6.2 2.2-6.2 5.1 0 1.6.8 3 2.2 4l-.6 2.4 2.6-1.3c.6.1 1.3.2 2 .2 3.5 0 6.2-2.2 6.2-5.1S12.7 5.5 9.2 5.5Z" />
    <path d="M15.5 10.2c3 0 5.5 1.9 5.5 4.5 0 1.3-.7 2.5-1.8 3.3l.5 2-2.2-1.1c-.6.1-1.2.2-1.9.2-3 0-5.5-1.9-5.5-4.5s2.5-4.4 5.4-4.4Z" />
    <circle cx="7.2" cy="10.5" r=".8" fill="currentColor" stroke="none" />
    <circle cx="11.2" cy="10.5" r=".8" fill="currentColor" stroke="none" />
    <circle cx="13.8" cy="14.6" r=".8" fill="currentColor" stroke="none" />
    <circle cx="17.2" cy="14.6" r=".8" fill="currentColor" stroke="none" />
  </svg>
</button>
<a class="top-action-link feedback-link" href="https://my.feishu.cn/share/base/form/shrcnQVnRPvEuOGjz9ojf05tD1d" target="_blank" rel="noreferrer" aria-label="意见反馈" title="意见反馈">
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M12 3.75 4.75 8v8L12 20.25 19.25 16V8L12 3.75Z" />
    <path d="M12 7.75v5.25" />
    <circle cx="12" cy="15.8" r=".9" fill="currentColor" stroke="none" />
  </svg>
</a>
"""

_PORTAL_CHATBOT_SNIPPET = """
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
"""


def _wechat_qr_data_url() -> str:
  qr_path = Path(__file__).resolve().parents[2] / "微信二维码.jpg"
  if not qr_path.exists():
    return ""
  encoded = base64.b64encode(qr_path.read_bytes()).decode("ascii")
  return f"data:image/jpeg;base64,{encoded}"


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
    openwebui_home_url = escape(_portal_base_url())
    wechat_qr_data_url = _wechat_qr_data_url()
    wechat_qr_html = (
        f'<div class="wechat-qr-wrap"><img class="wechat-qr-image" src="{wechat_qr_data_url}" alt="微信二维码" /></div>'
        if wechat_qr_data_url
        else '<div class="contact-modal-note">当前未找到微信二维码图片，先使用下方微信号添加。</div>'
    )
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
            {_PORTAL_CONTACT_ACTIONS_HTML}
          </div>
        </div>
      </div>
    </div>
    <div class="main">
      <div class="main-stack">{body_html}</div>
    </div>
  </div>
</div>
<div class="contact-modal" id="wechat-contact-modal" hidden>
  <div class="contact-modal-card" role="dialog" aria-modal="true" aria-labelledby="wechat-contact-title">
    <div class="contact-modal-top">
      <div>
        <div class="contact-modal-title" id="wechat-contact-title">微信联系</div>
        <div class="contact-modal-note">扫码即可添加微信，也可以直接复制微信号 xiamimate。</div>
      </div>
      <button type="button" class="contact-modal-close" id="wechat-contact-close" aria-label="关闭">×</button>
    </div>
    {wechat_qr_html}
    <div class="wechat-id-box">
      <div class="wechat-id-label">微信号</div>
      <div class="wechat-id-value" id="wechat-contact-id">xiamimate</div>
    </div>
    <div class="contact-modal-actions">
      <button type="button" class="contact-action-btn" id="wechat-contact-copy">复制微信号</button>
      <span class="contact-inline-status" id="wechat-contact-status"></span>
    </div>
  </div>
</div>
<script>
(function() {{
  var token = new URLSearchParams(location.search).get("t") || "";
  var sectionLinks = document.querySelectorAll(".sidebar .nav-item[href^='#']");
  var wechatTrigger = document.getElementById("wechat-contact-trigger");
  var wechatModal = document.getElementById("wechat-contact-modal");
  var wechatClose = document.getElementById("wechat-contact-close");
  var wechatCopy = document.getElementById("wechat-contact-copy");
  var wechatStatus = document.getElementById("wechat-contact-status");
  var wechatId = "xiamimate";
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
  function openWechatModal() {{
    if (!wechatModal) return;
    wechatModal.hidden = false;
    document.body.style.overflow = "hidden";
  }}
  function closeWechatModal() {{
    if (!wechatModal) return;
    wechatModal.hidden = true;
    document.body.style.overflow = "";
  }}
  if (wechatTrigger) {{
    wechatTrigger.addEventListener("click", openWechatModal);
  }}
  if (wechatClose) {{
    wechatClose.addEventListener("click", closeWechatModal);
  }}
  if (wechatModal) {{
    wechatModal.addEventListener("click", function(event) {{
      if (event.target === wechatModal) {{
        closeWechatModal();
      }}
    }});
  }}
  document.addEventListener("keydown", function(event) {{
    if (event.key === "Escape" && wechatModal && !wechatModal.hidden) {{
      closeWechatModal();
    }}
  }});
  if (wechatCopy) {{
    wechatCopy.addEventListener("click", function() {{
      var done = function(message) {{
        if (wechatStatus) wechatStatus.textContent = message;
      }};
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(wechatId).then(function() {{
          done("微信号已复制，可以直接到微信里粘贴添加。");
        }}).catch(function() {{
          done("复制失败，请手动添加微信号：" + wechatId);
        }});
        return;
      }}
      done("当前浏览器不支持自动复制，请手动添加微信号：" + wechatId);
    }});
  }}
  markActiveSection();
}})();
</script>
{_PORTAL_CHATBOT_SNIPPET}
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
        <h2>开始使用</h2>
        <div class="card-note">如果你是第一次使用，可以先按下面这套顺序完成登录、进入工作流、查看结果和回到账户页确认消耗。</div>
        <div class="guide-list">
          <div class="guide-item"><div class="guide-title">1. 进入首页并登录</div><div class="guide-desc">从 Open WebUI 首页进入产品，使用统一登录态进入对话与工作流环境。首次登录后，系统会自动为你初始化账户和积分状态。</div></div>
          <div class="guide-item"><div class="guide-title">2. 选择合适的分析入口</div><div class="guide-desc">如果你已经有明确目标商品或类目，可以直接进入 workflow 提交任务；如果还在探索阶段，可以先结合工具与知识库做问题澄清，再进入工作流。</div></div>
          <div class="guide-item"><div class="guide-title">3. 查看结果与中间过程</div><div class="guide-desc">工作流执行完成后，优先查看结论摘要、关键指标和异常提示；如果结果和预期不一致，再回看输入条件、工具返回数据和引用知识内容。</div></div>
          <div class="guide-item"><div class="guide-title">4. 回到账户页查看消耗</div><div class="guide-desc">每次使用后，都可以回到账户管理页确认余额、消费记录和趋势，判断当前套餐是否够用，或者是否需要补充充值额度。</div></div>
        </div>
      </section>
      <section id="workflow" class="section-block card">
        <h2>Workflow 使用方法</h2>
        <div class="card-note">workflow 是产品的核心使用入口，适合你把一个完整分析任务交给系统跑完，并拿到结构化结果。</div>
        <div class="guide-list">
          <div class="guide-item"><div class="guide-title">明确输入条件</div><div class="guide-desc">在发起 workflow 前，尽量明确国家站点、目标类目、分析周期、价格带和你最关心的问题。输入越具体，结果越稳定。</div></div>
          <div class="guide-item"><div class="guide-title">优先提交完整问题而不是短关键词</div><div class="guide-desc">推荐用完整句描述任务，例如“分析澳洲站便携榨汁机近 90 天的需求和竞争情况”，这样系统更容易正确调用工具和知识库。</div></div>
          <div class="guide-item"><div class="guide-title">重点看结论、证据和风险提示</div><div class="guide-desc">不要只看最终一句建议。更重要的是看系统引用了哪些数据、得出了哪些趋势结论、有哪些不确定性和风险点。</div></div>
          <div class="guide-item"><div class="guide-title">二次迭代时缩小问题范围</div><div class="guide-desc">如果第一次结果太泛，可以在第二轮把问题收窄到某个类目、某个市场或某个用户群，提升结果的可执行性。</div></div>
        </div>
      </section>
      <section id="tools" class="section-block card">
        <h2>工具如何使用</h2>
        <div class="card-note">工具能力用于补充 workflow 的自动分析，也适合你在开始正式任务前先做快速验证。</div>
        <div class="guide-list">
          <div class="guide-item"><div class="guide-title">先用工具验证假设</div><div class="guide-desc">如果你只想快速验证一个点，例如类目趋势是否存在、某个国家站点是否有明显波峰，可以先用工具做局部查询，再决定要不要跑完整 workflow。</div></div>
          <div class="guide-item"><div class="guide-title">对结果异常时回查工具输出</div><div class="guide-desc">当 workflow 结果与你经验冲突时，优先看工具层返回的数据是否完整、过滤条件是否准确，以及是否存在时间范围或地区选择错误。</div></div>
          <div class="guide-item"><div class="guide-title">工具适合短平快，workflow 适合完整分析</div><div class="guide-desc">如果你的目标是快速查一个指标，用工具即可；如果你要拿一份相对完整的市场判断、竞争判断和建议结论，还是应该用 workflow。</div></div>
        </div>
      </section>
      <section id="knowledge" class="section-block card">
        <h2>知识库如何使用</h2>
        <div class="card-note">知识库适合承接背景规则、方法论和固定经验，用来帮助系统理解上下文，而不是替代实时数据分析。</div>
        <div class="guide-list">
          <div class="guide-item"><div class="guide-title">适合问规则、方法和背景</div><div class="guide-desc">例如平台规则、选品思路、某类分析框架，这类相对稳定的问题更适合让系统检索知识库后回答。</div></div>
          <div class="guide-item"><div class="guide-title">不要把知识库当成实时行情源</div><div class="guide-desc">涉及实时销量、近期热度或最新竞争格局的问题，仍然应该优先用 workflow 和数据工具来完成，知识库只做补充解释。</div></div>
          <div class="guide-item"><div class="guide-title">把知识库和 workflow 组合使用</div><div class="guide-desc">推荐先用知识库确认概念、规则和分析方法，再进入 workflow 拉取数据并形成结论，这样准确率和可读性会更高。</div></div>
        </div>
      </section>
      <section id="tips" class="section-block card">
        <h2>使用建议</h2>
        <div class="card-note">下面这些习惯可以帮助你更稳定地获得高质量结果，也能避免不必要的积分消耗。</div>
        <div class="guide-list">
          <div class="guide-item"><div class="guide-title">问题一次说完整</div><div class="guide-desc">尽量把市场、类目、时间范围、目标用户和你要的输出形式一次说清楚，避免系统多轮追问或重复执行。</div></div>
          <div class="guide-item"><div class="guide-title">先小范围试跑，再扩大范围</div><div class="guide-desc">当任务比较大时，先从单市场、单类目开始试跑，确认分析方向正确后，再扩大到更多国家或更多商品段。</div></div>
          <div class="guide-item"><div class="guide-title">结合账户页管理使用成本</div><div class="guide-desc">如果你近期频繁使用 workflow 或高频调用工具，建议定期到账户管理页查看消费趋势和账本，及时调整套餐或充值策略。</div></div>
        </div>
      </section>
    '''

    sidebar_html = _sidebar([
        ("使用说明", [("start", "开始使用"), ("workflow", "Workflow 使用"), ("tools", "工具使用"), ("knowledge", "知识库使用"), ("tips", "使用建议")]),
    ])
    return _layout(
        active="guide",
        kicker="使用指南",
        title="产品使用指南",
        subtitle="说明如何使用 workflow、工具和知识库完成实际分析任务，并帮助你更高效地管理使用成本。",
        sidebar_html=sidebar_html,
        body_html=body_html,
    )


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