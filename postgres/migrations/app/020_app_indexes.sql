-- app.* indexes owned by chat-backend.

CREATE INDEX IF NOT EXISTS idx_app_user_plan_tier ON app.app_user(plan_tier);
CREATE INDEX IF NOT EXISTS idx_user_api_key_status ON app.user_api_key(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_credit_account_balance ON app.user_credit_account(balance_points DESC, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_billing_package_status_order ON app.billing_package(status, display_order ASC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_payment_order_user_created ON app.payment_order(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_payment_order_status_created ON app.payment_order(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_billing_subscription_user_status ON app.billing_subscription(user_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_subscription_grant_subscription_created ON app.subscription_grant(subscription_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_session_user_updated ON app.chat_session(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_message_session_created ON app.chat_message(session_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_analysis_run_session_started ON app.analysis_run(session_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_run_status ON app.analysis_run(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_artifact_run ON app.analysis_artifact(run_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_usage_event_user_created ON app.usage_event(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_credit_ledger_user_created ON app.credit_ledger_entry(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_credit_ledger_reference ON app.credit_ledger_entry(user_id, entry_type, reference_id);
CREATE INDEX IF NOT EXISTS idx_idempotency_request_created ON app.idempotency_request(created_at DESC);