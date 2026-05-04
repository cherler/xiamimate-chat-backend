-- ============================================================

-- app compatibility bootstrap: rebuild from postgres/migrations/app/*
-- do not hand-edit this file; edit fragments then rerun rebuild
-- ============================================================

-- >>> BEGIN migrations/app/001_create_app_schema.sql
-- app.* schema owned by chat-backend.

CREATE SCHEMA IF NOT EXISTS app;
-- <<< END migrations/app/001_create_app_schema.sql

-- >>> BEGIN migrations/app/010_app_business_tables.sql
-- app.* business tables owned by chat-backend.

CREATE TABLE IF NOT EXISTS app.app_user (
    user_id       TEXT PRIMARY KEY,
    email         TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active',
    plan_tier     TEXT NOT NULL DEFAULT 'free',
    invite_code   TEXT UNIQUE,
    email_verified_at TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE app.app_user ADD COLUMN IF NOT EXISTS invite_code TEXT;
ALTER TABLE app.app_user ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'app_user_invite_code_key'
    ) THEN
        ALTER TABLE app.app_user
        ADD CONSTRAINT app_user_invite_code_key UNIQUE (invite_code);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS app.user_api_key (
    user_id        TEXT PRIMARY KEY REFERENCES app.app_user(user_id) ON DELETE CASCADE,
    api_key_id     TEXT NOT NULL UNIQUE,
    api_key_prefix TEXT NOT NULL,
    api_key_hash   TEXT NOT NULL UNIQUE,
    api_key_raw    TEXT NOT NULL UNIQUE,
    status         TEXT NOT NULL DEFAULT 'active',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at   TIMESTAMPTZ,
    revoked_at     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS app.user_credit_account (
    user_id                    TEXT PRIMARY KEY REFERENCES app.app_user(user_id) ON DELETE CASCADE,
    balance_points             BIGINT NOT NULL DEFAULT 0,
    reserved_points            BIGINT NOT NULL DEFAULT 0,
    lifetime_granted_points    BIGINT NOT NULL DEFAULT 0,
    lifetime_purchased_points  BIGINT NOT NULL DEFAULT 0,
    lifetime_spent_points      BIGINT NOT NULL DEFAULT 0,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.billing_package (
    package_code    TEXT PRIMARY KEY,
    package_name    TEXT NOT NULL,
    product_type    TEXT NOT NULL,
    price_cents     INTEGER NOT NULL,
    points_amount   INTEGER NOT NULL,
    period_days     INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active',
    display_order   INTEGER NOT NULL DEFAULT 0,
    meta_json       JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.promotion_rule (
    rule_code             TEXT PRIMARY KEY,
    rule_name             TEXT NOT NULL,
    rule_type             TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'active',
    target_product_type   TEXT,
    target_package_codes  JSONB NOT NULL DEFAULT '[]'::JSONB,
    benefit_type          TEXT NOT NULL,
    benefit_value         INTEGER NOT NULL DEFAULT 0,
    criteria_json         JSONB NOT NULL DEFAULT '{}'::JSONB,
    meta_json             JSONB NOT NULL DEFAULT '{}'::JSONB,
    display_order         INTEGER NOT NULL DEFAULT 0,
    start_at              TIMESTAMPTZ,
    end_at                TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.credit_ledger_entry (
    entry_id             TEXT PRIMARY KEY,
    user_id              TEXT NOT NULL REFERENCES app.app_user(user_id) ON DELETE CASCADE,
    api_key_id           TEXT REFERENCES app.user_api_key(api_key_id) ON DELETE SET NULL,
    entry_type           TEXT NOT NULL,
    event_type           TEXT,
    units                INTEGER NOT NULL DEFAULT 1,
    points_delta         INTEGER NOT NULL,
    balance_after_points BIGINT NOT NULL,
    reference_id         TEXT,
    description          TEXT,
    meta_json            JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.payment_order (
    order_id                TEXT PRIMARY KEY,
    user_id                 TEXT NOT NULL REFERENCES app.app_user(user_id) ON DELETE CASCADE,
    package_code            TEXT NOT NULL REFERENCES app.billing_package(package_code),
    product_type            TEXT NOT NULL,
    provider                TEXT NOT NULL,
    list_amount_cents       INTEGER,
    discount_amount_cents   INTEGER,
    amount_cents            INTEGER NOT NULL,
    points_amount           INTEGER NOT NULL,
    status                  TEXT NOT NULL,
    provider_order_id       TEXT,
    provider_trade_no       TEXT,
    promotion_snapshot_json JSONB NOT NULL DEFAULT '{}'::JSONB,
    callback_payload_json   JSONB NOT NULL DEFAULT '{}'::JSONB,
    paid_at                 TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, provider_order_id),
    UNIQUE (provider, provider_trade_no)
);

ALTER TABLE app.payment_order ADD COLUMN IF NOT EXISTS list_amount_cents INTEGER;
ALTER TABLE app.payment_order ADD COLUMN IF NOT EXISTS discount_amount_cents INTEGER;
ALTER TABLE app.payment_order ADD COLUMN IF NOT EXISTS promotion_snapshot_json JSONB NOT NULL DEFAULT '{}'::JSONB;

UPDATE app.payment_order
SET list_amount_cents = COALESCE(list_amount_cents, amount_cents),
    discount_amount_cents = COALESCE(discount_amount_cents, 0),
    promotion_snapshot_json = COALESCE(promotion_snapshot_json, '{}'::JSONB)
WHERE list_amount_cents IS NULL
   OR discount_amount_cents IS NULL
   OR promotion_snapshot_json IS NULL;

CREATE TABLE IF NOT EXISTS app.billing_subscription (
    subscription_id           TEXT PRIMARY KEY,
    user_id                   TEXT NOT NULL REFERENCES app.app_user(user_id) ON DELETE CASCADE,
    package_code              TEXT NOT NULL REFERENCES app.billing_package(package_code),
    provider                  TEXT NOT NULL,
    provider_subscription_id  TEXT,
    status                    TEXT NOT NULL,
    monthly_points            INTEGER NOT NULL,
    current_period_start      TIMESTAMPTZ,
    current_period_end        TIMESTAMPTZ,
    next_grant_at             TIMESTAMPTZ,
    last_grant_at             TIMESTAMPTZ,
    cancel_at_period_end      BOOLEAN NOT NULL DEFAULT FALSE,
    meta_json                 JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, provider_subscription_id)
);

CREATE TABLE IF NOT EXISTS app.subscription_grant (
    grant_id          TEXT PRIMARY KEY,
    subscription_id   TEXT NOT NULL REFERENCES app.billing_subscription(subscription_id) ON DELETE CASCADE,
    user_id           TEXT NOT NULL REFERENCES app.app_user(user_id) ON DELETE CASCADE,
    order_id          TEXT REFERENCES app.payment_order(order_id) ON DELETE SET NULL,
    period_start      TIMESTAMPTZ NOT NULL,
    period_end        TIMESTAMPTZ NOT NULL,
    points_amount     INTEGER NOT NULL,
    reference_id      TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (subscription_id, period_start, period_end),
    UNIQUE (reference_id)
);

CREATE TABLE IF NOT EXISTS app.promotion_claim (
    claim_id                TEXT PRIMARY KEY,
    rule_code               TEXT NOT NULL REFERENCES app.promotion_rule(rule_code) ON DELETE CASCADE,
    user_id                 TEXT NOT NULL REFERENCES app.app_user(user_id) ON DELETE CASCADE,
    order_id                TEXT REFERENCES app.payment_order(order_id) ON DELETE SET NULL,
    claim_key               TEXT NOT NULL,
    status                  TEXT NOT NULL DEFAULT 'applied',
    benefit_snapshot_json   JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (rule_code, claim_key)
);

CREATE TABLE IF NOT EXISTS app.redeem_code_batch (
    batch_id       TEXT PRIMARY KEY,
    batch_name     TEXT NOT NULL,
    code_type      TEXT NOT NULL DEFAULT 'promotion',
    points_amount  INTEGER NOT NULL,
    code_count     INTEGER NOT NULL DEFAULT 1,
    status         TEXT NOT NULL DEFAULT 'active',
    created_by     TEXT NOT NULL,
    note           TEXT,
    meta_json      JSONB NOT NULL DEFAULT '{}'::JSONB,
    valid_from     TIMESTAMPTZ,
    valid_until    TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.redeem_code (
    code_id               TEXT PRIMARY KEY,
    batch_id              TEXT REFERENCES app.redeem_code_batch(batch_id) ON DELETE SET NULL,
    code_hash             TEXT NOT NULL UNIQUE,
    code_plaintext        TEXT,
    code_mask             TEXT NOT NULL,
    code_type             TEXT NOT NULL DEFAULT 'promotion',
    points_amount         INTEGER NOT NULL,
    status                TEXT NOT NULL DEFAULT 'active',
    created_by            TEXT NOT NULL,
    note                  TEXT,
    meta_json             JSONB NOT NULL DEFAULT '{}'::JSONB,
    valid_from            TIMESTAMPTZ,
    valid_until           TIMESTAMPTZ,
    redeemed_by_user_id   TEXT REFERENCES app.app_user(user_id) ON DELETE SET NULL,
    redeemed_at           TIMESTAMPTZ,
    ledger_entry_id       TEXT REFERENCES app.credit_ledger_entry(entry_id) ON DELETE SET NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE app.redeem_code ADD COLUMN IF NOT EXISTS code_plaintext TEXT;

CREATE TABLE IF NOT EXISTS app.email_verification_challenge (
    challenge_id      TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL REFERENCES app.app_user(user_id) ON DELETE CASCADE,
    email             TEXT NOT NULL,
    purpose           TEXT NOT NULL DEFAULT 'signup_email_verify',
    code_hash         TEXT NOT NULL,
    failed_attempt_count INTEGER NOT NULL DEFAULT 0,
    locked_until      TIMESTAMPTZ,
    last_failed_at    TIMESTAMPTZ,
    expires_at        TIMESTAMPTZ NOT NULL,
    consumed_at       TIMESTAMPTZ,
    last_sent_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE app.email_verification_challenge ADD COLUMN IF NOT EXISTS failed_attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE app.email_verification_challenge ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ;
ALTER TABLE app.email_verification_challenge ADD COLUMN IF NOT EXISTS last_failed_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS app.user_referral_binding (
    binding_id          TEXT PRIMARY KEY,
    inviter_user_id     TEXT NOT NULL REFERENCES app.app_user(user_id) ON DELETE CASCADE,
    invited_user_id     TEXT NOT NULL REFERENCES app.app_user(user_id) ON DELETE CASCADE,
    invite_code         TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'bound',
    activated_at        TIMESTAMPTZ,
    rewarded_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (invited_user_id)
);

CREATE TABLE IF NOT EXISTS app.idempotency_request (
    scope            TEXT NOT NULL,
    idempotency_key  TEXT NOT NULL,
    request_hash     TEXT NOT NULL,
    response_json    JSONB,
    status_code      INTEGER,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (scope, idempotency_key)
);

CREATE TABLE IF NOT EXISTS app.chat_session (
    session_id              TEXT PRIMARY KEY,
    user_id                 TEXT NOT NULL REFERENCES app.app_user(user_id),
    title                   TEXT,
    target_platform         TEXT NOT NULL,
    target_market           TEXT,
    validation_marketplace  TEXT,
    status                  TEXT NOT NULL DEFAULT 'active',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at               TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS app.chat_message (
    message_id      TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES app.chat_session(session_id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    message_type    TEXT NOT NULL DEFAULT 'text',
    metadata_json   JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.analysis_run (
    run_id               TEXT PRIMARY KEY,
    session_id           TEXT NOT NULL REFERENCES app.chat_session(session_id) ON DELETE CASCADE,
    message_id           TEXT REFERENCES app.chat_message(message_id) ON DELETE SET NULL,
    product_query        TEXT NOT NULL,
    analysis_goal        TEXT,
    input_payload_json   JSONB NOT NULL DEFAULT '{}'::JSONB,
    status               TEXT NOT NULL DEFAULT 'queued',
    dify_run_id          TEXT,
    final_answer_text    TEXT,
    started_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at          TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.analysis_artifact (
    artifact_id             TEXT PRIMARY KEY,
    run_id                  TEXT NOT NULL REFERENCES app.analysis_run(run_id) ON DELETE CASCADE,
    artifact_type           TEXT NOT NULL,
    artifact_key            TEXT NOT NULL,
    artifact_payload_json   JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, artifact_key)
);

CREATE TABLE IF NOT EXISTS app.usage_event (
    event_id       TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES app.app_user(user_id),
    session_id     TEXT REFERENCES app.chat_session(session_id) ON DELETE CASCADE,
    run_id         TEXT REFERENCES app.analysis_run(run_id) ON DELETE CASCADE,
    event_type     TEXT NOT NULL,
    units          INTEGER NOT NULL DEFAULT 1,
    meta_json      JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.report_tiktok_realtime_queries (
    id                   UUID PRIMARY KEY,
    report_run_id        TEXT NOT NULL,
    query                TEXT NOT NULL,
    target_market        TEXT NOT NULL,
    provider             TEXT NOT NULL DEFAULT 'tikhub',
    request_payload      JSONB NOT NULL,
    vendor_endpoints     JSONB NOT NULL,
    vendor_response_raw  JSONB,
    normalized_summary   JSONB,
    result_text          TEXT,
    status               TEXT NOT NULL,
    latency_ms           INTEGER,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.daily_credit_quota_state (
    user_id               TEXT NOT NULL REFERENCES app.app_user(user_id) ON DELETE CASCADE,
    quota_date            DATE NOT NULL,
    quota_points          INTEGER NOT NULL,
    applied_delta_points  INTEGER NOT NULL,
    consumed_points       INTEGER NOT NULL DEFAULT 0,
    reset_reference_id    TEXT NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, quota_date)
);

CREATE TABLE IF NOT EXISTS app.user_notification (
    notification_id   TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL REFERENCES app.app_user(user_id) ON DELETE CASCADE,
    notification_key  TEXT NOT NULL,
    category          TEXT NOT NULL,
    tag               TEXT NOT NULL,
    level             TEXT NOT NULL DEFAULT 'info',
    title             TEXT NOT NULL,
    body              TEXT NOT NULL,
    event_type        TEXT,
    resource_type     TEXT,
    resource_id       TEXT,
    action_url        TEXT,
    read_at           TIMESTAMPTZ,
    occurred_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, notification_key)
);

CREATE TABLE IF NOT EXISTS app.system_notification_broadcast (
    broadcast_id           TEXT PRIMARY KEY,
    operator_id            TEXT NOT NULL,
    target_scope           TEXT NOT NULL DEFAULT 'all_active',
    tag                    TEXT NOT NULL,
    level                  TEXT NOT NULL DEFAULT 'info',
    title                  TEXT NOT NULL,
    body                   TEXT NOT NULL,
    action_url             TEXT,
    delivered_user_count   INTEGER NOT NULL DEFAULT 0,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.billing_event_pricing (
    event_type      TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    points_per_unit INTEGER NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'active',
    display_order   INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.admin_audit_log (
    audit_id      TEXT PRIMARY KEY,
    operator_id   TEXT NOT NULL,
    action        TEXT NOT NULL,
    target_type   TEXT NOT NULL,
    target_id     TEXT,
    request_json  JSONB NOT NULL DEFAULT '{}'::JSONB,
    result_json   JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- <<< END migrations/app/010_app_business_tables.sql

-- >>> BEGIN migrations/app/020_app_indexes.sql
-- app.* indexes owned by chat-backend.

CREATE INDEX IF NOT EXISTS idx_app_user_plan_tier ON app.app_user(plan_tier);
CREATE INDEX IF NOT EXISTS idx_app_user_email_verified ON app.app_user(email_verified_at DESC);
CREATE INDEX IF NOT EXISTS idx_app_user_invite_code ON app.app_user(invite_code);
CREATE INDEX IF NOT EXISTS idx_user_api_key_status ON app.user_api_key(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_credit_account_balance ON app.user_credit_account(balance_points DESC, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_billing_package_status_order ON app.billing_package(status, display_order ASC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_promotion_rule_status_order ON app.promotion_rule(status, display_order ASC, start_at ASC, end_at ASC);
CREATE INDEX IF NOT EXISTS idx_payment_order_user_created ON app.payment_order(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_payment_order_status_created ON app.payment_order(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_payment_order_user_product_status ON app.payment_order(user_id, product_type, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_billing_subscription_user_status ON app.billing_subscription(user_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_subscription_grant_subscription_created ON app.subscription_grant(subscription_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_promotion_claim_user_created ON app.promotion_claim(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_promotion_claim_order_created ON app.promotion_claim(order_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_redeem_code_batch_status_created ON app.redeem_code_batch(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_redeem_code_batch_operator_created ON app.redeem_code_batch(created_by, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_redeem_code_status_created ON app.redeem_code(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_redeem_code_batch_created ON app.redeem_code(batch_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_redeem_code_redeemed_user_created ON app.redeem_code(redeemed_by_user_id, redeemed_at DESC);
WITH ranked_redeem_duplicates AS (
		SELECT
				code_id,
				ROW_NUMBER() OVER (
						PARTITION BY batch_id, redeemed_by_user_id
						ORDER BY COALESCE(redeemed_at, created_at) ASC, code_id ASC
				) AS redeem_rank
		FROM app.redeem_code
		WHERE batch_id IS NOT NULL
			AND redeemed_by_user_id IS NOT NULL
)
UPDATE app.redeem_code AS code
SET meta_json = COALESCE(code.meta_json, '{}'::jsonb) || '{"legacy_batch_duplicate": true}'::jsonb,
		updated_at = NOW()
FROM ranked_redeem_duplicates AS ranked
WHERE code.code_id = ranked.code_id
	AND ranked.redeem_rank > 1
	AND COALESCE(code.meta_json ->> 'legacy_batch_duplicate', 'false') <> 'true';

CREATE UNIQUE INDEX IF NOT EXISTS idx_redeem_code_batch_user_once ON app.redeem_code(batch_id, redeemed_by_user_id)
WHERE batch_id IS NOT NULL
	AND redeemed_by_user_id IS NOT NULL
	AND COALESCE(meta_json ->> 'legacy_batch_duplicate', 'false') <> 'true';
CREATE INDEX IF NOT EXISTS idx_email_verification_challenge_user_created ON app.email_verification_challenge(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_verification_challenge_email_created ON app.email_verification_challenge(email, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_referral_binding_inviter_created ON app.user_referral_binding(inviter_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_referral_binding_status_updated ON app.user_referral_binding(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_session_user_updated ON app.chat_session(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_message_session_created ON app.chat_message(session_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_analysis_run_session_started ON app.analysis_run(session_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_run_status ON app.analysis_run(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_artifact_run ON app.analysis_artifact(run_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_usage_event_user_created ON app.usage_event(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tiktok_realtime_queries_run ON app.report_tiktok_realtime_queries(report_run_id);
CREATE INDEX IF NOT EXISTS idx_tiktok_realtime_queries_reuse ON app.report_tiktok_realtime_queries(report_run_id, lower(query), target_market, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tiktok_realtime_queries_created_at ON app.report_tiktok_realtime_queries(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tiktok_realtime_queries_status ON app.report_tiktok_realtime_queries(status);
CREATE INDEX IF NOT EXISTS idx_credit_ledger_user_created ON app.credit_ledger_entry(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_credit_ledger_reference ON app.credit_ledger_entry(user_id, entry_type, reference_id);
CREATE INDEX IF NOT EXISTS idx_redeem_code_hash_status ON app.redeem_code(code_hash, status);
CREATE INDEX IF NOT EXISTS idx_redeem_code_plaintext_batch_created ON app.redeem_code(batch_id, code_plaintext, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_daily_credit_quota_state_quota_date ON app.daily_credit_quota_state(quota_date DESC, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_notification_user_occurred ON app.user_notification(user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_notification_user_category_read ON app.user_notification(user_id, category, read_at, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_system_notification_broadcast_created ON app.system_notification_broadcast(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_system_notification_broadcast_operator_created ON app.system_notification_broadcast(operator_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_billing_event_pricing_status ON app.billing_event_pricing(status, display_order ASC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_operator_created ON app.admin_audit_log(operator_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_target_created ON app.admin_audit_log(target_type, target_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_idempotency_request_created ON app.idempotency_request(created_at DESC);
-- <<< END migrations/app/020_app_indexes.sql

