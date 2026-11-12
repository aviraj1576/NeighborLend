-- Generated from migrate_payments against the inspected hosted catalog, locally.
-- REVIEW AND APPROVAL REQUIRED BEFORE HOSTED EXECUTION.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='60s';
SET LOCAL search_path=public;
CREATE TABLE IF NOT EXISTS rental_bookings (
	id VARCHAR(36) NOT NULL,
	borrow_request_id VARCHAR NOT NULL,
	offer_id VARCHAR NOT NULL,
	listing_id VARCHAR NOT NULL,
	borrower_id VARCHAR NOT NULL,
	lender_id VARCHAR NOT NULL,
	start_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	end_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	duration_days INTEGER NOT NULL,
	daily_rate_paise BIGINT NOT NULL,
	rental_fee_paise BIGINT NOT NULL,
	security_deposit_paise BIGINT NOT NULL,
	total_amount_paise BIGINT NOT NULL,
	currency VARCHAR(3) NOT NULL,
	provider VARCHAR(20) NOT NULL,
	booking_status VARCHAR(32) NOT NULL,
	payment_status VARCHAR(32) NOT NULL,
	deposit_state VARCHAR(32) NOT NULL,
	refunded_paise BIGINT NOT NULL,
	deduction_paise BIGINT NOT NULL,
	settlement_kind VARCHAR(32),
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (duration_days > 0 AND daily_rate_paise > 0 AND rental_fee_paise > 0),
	CHECK (security_deposit_paise >= 0 AND total_amount_paise = rental_fee_paise + security_deposit_paise),
	CHECK (refunded_paise >= 0 AND deduction_paise >= 0 AND refunded_paise + deduction_paise <= security_deposit_paise),
	CHECK (currency = 'INR' AND provider IN ('mock', 'razorpay_test')),
	CHECK (booking_status IN ('awaiting_payment','funded','active','returned','disputed','settling','completed','cancelled')),
	CHECK (payment_status IN ('unpaid','order_created','authorized','captured','failed')),
	UNIQUE (borrow_request_id),
	FOREIGN KEY(borrow_request_id) REFERENCES borrow_requests (id),
	UNIQUE (offer_id),
	FOREIGN KEY(offer_id) REFERENCES negotiation_offers (id),
	FOREIGN KEY(listing_id) REFERENCES listings (id),
	FOREIGN KEY(borrower_id) REFERENCES users (id),
	FOREIGN KEY(lender_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_rental_bookings_lender_id ON rental_bookings (lender_id);

CREATE INDEX IF NOT EXISTS ix_rental_bookings_borrower_id ON rental_bookings (borrower_id);

CREATE TABLE IF NOT EXISTS processed_webhooks (
	event_id VARCHAR(128) NOT NULL,
	event_type VARCHAR(64) NOT NULL,
	payload_sha256 VARCHAR(64) NOT NULL,
	status VARCHAR(32) NOT NULL,
	payload TEXT NOT NULL,
	processed_at TIMESTAMP WITHOUT TIME ZONE,
	PRIMARY KEY (event_id)
);

CREATE TABLE IF NOT EXISTS payment_transactions (
	id VARCHAR(36) NOT NULL,
	booking_id VARCHAR NOT NULL,
	provider VARCHAR(20) NOT NULL,
	transaction_type VARCHAR(32) NOT NULL,
	amount_paise BIGINT NOT NULL,
	currency VARCHAR(3) NOT NULL,
	status VARCHAR(32) NOT NULL,
	idempotency_key VARCHAR(128) NOT NULL,
	razorpay_order_id VARCHAR(128),
	razorpay_payment_id VARCHAR(128),
	razorpay_refund_id VARCHAR(128),
	error_code VARCHAR(64),
	operation_version INTEGER NOT NULL,
	raw_response TEXT,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (amount_paise > 0 AND currency = 'INR'),
	FOREIGN KEY(booking_id) REFERENCES rental_bookings (id),
	UNIQUE (idempotency_key),
	UNIQUE (razorpay_payment_id),
	UNIQUE (razorpay_refund_id)
);

CREATE INDEX IF NOT EXISTS ix_payment_transactions_razorpay_order_id ON payment_transactions (razorpay_order_id);

CREATE INDEX IF NOT EXISTS ix_payment_transactions_booking_id ON payment_transactions (booking_id);

CREATE TABLE IF NOT EXISTS journal_transactions (
	id VARCHAR(36) NOT NULL,
	booking_id VARCHAR NOT NULL,
	reference VARCHAR(128) NOT NULL,
	status VARCHAR(10) NOT NULL,
	debit_paise BIGINT NOT NULL,
	credit_paise BIGINT NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (debit_paise = credit_paise AND debit_paise > 0),
	FOREIGN KEY(booking_id) REFERENCES rental_bookings (id),
	UNIQUE (reference)
);

CREATE INDEX IF NOT EXISTS ix_journal_transactions_booking_id ON journal_transactions (booking_id);

CREATE TABLE IF NOT EXISTS refund_intents (
	id VARCHAR(36) NOT NULL,
	booking_id VARCHAR NOT NULL,
	amount_paise BIGINT NOT NULL,
	deduction_paise BIGINT NOT NULL,
	kind VARCHAR(32) NOT NULL,
	authorized_by VARCHAR NOT NULL,
	status VARCHAR(32) NOT NULL,
	provider_refund_id VARCHAR(128),
	idempotency_key VARCHAR(128) NOT NULL,
	error_code VARCHAR(64),
	active_attempt_id VARCHAR(36),
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (amount_paise >= 0 AND deduction_paise >= 0),
	UNIQUE (booking_id),
	FOREIGN KEY(booking_id) REFERENCES rental_bookings (id),
	FOREIGN KEY(authorized_by) REFERENCES users (id),
	UNIQUE (provider_refund_id),
	UNIQUE (idempotency_key)
);

CREATE TABLE IF NOT EXISTS rental_disputes (
	id VARCHAR(36) NOT NULL,
	booking_id VARCHAR NOT NULL,
	inspection_id VARCHAR(64),
	cv_run_id VARCHAR(64),
	assessment_id VARCHAR(64),
	claimed_deduction_paise BIGINT NOT NULL,
	claim_version INTEGER NOT NULL,
	approved_deduction_paise BIGINT,
	status VARCHAR(32) NOT NULL,
	lender_claim_notes TEXT NOT NULL,
	borrower_response_notes TEXT,
	borrower_accepted BOOLEAN NOT NULL,
	resolved_by VARCHAR,
	resolved_at TIMESTAMP WITHOUT TIME ZONE,
	initiated_by VARCHAR,
	origin VARCHAR(32) NOT NULL,
	resolution_reason TEXT,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (claimed_deduction_paise >= 0 AND (approved_deduction_paise IS NULL OR approved_deduction_paise >= 0)),
	UNIQUE (booking_id),
	FOREIGN KEY(booking_id) REFERENCES rental_bookings (id),
	FOREIGN KEY(resolved_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS financial_audit_records (
	id VARCHAR(36) NOT NULL,
	booking_id VARCHAR NOT NULL,
	actor_id VARCHAR NOT NULL,
	action VARCHAR(64) NOT NULL,
	details TEXT NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(booking_id) REFERENCES rental_bookings (id)
);

CREATE INDEX IF NOT EXISTS ix_financial_audit_records_booking_id ON financial_audit_records (booking_id);

CREATE TABLE IF NOT EXISTS rental_evidence (
	id VARCHAR(36) NOT NULL,
	booking_id VARCHAR NOT NULL,
	uploaded_by VARCHAR NOT NULL,
	stage VARCHAR(24) NOT NULL,
	storage_name VARCHAR(80) NOT NULL,
	sha256 VARCHAR(64) NOT NULL,
	media_type VARCHAR(32) NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (stage IN ('handover','receipt','return')),
	FOREIGN KEY(booking_id) REFERENCES rental_bookings (id),
	FOREIGN KEY(uploaded_by) REFERENCES users (id),
	UNIQUE (storage_name)
);

CREATE INDEX IF NOT EXISTS ix_rental_evidence_booking_id ON rental_evidence (booking_id);

CREATE TABLE IF NOT EXISTS escrow_ledger_entries (
	id VARCHAR(36) NOT NULL,
	journal_id VARCHAR NOT NULL,
	booking_id VARCHAR NOT NULL,
	account_type VARCHAR(40) NOT NULL,
	entry_type VARCHAR(6) NOT NULL,
	amount_paise BIGINT NOT NULL,
	description VARCHAR(255) NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (amount_paise > 0 AND entry_type IN ('DEBIT','CREDIT')),
	FOREIGN KEY(journal_id) REFERENCES journal_transactions (id),
	FOREIGN KEY(booking_id) REFERENCES rental_bookings (id)
);

CREATE INDEX IF NOT EXISTS ix_escrow_ledger_entries_journal_id ON escrow_ledger_entries (journal_id);

CREATE INDEX IF NOT EXISTS ix_escrow_ledger_entries_booking_id ON escrow_ledger_entries (booking_id);

CREATE TABLE IF NOT EXISTS refund_attempts (
	id VARCHAR(36) NOT NULL,
	refund_id VARCHAR NOT NULL,
	provider_refund_id VARCHAR(128),
	idempotency_key VARCHAR(128),
	status VARCHAR(32) NOT NULL,
	error_code VARCHAR(64),
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(refund_id) REFERENCES refund_intents (id)
);

CREATE INDEX IF NOT EXISTS ix_refund_attempts_provider_refund_id ON refund_attempts (provider_refund_id);

CREATE INDEX IF NOT EXISTS ix_refund_attempts_refund_id ON refund_attempts (refund_id);

ALTER TABLE negotiation_offers ADD COLUMN IF NOT EXISTS borrower_id_snapshot VARCHAR;

ALTER TABLE negotiation_offers ADD COLUMN IF NOT EXISTS lender_id_snapshot VARCHAR;

ALTER TABLE negotiation_offers ADD COLUMN IF NOT EXISTS daily_rate_paise BIGINT;

ALTER TABLE negotiation_offers ADD COLUMN IF NOT EXISTS rental_fee_paise BIGINT;

ALTER TABLE negotiation_offers ADD COLUMN IF NOT EXISTS security_deposit_paise BIGINT;

ALTER TABLE negotiation_offers ADD COLUMN IF NOT EXISTS total_amount_paise BIGINT;

ALTER TABLE borrow_requests ADD COLUMN IF NOT EXISTS handover_condition_note TEXT;

ALTER TABLE borrow_requests ADD COLUMN IF NOT EXISTS return_condition_note TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS ix_payment_refund_unique ON payment_transactions (razorpay_refund_id);

CREATE OR REPLACE FUNCTION nl_snapshot_guard() RETURNS trigger AS $$ BEGIN
              IF ROW(OLD.borrow_request_id,OLD.offer_id,OLD.listing_id,OLD.borrower_id,OLD.lender_id,OLD.start_date,OLD.end_date,OLD.duration_days,OLD.daily_rate_paise,OLD.rental_fee_paise,OLD.security_deposit_paise,OLD.total_amount_paise,OLD.currency,OLD.provider)
                IS DISTINCT FROM ROW(NEW.borrow_request_id,NEW.offer_id,NEW.listing_id,NEW.borrower_id,NEW.lender_id,NEW.start_date,NEW.end_date,NEW.duration_days,NEW.daily_rate_paise,NEW.rental_fee_paise,NEW.security_deposit_paise,NEW.total_amount_paise,NEW.currency,NEW.provider)
              THEN RAISE EXCEPTION 'immutable booking snapshot'; END IF;
              RETURN NEW; END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS nl_snapshot_guard ON rental_bookings;

CREATE TRIGGER nl_snapshot_guard BEFORE UPDATE ON rental_bookings FOR EACH ROW EXECUTE FUNCTION nl_snapshot_guard();

CREATE OR REPLACE FUNCTION nl_immutable() RETURNS trigger AS $$
              BEGIN RAISE EXCEPTION 'append-only financial records'; END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS nl_immutable ON escrow_ledger_entries;

CREATE TRIGGER nl_immutable BEFORE UPDATE OR DELETE ON escrow_ledger_entries FOR EACH ROW EXECUTE FUNCTION nl_immutable();

DROP TRIGGER IF EXISTS nl_immutable ON financial_audit_records;

CREATE TRIGGER nl_immutable BEFORE UPDATE OR DELETE ON financial_audit_records FOR EACH ROW EXECUTE FUNCTION nl_immutable();

DROP TRIGGER IF EXISTS nl_immutable ON rental_evidence;

CREATE TRIGGER nl_immutable BEFORE UPDATE OR DELETE ON rental_evidence FOR EACH ROW EXECUTE FUNCTION nl_immutable();

CREATE OR REPLACE FUNCTION nl_journal_guard() RETURNS trigger AS $$ BEGIN
              IF TG_OP='DELETE' THEN RAISE EXCEPTION 'append-only journal'; END IF;
              IF TG_OP='INSERT' THEN
                IF NEW.status!='draft' THEN RAISE EXCEPTION 'journal must start draft'; END IF;
                RETURN NEW;
              END IF;
              IF OLD.status!='draft' OR NEW.status!='posted'
                OR (to_jsonb(OLD)-'status') IS DISTINCT FROM (to_jsonb(NEW)-'status')
                OR NEW.debit_paise!=(SELECT COALESCE(SUM(amount_paise),0) FROM escrow_ledger_entries WHERE journal_id=NEW.id AND entry_type='DEBIT')
                OR NEW.credit_paise!=(SELECT COALESCE(SUM(amount_paise),0) FROM escrow_ledger_entries WHERE journal_id=NEW.id AND entry_type='CREDIT')
              THEN RAISE EXCEPTION 'invalid journal posting'; END IF;
              RETURN NEW; END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS nl_journal_guard ON journal_transactions;

CREATE TRIGGER nl_journal_guard BEFORE INSERT OR UPDATE OR DELETE ON journal_transactions FOR EACH ROW EXECUTE FUNCTION nl_journal_guard();

CREATE OR REPLACE FUNCTION nl_line_guard() RETURNS trigger AS $$ BEGIN
              PERFORM id FROM journal_transactions WHERE id=NEW.journal_id AND booking_id=NEW.booking_id AND status='draft' FOR UPDATE;
              IF NOT FOUND THEN RAISE EXCEPTION 'invalid journal line'; END IF;
              RETURN NEW; END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS nl_line_guard ON escrow_ledger_entries;

CREATE TRIGGER nl_line_guard BEFORE INSERT ON escrow_ledger_entries FOR EACH ROW EXECUTE FUNCTION nl_line_guard();

CREATE OR REPLACE FUNCTION nl_terms_refund_intents() RETURNS trigger AS $$ BEGIN IF ROW(OLD.booking_id,OLD.amount_paise,OLD.deduction_paise,OLD.kind,OLD.authorized_by) IS DISTINCT FROM ROW(NEW.booking_id,NEW.amount_paise,NEW.deduction_paise,NEW.kind,NEW.authorized_by) THEN RAISE EXCEPTION 'immutable financial terms'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS nl_terms ON refund_intents;

CREATE TRIGGER nl_terms BEFORE UPDATE ON refund_intents FOR EACH ROW EXECUTE FUNCTION nl_terms_refund_intents();

CREATE OR REPLACE FUNCTION nl_terms_negotiation_offers() RETURNS trigger AS $$ BEGIN IF ROW(OLD.listing_id,OLD.conversation_id,OLD.sender_id,OLD.start_date,OLD.end_date,OLD.daily_price,OLD.total_cost,OLD.borrower_id_snapshot,OLD.lender_id_snapshot,OLD.daily_rate_paise,OLD.rental_fee_paise,OLD.security_deposit_paise,OLD.total_amount_paise) IS DISTINCT FROM ROW(NEW.listing_id,NEW.conversation_id,NEW.sender_id,NEW.start_date,NEW.end_date,NEW.daily_price,NEW.total_cost,NEW.borrower_id_snapshot,NEW.lender_id_snapshot,NEW.daily_rate_paise,NEW.rental_fee_paise,NEW.security_deposit_paise,NEW.total_amount_paise) THEN RAISE EXCEPTION 'immutable financial terms'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS nl_terms ON negotiation_offers;

CREATE TRIGGER nl_terms BEFORE UPDATE ON negotiation_offers FOR EACH ROW EXECUTE FUNCTION nl_terms_negotiation_offers();

CREATE TABLE IF NOT EXISTS payment_schema_versions (version INTEGER PRIMARY KEY);

INSERT INTO payment_schema_versions(version) VALUES (2) ON CONFLICT(version) DO NOTHING;

CREATE OR REPLACE FUNCTION nl_terminal_guard() RETURNS trigger AS $$ BEGIN
              IF TG_TABLE_NAME='rental_bookings' THEN
                IF OLD.payment_status='captured' AND NEW.payment_status!='captured' THEN RAISE EXCEPTION 'confirmed capture cannot regress'; END IF;
              ELSE
                IF OLD.status='processed' AND NEW.status!='processed' THEN RAISE EXCEPTION 'confirmed refund cannot regress'; END IF;
              END IF; RETURN NEW; END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS nl_terminal_guard ON rental_bookings;

CREATE TRIGGER nl_terminal_guard BEFORE UPDATE ON rental_bookings FOR EACH ROW EXECUTE FUNCTION nl_terminal_guard();

DROP TRIGGER IF EXISTS nl_terminal_guard ON refund_intents;

CREATE TRIGGER nl_terminal_guard BEFORE UPDATE ON refund_intents FOR EACH ROW EXECUTE FUNCTION nl_terminal_guard();

CREATE OR REPLACE FUNCTION nl_decision_guard() RETURNS trigger AS $$ BEGIN
              IF OLD.resolved_at IS NOT NULL AND ROW(OLD.approved_deduction_paise,OLD.resolved_by,OLD.resolved_at,OLD.resolution_reason,OLD.status) IS DISTINCT FROM ROW(NEW.approved_deduction_paise,NEW.resolved_by,NEW.resolved_at,NEW.resolution_reason,NEW.status) THEN RAISE EXCEPTION 'immutable dispute decision'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS nl_decision_guard ON rental_disputes;

CREATE TRIGGER nl_decision_guard BEFORE UPDATE ON rental_disputes FOR EACH ROW EXECUTE FUNCTION nl_decision_guard();

CREATE UNIQUE INDEX IF NOT EXISTS nl_one_capture_per_booking
        ON payment_transactions(booking_id) WHERE transaction_type='payment' AND status='captured';

CREATE UNIQUE INDEX IF NOT EXISTS nl_order_provider_unique
        ON payment_transactions(razorpay_order_id) WHERE transaction_type='order';

CREATE INDEX IF NOT EXISTS nl_refund_reconciliation
        ON refund_intents(status,created_at);

CREATE INDEX IF NOT EXISTS nl_dispute_review
        ON rental_disputes(status,created_at);

CREATE OR REPLACE FUNCTION nl_booking_binding_guard() RETURNS trigger
            LANGUAGE plpgsql SET search_path FROM CURRENT AS $$ BEGIN
              IF NEW.duration_days<=0 OR NEW.duration_days>3650 OR NEW.total_amount_paise>1000000000
                OR NEW.rental_fee_paise!=NEW.daily_rate_paise*NEW.duration_days OR NEW.end_date<NEW.start_date
                OR NOT EXISTS(SELECT 1 FROM borrow_requests r JOIN listings l ON l.id=r.listing_id
                  JOIN negotiation_offers o ON o.id=NEW.offer_id
                  WHERE r.id=NEW.borrow_request_id AND r.borrower_id=NEW.borrower_id
                    AND l.id=NEW.listing_id AND l.owner_id=NEW.lender_id
                    AND o.borrow_request_id=r.id AND o.listing_id=l.id AND o.status='accepted'
                    AND o.borrower_id_snapshot=NEW.borrower_id AND o.lender_id_snapshot=NEW.lender_id
                    AND o.daily_rate_paise=NEW.daily_rate_paise AND o.rental_fee_paise=NEW.rental_fee_paise
                    AND o.security_deposit_paise=NEW.security_deposit_paise
                    AND o.total_amount_paise=NEW.total_amount_paise
                    AND o.start_date=NEW.start_date AND o.end_date=NEW.end_date)
              THEN RAISE EXCEPTION 'booking does not match accepted rental'; END IF;
              RETURN NEW;
            END; $$;

DROP TRIGGER IF EXISTS nl_booking_binding_guard ON rental_bookings;

CREATE TRIGGER nl_booking_binding_guard BEFORE INSERT
            ON rental_bookings FOR EACH ROW EXECUTE FUNCTION nl_booking_binding_guard();

CREATE OR REPLACE FUNCTION nl_payment_binding_guard() RETURNS trigger
            LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
            DECLARE b RECORD;
            BEGIN
              SELECT * INTO b FROM rental_bookings WHERE id=NEW.booking_id FOR UPDATE;
              IF NOT FOUND OR NEW.provider IS DISTINCT FROM b.provider OR NEW.currency IS DISTINCT FROM b.currency
                OR NEW.amount_paise<=0 OR NEW.transaction_type NOT IN ('order','payment','deposit_refund')
                OR (NEW.transaction_type IN ('order','payment') AND NEW.amount_paise!=b.total_amount_paise)
                OR (NEW.transaction_type='deposit_refund' AND NOT EXISTS(
                  SELECT 1 FROM refund_intents r WHERE r.booking_id=b.id AND r.amount_paise=NEW.amount_paise))
              THEN RAISE EXCEPTION 'payment does not match authorized booking'; END IF;
              IF TG_OP='UPDATE' AND (
                ROW(OLD.booking_id,OLD.provider,OLD.transaction_type,OLD.amount_paise,OLD.currency,OLD.idempotency_key)
                  IS DISTINCT FROM ROW(NEW.booking_id,NEW.provider,NEW.transaction_type,NEW.amount_paise,NEW.currency,NEW.idempotency_key)
                OR (OLD.razorpay_order_id IS NOT NULL AND OLD.razorpay_order_id IS DISTINCT FROM NEW.razorpay_order_id)
                OR (OLD.razorpay_payment_id IS NOT NULL AND OLD.razorpay_payment_id IS DISTINCT FROM NEW.razorpay_payment_id)
                OR (OLD.status IN ('captured','processed') AND OLD.status IS DISTINCT FROM NEW.status))
              THEN RAISE EXCEPTION 'immutable verified payment'; END IF;
              IF NEW.transaction_type='payment' AND NOT EXISTS(
                SELECT 1 FROM payment_transactions p WHERE p.booking_id=b.id AND p.transaction_type='order'
                  AND p.razorpay_order_id=NEW.razorpay_order_id AND NEW.razorpay_payment_id IS NOT NULL)
              THEN RAISE EXCEPTION 'payment order binding missing'; END IF;
              RETURN NEW;
            END; $$;

DROP TRIGGER IF EXISTS nl_payment_binding_guard ON payment_transactions;

CREATE TRIGGER nl_payment_binding_guard BEFORE INSERT OR UPDATE
            ON payment_transactions FOR EACH ROW EXECUTE FUNCTION nl_payment_binding_guard();

CREATE OR REPLACE FUNCTION nl_refund_allocation_guard() RETURNS trigger
            LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
            DECLARE b RECORD;
            BEGIN
              SELECT * INTO b FROM rental_bookings WHERE id=NEW.booking_id FOR UPDATE;
              IF NOT FOUND OR b.payment_status!='captured'
                OR NEW.amount_paise<0 OR NEW.deduction_paise<0
                OR NEW.kind NOT IN ('clean_return','dispute','cancellation')
                OR (NEW.kind='cancellation' AND (NEW.deduction_paise!=0 OR NEW.amount_paise!=b.total_amount_paise))
                OR (NEW.kind!='cancellation' AND NEW.amount_paise+NEW.deduction_paise!=b.security_deposit_paise)
              THEN RAISE EXCEPTION 'refund exceeds authorized allocation'; END IF;
              RETURN NEW;
            END; $$;

DROP TRIGGER IF EXISTS nl_refund_allocation_guard ON refund_intents;

CREATE TRIGGER nl_refund_allocation_guard BEFORE INSERT OR UPDATE
            ON refund_intents FOR EACH ROW EXECUTE FUNCTION nl_refund_allocation_guard();

DROP TRIGGER IF EXISTS nl_no_financial_delete ON payment_transactions;

CREATE TRIGGER nl_no_financial_delete BEFORE DELETE ON payment_transactions FOR EACH ROW EXECUTE FUNCTION nl_immutable();

DROP TRIGGER IF EXISTS nl_no_financial_delete ON refund_intents;

CREATE TRIGGER nl_no_financial_delete BEFORE DELETE ON refund_intents FOR EACH ROW EXECUTE FUNCTION nl_immutable();

DROP TRIGGER IF EXISTS nl_no_financial_delete ON rental_disputes;

CREATE TRIGGER nl_no_financial_delete BEFORE DELETE ON rental_disputes FOR EACH ROW EXECUTE FUNCTION nl_immutable();

DROP TRIGGER IF EXISTS nl_no_financial_delete ON processed_webhooks;

CREATE TRIGGER nl_no_financial_delete BEFORE DELETE ON processed_webhooks FOR EACH ROW EXECUTE FUNCTION nl_immutable();

ALTER TABLE rental_bookings ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE rental_bookings FROM PUBLIC;

REVOKE ALL ON TABLE rental_bookings FROM anon;

REVOKE ALL ON TABLE rental_bookings FROM authenticated;

ALTER TABLE payment_transactions ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE payment_transactions FROM PUBLIC;

REVOKE ALL ON TABLE payment_transactions FROM anon;

REVOKE ALL ON TABLE payment_transactions FROM authenticated;

ALTER TABLE journal_transactions ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE journal_transactions FROM PUBLIC;

REVOKE ALL ON TABLE journal_transactions FROM anon;

REVOKE ALL ON TABLE journal_transactions FROM authenticated;

ALTER TABLE escrow_ledger_entries ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE escrow_ledger_entries FROM PUBLIC;

REVOKE ALL ON TABLE escrow_ledger_entries FROM anon;

REVOKE ALL ON TABLE escrow_ledger_entries FROM authenticated;

ALTER TABLE refund_intents ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE refund_intents FROM PUBLIC;

REVOKE ALL ON TABLE refund_intents FROM anon;

REVOKE ALL ON TABLE refund_intents FROM authenticated;

ALTER TABLE refund_attempts ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE refund_attempts FROM PUBLIC;

REVOKE ALL ON TABLE refund_attempts FROM anon;

REVOKE ALL ON TABLE refund_attempts FROM authenticated;

ALTER TABLE rental_disputes ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE rental_disputes FROM PUBLIC;

REVOKE ALL ON TABLE rental_disputes FROM anon;

REVOKE ALL ON TABLE rental_disputes FROM authenticated;

ALTER TABLE processed_webhooks ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE processed_webhooks FROM PUBLIC;

REVOKE ALL ON TABLE processed_webhooks FROM anon;

REVOKE ALL ON TABLE processed_webhooks FROM authenticated;

ALTER TABLE financial_audit_records ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE financial_audit_records FROM PUBLIC;

REVOKE ALL ON TABLE financial_audit_records FROM anon;

REVOKE ALL ON TABLE financial_audit_records FROM authenticated;

ALTER TABLE rental_evidence ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE rental_evidence FROM PUBLIC;

REVOKE ALL ON TABLE rental_evidence FROM anon;

REVOKE ALL ON TABLE rental_evidence FROM authenticated;

ALTER TABLE payment_schema_versions ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE payment_schema_versions FROM PUBLIC;

REVOKE ALL ON TABLE payment_schema_versions FROM anon;

REVOKE ALL ON TABLE payment_schema_versions FROM authenticated;

ALTER FUNCTION nl_snapshot_guard() SET search_path FROM CURRENT;

REVOKE ALL ON FUNCTION nl_snapshot_guard() FROM PUBLIC;

REVOKE ALL ON FUNCTION nl_snapshot_guard() FROM anon;

REVOKE ALL ON FUNCTION nl_snapshot_guard() FROM authenticated;

ALTER FUNCTION nl_immutable() SET search_path FROM CURRENT;

REVOKE ALL ON FUNCTION nl_immutable() FROM PUBLIC;

REVOKE ALL ON FUNCTION nl_immutable() FROM anon;

REVOKE ALL ON FUNCTION nl_immutable() FROM authenticated;

ALTER FUNCTION nl_journal_guard() SET search_path FROM CURRENT;

REVOKE ALL ON FUNCTION nl_journal_guard() FROM PUBLIC;

REVOKE ALL ON FUNCTION nl_journal_guard() FROM anon;

REVOKE ALL ON FUNCTION nl_journal_guard() FROM authenticated;

ALTER FUNCTION nl_line_guard() SET search_path FROM CURRENT;

REVOKE ALL ON FUNCTION nl_line_guard() FROM PUBLIC;

REVOKE ALL ON FUNCTION nl_line_guard() FROM anon;

REVOKE ALL ON FUNCTION nl_line_guard() FROM authenticated;

ALTER FUNCTION nl_terms_refund_intents() SET search_path FROM CURRENT;

REVOKE ALL ON FUNCTION nl_terms_refund_intents() FROM PUBLIC;

REVOKE ALL ON FUNCTION nl_terms_refund_intents() FROM anon;

REVOKE ALL ON FUNCTION nl_terms_refund_intents() FROM authenticated;

ALTER FUNCTION nl_terms_negotiation_offers() SET search_path FROM CURRENT;

REVOKE ALL ON FUNCTION nl_terms_negotiation_offers() FROM PUBLIC;

REVOKE ALL ON FUNCTION nl_terms_negotiation_offers() FROM anon;

REVOKE ALL ON FUNCTION nl_terms_negotiation_offers() FROM authenticated;

ALTER FUNCTION nl_terminal_guard() SET search_path FROM CURRENT;

REVOKE ALL ON FUNCTION nl_terminal_guard() FROM PUBLIC;

REVOKE ALL ON FUNCTION nl_terminal_guard() FROM anon;

REVOKE ALL ON FUNCTION nl_terminal_guard() FROM authenticated;

ALTER FUNCTION nl_decision_guard() SET search_path FROM CURRENT;

REVOKE ALL ON FUNCTION nl_decision_guard() FROM PUBLIC;

REVOKE ALL ON FUNCTION nl_decision_guard() FROM anon;

REVOKE ALL ON FUNCTION nl_decision_guard() FROM authenticated;

ALTER FUNCTION nl_booking_binding_guard() SET search_path FROM CURRENT;

REVOKE ALL ON FUNCTION nl_booking_binding_guard() FROM PUBLIC;

REVOKE ALL ON FUNCTION nl_booking_binding_guard() FROM anon;

REVOKE ALL ON FUNCTION nl_booking_binding_guard() FROM authenticated;

ALTER FUNCTION nl_payment_binding_guard() SET search_path FROM CURRENT;

REVOKE ALL ON FUNCTION nl_payment_binding_guard() FROM PUBLIC;

REVOKE ALL ON FUNCTION nl_payment_binding_guard() FROM anon;

REVOKE ALL ON FUNCTION nl_payment_binding_guard() FROM authenticated;

ALTER FUNCTION nl_refund_allocation_guard() SET search_path FROM CURRENT;

REVOKE ALL ON FUNCTION nl_refund_allocation_guard() FROM PUBLIC;

REVOKE ALL ON FUNCTION nl_refund_allocation_guard() FROM anon;

REVOKE ALL ON FUNCTION nl_refund_allocation_guard() FROM authenticated;

INSERT INTO payment_schema_versions(version) VALUES (3) ON CONFLICT(version) DO NOTHING;

COMMIT;
