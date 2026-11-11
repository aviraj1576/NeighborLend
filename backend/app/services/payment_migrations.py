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

    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in TABLES])
    with engine.begin() as c:
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
