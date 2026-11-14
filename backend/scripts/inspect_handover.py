"""Read-only investigation of the authorized test rental; no state transitions."""
import argparse
import json
import logging
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / ".test-tools"), str(ROOT)]
REQUEST_ID = "38af43ff-454f-4413-beda-6f84c9a4034f"
STAGE = "configuration"


def main():
    global STAGE
    logging.disable(logging.CRITICAL)
    from sqlalchemy import create_engine, select, text
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.models import BorrowRequest, User
    from app.payment_models import EscrowLedgerEntry, PaymentTransaction, RentalBooking
    from app.services.razorpay_service import configured_provider
    from scripts.provision_fictional_accounts import PRIVATE, inputs, validate_target

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-views", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    validate_target(settings)
    engine = create_engine(settings.database_url, hide_parameters=True,
                           connect_args={"connect_timeout": 15, "sslmode": "require"})
    STAGE = "database_read"
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN READ ONLY")
        with Session(bind=connection) as db:
            rental = db.get(BorrowRequest, REQUEST_ID)
            booking = db.scalar(select(RentalBooking).where(RentalBooking.borrow_request_id == REQUEST_ID))
            if rental is None or booking is None:
                raise RuntimeError("Rental or booking missing")
            payment = db.scalar(select(PaymentTransaction).where(
                PaymentTransaction.booking_id == booking.id,
                PaymentTransaction.transaction_type == "payment",
                PaymentTransaction.status == "captured",
            ))
            # Snapshot only hashes/counts, never payment IDs or raw provider data.
            snapshot = {}
            for table in ("borrow_requests", "rental_bookings", "payment_transactions", "journal_transactions",
                          "escrow_ledger_entries", "refund_intents", "refund_attempts", "rental_disputes",
                          "processed_webhooks", "financial_audit_records", "rental_evidence"):
                snapshot[table] = dict(connection.execute(text(
                    "SELECT count(*) AS count, md5(COALESCE(string_agg(md5(row_to_json(t)::text), '' "
                    f"ORDER BY md5(row_to_json(t)::text)), '')) AS digest FROM public.{table} t"
                )).mappings().one())
            lines = db.scalars(select(EscrowLedgerEntry).where(EscrowLedgerEntry.booking_id == booking.id)).all()
            result = {
                "request_status": rental.status.value, "handover_status": rental.handover_status,
                "listing_present": rental.listing_id is not None,
                "borrower_is_aarav": db.get(User, rental.borrower_id).username == "aarav_mehta",
                "lender_is_rohan": rental.listing.owner.username == "rohan_kapoor",
                "lender_username": rental.listing.owner.username,
                "booking_lender_matches_listing_owner": booking.lender_id == rental.listing.owner_id,
                "booking_status": booking.booking_status, "payment_status": booking.payment_status,
                "provider": booking.provider, "rental_fee_paise": booking.rental_fee_paise,
                "deposit_paise": booking.security_deposit_paise, "total_paise": booking.total_amount_paise,
                "ledger_debits_paise": sum(row.amount_paise for row in lines if row.entry_type == "DEBIT"),
                "ledger_credits_paise": sum(row.amount_paise for row in lines if row.entry_type == "CREDIT"),
                "ledger_lines": len(lines), "captured_payment_record": payment is not None,
            }
            if payment is not None:
                STAGE = "razorpay_read_only_get"
                provider = configured_provider(settings)
                actual = provider.fetch_payment(payment.razorpay_payment_id)
                order = provider.fetch_order(payment.razorpay_order_id)
                result["razorpay_get_verified"] = (
                    actual.get("status") == "captured" and actual.get("captured") is True
                    and actual.get("amount") == booking.total_amount_paise
                    and actual.get("currency") == "INR"
                    and actual.get("order_id") == payment.razorpay_order_id
                    and order.get("status") == "paid" and order.get("amount_paid") == booking.total_amount_paise
                )
            before = PRIVATE / "handover-readonly-before.json"
            if not before.exists():
                before.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
            result["database_snapshot_unchanged"] = json.loads(before.read_text()) == snapshot
            (PRIVATE / "handover-readonly-latest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            expected_ids = {"aarav_mehta": rental.borrower_id, rental.listing.owner.username: rental.listing.owner_id}
        connection.rollback()
    opener = build_opener(ProxyHandler({}))
    print(json.dumps(result, indent=2), flush=True)
    if not args.backend_views:
        engine.dispose()
        return
    def request(path, payload=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        with opener.open(Request("http://127.0.0.1:8000/api/" + path,
                                 data=json.dumps(payload).encode() if payload else None,
                                 headers=headers), timeout=30) as response:
            return json.load(response)
    result["interfaces"] = []
    for record in inputs():
        STAGE = "backend_view_" + record["username"]
        STAGE += "_login"
        token = request("auth/login", {"username_or_email": record["username"],
                                       "password": record["password"]})["access_token"]
        STAGE = "backend_rental_" + record["username"]
        try:
            rental_view = request(f"payments/requests/{REQUEST_ID}/rental", token=token)
        except HTTPError as exc:
            if record["username"] not in expected_ids and exc.code == 403:
                result["interfaces"].append({"username": record["username"], "nonparticipant_denied": True})
                exc.close()
                continue
            raise
        handover = request(f"borrow-requests/{REQUEST_ID}/handover", token=token)
        view = request(f"payments/by-request/{REQUEST_ID}", token=token)
        result["interfaces"].append({
            "username": record["username"], "handover_status": handover["handover_status"],
            "identity_matches": request("auth/me", token=token)["id"] == expected_ids[record["username"]],
            "lender_id_present": bool(rental_view.get("lender_id")),
            "handover_unlocked": view.get("handover_unlocked"),
            "operations_enabled": view.get("operations_enabled"),
        })
    before = PRIVATE / "handover-readonly-before.json"
    current = PRIVATE / "handover-readonly-latest.json"
    if not before.exists():
        before.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    result["database_snapshot_unchanged"] = json.loads(before.read_text()) == snapshot
    current.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Read-only inspection failed at " + STAGE + " (" + type(exc).__name__ + "); sensitive details suppressed.", file=sys.stderr)
        sys.exit(1)
