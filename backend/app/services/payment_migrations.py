"""Additive financial tables and immutable balanced-posting guards."""

from sqlalchemy import inspect

from app.payment_models import Base

TABLES = (
    "rental_bookings",
    "payment_transactions",
    "journal_transactions",
    "escrow_ledger_entries",
    "refund_intents",
    "refund_attempts",
    "rental_disputes",
    "processed_webhooks",
    "financial_audit_records",
    "rental_evidence",
)


def migrate_payments(engine):
    from app import models  # noqa: F401 - resolve all referenced existing metadata tables.

    with engine.begin() as c:
        Base.metadata.create_all(c, tables=[Base.metadata.tables[name] for name in TABLES])
        additions = {
            "payment_transactions": {
                "razorpay_refund_id": "VARCHAR(128)",
                "operation_version": "INTEGER NOT NULL DEFAULT 1",
            },
            "refund_intents": {"active_attempt_id": "VARCHAR(36)"},
            "rental_disputes": {
                "initiated_by": "VARCHAR",
                "origin": "VARCHAR(32) NOT NULL DEFAULT 'lender_claim'",
                "resolution_reason": "TEXT",
                "claim_version": "INTEGER NOT NULL DEFAULT 1",
            },
            "negotiation_offers": {
                "borrower_id_snapshot": "VARCHAR",
                "lender_id_snapshot": "VARCHAR",
                "daily_rate_paise": "BIGINT",
                "rental_fee_paise": "BIGINT",
                "security_deposit_paise": "BIGINT",
                "total_amount_paise": "BIGINT",
            },
            "borrow_requests": {"handover_condition_note": "TEXT", "return_condition_note": "TEXT"},
            "refund_attempts": {
                "provider_refund_id": "VARCHAR(128)",
                "idempotency_key": "VARCHAR(128)",
            },
        }
        for table, definitions in additions.items():
            if not inspect(c).has_table(table):
                continue
            columns = {column["name"] for column in inspect(c).get_columns(table)}
            for name, definition in definitions.items():
                if name not in columns:
                    c.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        c.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_payment_refund_unique ON payment_transactions (razorpay_refund_id)"
        )
        if c.dialect.name == "sqlite":
            fields = (
                "borrow_request_id",
                "offer_id",
                "listing_id",
                "borrower_id",
                "lender_id",
                "start_date",
                "end_date",
                "duration_days",
                "daily_rate_paise",
                "rental_fee_paise",
                "security_deposit_paise",
                "total_amount_paise",
                "currency",
                "provider",
            )
            changed = " OR ".join(f"OLD.{name} IS NOT NEW.{name}" for name in fields)
            c.exec_driver_sql(
                f"CREATE TRIGGER IF NOT EXISTS immutable_booking_snapshot BEFORE UPDATE ON rental_bookings WHEN {changed} BEGIN SELECT RAISE(ABORT,'immutable booking snapshot'); END"
            )
            for table in ("escrow_ledger_entries", "financial_audit_records", "rental_evidence"):
                for action in ("UPDATE", "DELETE"):
                    c.exec_driver_sql(
                        f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'append-only financial records'); END"
                    )
            c.exec_driver_sql("""CREATE TRIGGER IF NOT EXISTS journal_guard BEFORE UPDATE ON journal_transactions BEGIN
              SELECT CASE WHEN OLD.status!='draft' OR NEW.status!='posted' OR OLD.id!=NEW.id
                OR OLD.reference!=NEW.reference OR OLD.booking_id!=NEW.booking_id
                OR OLD.debit_paise!=NEW.debit_paise OR OLD.credit_paise!=NEW.credit_paise
                THEN RAISE(ABORT,'immutable journal') END;
              SELECT CASE WHEN NEW.debit_paise!=(SELECT COALESCE(SUM(amount_paise),0) FROM escrow_ledger_entries WHERE journal_id=NEW.id AND entry_type='DEBIT')
                OR NEW.credit_paise!=(SELECT COALESCE(SUM(amount_paise),0) FROM escrow_ledger_entries WHERE journal_id=NEW.id AND entry_type='CREDIT')
                THEN RAISE(ABORT,'unbalanced journal') END; END""")
            c.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS journal_insert_guard BEFORE INSERT ON journal_transactions WHEN NEW.status!='draft' BEGIN SELECT RAISE(ABORT,'journal must start draft'); END"
            )
            c.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS journal_delete_guard BEFORE DELETE ON journal_transactions BEGIN SELECT RAISE(ABORT,'append-only journal'); END"
            )
            c.exec_driver_sql("""CREATE TRIGGER IF NOT EXISTS line_insert_guard BEFORE INSERT ON escrow_ledger_entries
              WHEN NOT EXISTS(SELECT 1 FROM journal_transactions WHERE id=NEW.journal_id AND booking_id=NEW.booking_id AND status='draft')
              BEGIN SELECT RAISE(ABORT,'invalid journal line'); END""")
        elif c.dialect.name == "postgresql":
            c.exec_driver_sql("""CREATE OR REPLACE FUNCTION nl_snapshot_guard() RETURNS trigger AS $$ BEGIN
              IF ROW(OLD.borrow_request_id,OLD.offer_id,OLD.listing_id,OLD.borrower_id,OLD.lender_id,OLD.start_date,OLD.end_date,OLD.duration_days,OLD.daily_rate_paise,OLD.rental_fee_paise,OLD.security_deposit_paise,OLD.total_amount_paise,OLD.currency,OLD.provider)
                IS DISTINCT FROM ROW(NEW.borrow_request_id,NEW.offer_id,NEW.listing_id,NEW.borrower_id,NEW.lender_id,NEW.start_date,NEW.end_date,NEW.duration_days,NEW.daily_rate_paise,NEW.rental_fee_paise,NEW.security_deposit_paise,NEW.total_amount_paise,NEW.currency,NEW.provider)
              THEN RAISE EXCEPTION 'immutable booking snapshot'; END IF;
              RETURN NEW; END; $$ LANGUAGE plpgsql""")
            c.exec_driver_sql("DROP TRIGGER IF EXISTS nl_snapshot_guard ON rental_bookings")
            c.exec_driver_sql(
                "CREATE TRIGGER nl_snapshot_guard BEFORE UPDATE ON rental_bookings FOR EACH ROW EXECUTE FUNCTION nl_snapshot_guard()"
            )
            c.exec_driver_sql("""CREATE OR REPLACE FUNCTION nl_immutable() RETURNS trigger AS $$
              BEGIN RAISE EXCEPTION 'append-only financial records'; END; $$ LANGUAGE plpgsql""")
            for table in ("escrow_ledger_entries", "financial_audit_records", "rental_evidence"):
                c.exec_driver_sql(f"DROP TRIGGER IF EXISTS nl_immutable ON {table}")
                c.exec_driver_sql(
                    f"CREATE TRIGGER nl_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION nl_immutable()"
                )
            c.exec_driver_sql("""CREATE OR REPLACE FUNCTION nl_journal_guard() RETURNS trigger AS $$ BEGIN
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
              RETURN NEW; END; $$ LANGUAGE plpgsql""")
            c.exec_driver_sql("DROP TRIGGER IF EXISTS nl_journal_guard ON journal_transactions")
            c.exec_driver_sql(
                "CREATE TRIGGER nl_journal_guard BEFORE INSERT OR UPDATE OR DELETE ON journal_transactions FOR EACH ROW EXECUTE FUNCTION nl_journal_guard()"
            )
            c.exec_driver_sql("""CREATE OR REPLACE FUNCTION nl_line_guard() RETURNS trigger AS $$ BEGIN
              PERFORM id FROM journal_transactions WHERE id=NEW.journal_id AND booking_id=NEW.booking_id AND status='draft' FOR UPDATE;
              IF NOT FOUND THEN RAISE EXCEPTION 'invalid journal line'; END IF;
              RETURN NEW; END; $$ LANGUAGE plpgsql""")
            c.exec_driver_sql("DROP TRIGGER IF EXISTS nl_line_guard ON escrow_ledger_entries")
            c.exec_driver_sql(
                "CREATE TRIGGER nl_line_guard BEFORE INSERT ON escrow_ledger_entries FOR EACH ROW EXECUTE FUNCTION nl_line_guard()"
            )
        # Version 2: immutable authorized allocation and negotiated financial terms.
        guards = {
            "refund_intents": (
                "booking_id",
                "amount_paise",
                "deduction_paise",
                "kind",
                "authorized_by",
            ),
            "negotiation_offers": (
                "listing_id",
                "conversation_id",
                "sender_id",
                "start_date",
                "end_date",
                "daily_price",
                "total_cost",
                "borrower_id_snapshot",
                "lender_id_snapshot",
                "daily_rate_paise",
                "rental_fee_paise",
                "security_deposit_paise",
                "total_amount_paise",
            ),
        }
        for table, fields in guards.items():
            if not inspect(c).has_table(table):
                continue
            if c.dialect.name == "sqlite":
                changed = " OR ".join(f"OLD.{name} IS NOT NEW.{name}" for name in fields)
                c.exec_driver_sql(
                    f"CREATE TRIGGER IF NOT EXISTS nl_terms_{table} BEFORE UPDATE ON {table} WHEN {changed} BEGIN SELECT RAISE(ABORT,'immutable financial terms'); END"
                )
            elif c.dialect.name == "postgresql":
                before = ",".join(f"OLD.{name}" for name in fields)
                after = ",".join(f"NEW.{name}" for name in fields)
                c.exec_driver_sql(
                    f"CREATE OR REPLACE FUNCTION nl_terms_{table}() RETURNS trigger AS $$ BEGIN IF ROW({before}) IS DISTINCT FROM ROW({after}) THEN RAISE EXCEPTION 'immutable financial terms'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql"
                )
                c.exec_driver_sql(f"DROP TRIGGER IF EXISTS nl_terms ON {table}")
                c.exec_driver_sql(
                    f"CREATE TRIGGER nl_terms BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION nl_terms_{table}()"
                )
        c.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS payment_schema_versions (version INTEGER PRIMARY KEY)"
        )
        c.exec_driver_sql(
            "INSERT INTO payment_schema_versions(version) VALUES (2) ON CONFLICT(version) DO NOTHING"
        )
        if c.dialect.name == "sqlite":
            c.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS nl_capture_monotonic BEFORE UPDATE ON rental_bookings WHEN OLD.payment_status='captured' AND NEW.payment_status!='captured' BEGIN SELECT RAISE(ABORT,'confirmed capture cannot regress'); END"
            )
            c.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS nl_refund_monotonic BEFORE UPDATE ON refund_intents WHEN OLD.status='processed' AND NEW.status!='processed' BEGIN SELECT RAISE(ABORT,'confirmed refund cannot regress'); END"
            )
            c.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS nl_decision_immutable BEFORE UPDATE ON rental_disputes WHEN OLD.resolved_at IS NOT NULL AND (OLD.approved_deduction_paise IS NOT NEW.approved_deduction_paise OR OLD.resolved_by IS NOT NEW.resolved_by OR OLD.resolved_at IS NOT NEW.resolved_at OR OLD.resolution_reason IS NOT NEW.resolution_reason OR OLD.status IS NOT NEW.status) BEGIN SELECT RAISE(ABORT,'immutable dispute decision'); END"
            )
        elif c.dialect.name == "postgresql":
            c.exec_driver_sql("""CREATE OR REPLACE FUNCTION nl_terminal_guard() RETURNS trigger AS $$ BEGIN
              IF TG_TABLE_NAME='rental_bookings' THEN
                IF OLD.payment_status='captured' AND NEW.payment_status!='captured' THEN RAISE EXCEPTION 'confirmed capture cannot regress'; END IF;
              ELSE
                IF OLD.status='processed' AND NEW.status!='processed' THEN RAISE EXCEPTION 'confirmed refund cannot regress'; END IF;
              END IF; RETURN NEW; END; $$ LANGUAGE plpgsql""")
            for table in ("rental_bookings", "refund_intents"):
                c.exec_driver_sql(f"DROP TRIGGER IF EXISTS nl_terminal_guard ON {table}")
                c.exec_driver_sql(
                    f"CREATE TRIGGER nl_terminal_guard BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION nl_terminal_guard()"
                )
            c.exec_driver_sql("""CREATE OR REPLACE FUNCTION nl_decision_guard() RETURNS trigger AS $$ BEGIN
              IF OLD.resolved_at IS NOT NULL AND ROW(OLD.approved_deduction_paise,OLD.resolved_by,OLD.resolved_at,OLD.resolution_reason,OLD.status) IS DISTINCT FROM ROW(NEW.approved_deduction_paise,NEW.resolved_by,NEW.resolved_at,NEW.resolution_reason,NEW.status) THEN RAISE EXCEPTION 'immutable dispute decision'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql""")
            c.exec_driver_sql("DROP TRIGGER IF EXISTS nl_decision_guard ON rental_disputes")
            c.exec_driver_sql(
                "CREATE TRIGGER nl_decision_guard BEFORE UPDATE ON rental_disputes FOR EACH ROW EXECUTE FUNCTION nl_decision_guard()"
            )
        _financial_v3(c)


def _financial_v3(c):
    """Extend the existing migration history; no business record is backfilled."""
    c.exec_driver_sql("""CREATE UNIQUE INDEX IF NOT EXISTS nl_one_capture_per_booking
        ON payment_transactions(booking_id) WHERE transaction_type='payment' AND status='captured'""")
    c.exec_driver_sql("""CREATE UNIQUE INDEX IF NOT EXISTS nl_order_provider_unique
        ON payment_transactions(razorpay_order_id) WHERE transaction_type='order'""")
    c.exec_driver_sql("""CREATE INDEX IF NOT EXISTS nl_refund_reconciliation
        ON refund_intents(status,created_at)""")
    c.exec_driver_sql("""CREATE INDEX IF NOT EXISTS nl_dispute_review
        ON rental_disputes(status,created_at)""")
    if c.dialect.name == "postgresql":
        c.exec_driver_sql("""CREATE OR REPLACE FUNCTION nl_booking_binding_guard() RETURNS trigger
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
            END; $$""")
        c.exec_driver_sql("DROP TRIGGER IF EXISTS nl_booking_binding_guard ON rental_bookings")
        c.exec_driver_sql("""CREATE TRIGGER nl_booking_binding_guard BEFORE INSERT
            ON rental_bookings FOR EACH ROW EXECUTE FUNCTION nl_booking_binding_guard()""")
        c.exec_driver_sql("""CREATE OR REPLACE FUNCTION nl_payment_binding_guard() RETURNS trigger
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
            END; $$""")
        c.exec_driver_sql("DROP TRIGGER IF EXISTS nl_payment_binding_guard ON payment_transactions")
        c.exec_driver_sql("""CREATE TRIGGER nl_payment_binding_guard BEFORE INSERT OR UPDATE
            ON payment_transactions FOR EACH ROW EXECUTE FUNCTION nl_payment_binding_guard()""")
        c.exec_driver_sql("""CREATE OR REPLACE FUNCTION nl_refund_allocation_guard() RETURNS trigger
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
            END; $$""")
        c.exec_driver_sql("DROP TRIGGER IF EXISTS nl_refund_allocation_guard ON refund_intents")
        c.exec_driver_sql("""CREATE TRIGGER nl_refund_allocation_guard BEFORE INSERT OR UPDATE
            ON refund_intents FOR EACH ROW EXECUTE FUNCTION nl_refund_allocation_guard()""")
        for table in (
            "payment_transactions",
            "refund_intents",
            "rental_disputes",
            "processed_webhooks",
        ):
            c.exec_driver_sql(f"DROP TRIGGER IF EXISTS nl_no_financial_delete ON {table}")
            c.exec_driver_sql(
                f"CREATE TRIGGER nl_no_financial_delete BEFORE DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION nl_immutable()"
            )
        for table in (*TABLES, "payment_schema_versions"):
            # App JWT subjects are varchar IDs, not Supabase auth.uid(). Financial
            # records are served exclusively by the authenticated backend API.
            c.exec_driver_sql(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            c.exec_driver_sql(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
            for role in ("anon", "authenticated"):
                if c.exec_driver_sql("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).scalar():
                    c.exec_driver_sql(f"REVOKE ALL ON TABLE {table} FROM {role}")
        # Pin all existing trigger functions to the migration's resolved schema.
        functions = (
            c.exec_driver_sql("""SELECT p.proname FROM pg_proc p
            JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=current_schema()
            AND left(p.proname,3)='nl_' AND p.prorettype='trigger'::regtype""")
            .scalars()
            .all()
        )
        for name in functions:
            quoted = c.dialect.identifier_preparer.quote(name)
            c.exec_driver_sql(f"ALTER FUNCTION {quoted}() SET search_path FROM CURRENT")
            c.exec_driver_sql(f"REVOKE ALL ON FUNCTION {quoted}() FROM PUBLIC")
            for role in ("anon", "authenticated"):
                if c.exec_driver_sql("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).scalar():
                    c.exec_driver_sql(f"REVOKE ALL ON FUNCTION {quoted}() FROM {role}")
    c.exec_driver_sql(
        "INSERT INTO payment_schema_versions(version) VALUES (3) ON CONFLICT(version) DO NOTHING"
    )
