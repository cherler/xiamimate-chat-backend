-- app.* business tables owned by chat-backend.

CREATE TABLE IF NOT EXISTS app.app_user (
    user_id       TEXT PRIMARY KEY,
    email         TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active',
    plan_tier     TEXT NOT NULL DEFAULT 'free',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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
    amount_cents            INTEGER NOT NULL,
    points_amount           INTEGER NOT NULL,
    status                  TEXT NOT NULL,
    provider_order_id       TEXT,
    provider_trade_no       TEXT,
    callback_payload_json   JSONB NOT NULL DEFAULT '{}'::JSONB,
    paid_at                 TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, provider_order_id),
    UNIQUE (provider, provider_trade_no)
);

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