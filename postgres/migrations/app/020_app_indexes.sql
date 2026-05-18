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
CREATE INDEX IF NOT EXISTS idx_payment_session_order_created ON app.payment_session(order_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_payment_session_user_created ON app.payment_session(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_payment_session_provider_order ON app.payment_session(provider, provider_order_id);
CREATE INDEX IF NOT EXISTS idx_payment_session_status_expires ON app.payment_session(status, expires_at DESC);
CREATE INDEX IF NOT EXISTS idx_payment_callback_event_provider_order ON app.payment_callback_event(provider, order_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_payment_callback_event_trade ON app.payment_callback_event(provider, provider_trade_no, created_at DESC);
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
CREATE INDEX IF NOT EXISTS idx_onebound_1688_queries_run ON app.report_onebound_1688_realtime_queries(report_run_id);
CREATE INDEX IF NOT EXISTS idx_onebound_1688_queries_reuse ON app.report_onebound_1688_realtime_queries(report_run_id, lower(query), marketplace, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_onebound_1688_queries_created_at ON app.report_onebound_1688_realtime_queries(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_onebound_1688_queries_status ON app.report_onebound_1688_realtime_queries(status);
CREATE INDEX IF NOT EXISTS idx_onebound_1688_offers_snapshot_rank ON app.report_onebound_1688_supplier_offer_results(snapshot_id, rank ASC);
CREATE INDEX IF NOT EXISTS idx_onebound_1688_offers_report_created ON app.report_onebound_1688_supplier_offer_results(report_run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_onebound_1688_offers_seller ON app.report_onebound_1688_supplier_offer_results(seller_id, created_at DESC);
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