"""GET-only gateway and READ ONLY PostgreSQL inspection; never dispatch/reconcile."""
import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / ".test-tools"), str(ROOT)]
REQUEST_ID = "38af43ff-454f-4413-beda-6f84c9a4034f"


def check_local_api(expected_booking_id):
    """Only credential authentication and GETs; no financial POST is permitted."""
    import httpx

    from scripts.provision_fictional_accounts import inputs

    result = {}
    with httpx.Client(base_url="http://127.0.0.1:8000/api", timeout=30, trust_env=False,
                      follow_redirects=False) as client:
        for account in inputs():
            response = client.post("/auth/login", json={
                "username_or_email": account["username"], "password": account["password"],
            })
            if response.status_code != 200:
                raise RuntimeError("Local authentication failed")
            data = response.json()
            headers = {"Authorization": "Bearer " + data["access_token"]}
            me = client.get("/auth/me", headers=headers)
            if me.status_code != 200 or me.json()["username"] != account["username"]:
                raise RuntimeError("Local identity mismatch")
            view = client.get("/payments/by-request/" + REQUEST_ID, headers=headers)
            expected = 403 if account["username"] == "rohan_kapoor" else 200
            if view.status_code != expected:
                raise RuntimeError("Local rental authorization mismatch")
            summary = {"login_status": response.status_code, "identity_verified": True,
                       "admin": me.json()["is_admin"], "rental_read_status": view.status_code}
            if expected == 200:
                booking = view.json()
                if booking["id"] != expected_booking_id or booking["provider"] != "razorpay_test":
                    raise RuntimeError("Local API database target mismatch")
                summary["refund_status"] = booking["refund"]["status"]
                for name in ("receipt", "refund-acknowledgment"):
                    document = client.get(f"/payments/bookings/{expected_booking_id}/{name}",
                                          headers=headers)
                    summary[name + "_status"] = document.status_code
            result[account["username"]] = summary
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-local-api", action="store_true")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    from sqlalchemy import MetaData, create_engine, select
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.models import BorrowRequest, User
    from app.payment_models import (
        FinancialAudit,
        PaymentTransaction,
        ProcessedWebhook,
        RefundAttempt,
        RefundIntent,
        RentalBooking,
        RentalDispute,
    )
    from app.services.payments import PaymentService
    from app.services.razorpay_service import configured_provider
    from scripts.provision_fictional_accounts import PRIVATE, fingerprints, validate_target

    settings = get_settings()
    validate_target(settings)
    engine = create_engine(settings.database_url, hide_parameters=True,
                           connect_args={"connect_timeout": 15, "sslmode": "require"})
    provider = configured_provider(settings)
    original = provider._request

    def get_only(method, path, payload=None, idempotency=None):
        if method != "GET" or payload is not None:
            raise RuntimeError("Non-GET gateway operation forbidden")
        return original(method, path, payload, idempotency)

    provider._request = get_only
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN READ ONLY")
        connection.exec_driver_sql("SET LOCAL statement_timeout='30s'")
        metadata = MetaData(schema="public")
        metadata.reflect(bind=connection)
        snapshot = fingerprints(connection, metadata)
        with Session(bind=connection) as db:
            request = db.get(BorrowRequest, REQUEST_ID)
            booking = db.scalar(select(RentalBooking).where(RentalBooking.borrow_request_id == REQUEST_ID))
            if request is None or booking is None:
                raise RuntimeError("Rental not found")
            intent = db.scalar(select(RefundIntent).where(RefundIntent.booking_id == booking.id))
            attempts = db.scalars(select(RefundAttempt).where(RefundAttempt.refund_id == intent.id)
                                 .order_by(RefundAttempt.created_at)) .all() if intent else []
            dispute = db.scalar(select(RentalDispute).where(RentalDispute.booking_id == booking.id))
            payment = db.scalar(select(PaymentTransaction).where(
                PaymentTransaction.booking_id == booking.id, PaymentTransaction.transaction_type == "payment",
                PaymentTransaction.status == "captured"))
            view = PaymentService(db, provider).view(booking)
            journal_balances = {}
            for line in view["journal"]:
                journal_balances.setdefault(line["journal_id"], 0)
                journal_balances[line["journal_id"]] += line["amount_paise"] * (
                    1 if line["side"] == "DEBIT" else -1
                )
            booking_id = booking.id
            report = {
                "request_status": request.status.value, "handover_status": request.handover_status,
                "borrower_return_reported": request.returned_at is not None,
                "lender_return_confirmed": request.return_confirmed_at is not None,
                "return_photos_count": len(json.loads(request.return_photos or "[]")),
                "borrower_username": db.get(User, booking.borrower_id).username,
                "lender_username": db.get(User, booking.lender_id).username,
                "booking_status": booking.booking_status, "payment_status": booking.payment_status,
                "deposit_state": booking.deposit_state, "settlement_kind": booking.settlement_kind,
                "rental_fee_paise": booking.rental_fee_paise, "deposit_paise": booking.security_deposit_paise,
                "total_captured_paise": booking.total_amount_paise, "refunded_deposit_paise": booking.refunded_paise,
                "deduction_paise": booking.deduction_paise, "operations_enabled": view["operations_enabled"],
                "reconciliation": view["reconciliation"],
                "posted_journal_count": len(journal_balances),
                "all_posted_journals_balanced": all(value == 0 for value in journal_balances.values()),
                "financial_transactions": [
                    {"kind": row.transaction_type, "status": row.status, "amount_paise": row.amount_paise}
                    for row in db.scalars(select(PaymentTransaction).where(
                        PaymentTransaction.booking_id == booking.id)).all()
                ],
                "dispute": None if dispute is None else {"status": dispute.status, "origin": dispute.origin},
                "refund_intent": None if intent is None else {
                    "kind": intent.kind, "status": intent.status, "amount_paise": intent.amount_paise,
                    "deduction_paise": intent.deduction_paise, "error_code": intent.error_code,
                    "provider_reference_present": bool(intent.provider_refund_id),
                    "authorized_by_username": db.get(User, intent.authorized_by).username,
                },
                "attempts": [{"status": row.status, "provider_reference_present": bool(row.provider_refund_id),
                              "error_code": row.error_code} for row in attempts],
                "distinct_attempt_provider_refund_count": len({row.provider_refund_id for row in attempts
                                                              if row.provider_refund_id}),
                "refund_webhook_receipts": [
                    {"event_type": row.event_type, "status": row.status}
                    for row in db.scalars(select(ProcessedWebhook).where(
                        ProcessedWebhook.event_type.like("refund.%"))).all()
                    if intent and intent.provider_refund_id and intent.provider_refund_id in row.payload
                ],
                "audit_actions": [row.action for row in db.scalars(select(FinancialAudit).where(
                    FinancialAudit.booking_id == booking.id).order_by(FinancialAudit.created_at)).all()],
            }
            gateway_payment = provider.fetch_payment(payment.razorpay_payment_id)
            report["gateway_payment"] = {
                "status": gateway_payment.get("status"), "captured": gateway_payment.get("captured"),
                "amount_paise": gateway_payment.get("amount"), "currency": gateway_payment.get("currency"),
                "refunded_paise": gateway_payment.get("amount_refunded"),
            }
            report["gateway_capture_matches_booking"] = (
                gateway_payment.get("status") == "captured"
                and gateway_payment.get("captured") is True
                and gateway_payment.get("amount") == booking.total_amount_paise == payment.amount_paise
                and gateway_payment.get("currency") == booking.currency == "INR"
            )
            report["unrefunded_capture_paise"] = (
                gateway_payment["amount"] - gateway_payment["amount_refunded"]
            )
            refunds = []
            complete = False
            for offset in range(0, 1000, 100):
                rows = provider.collection(provider._request("GET", "payments/" + provider.identifier(
                    payment.razorpay_payment_id, "pay") + f"/refunds?count=100&skip={offset}"))
                refunds.extend(rows)
                if len(rows) < 100:
                    complete = True
                    break
            report["gateway_refund_inventory_complete"] = complete
            report["gateway_refunds"] = [
                {"status": row.get("status"), "amount_paise": row.get("amount"), "currency": row.get("currency"),
                 "speed_requested": row.get("speed_requested"), "speed_processed": row.get("speed_processed"),
                 "created_at_unix": row.get("created_at"), "error_code": row.get("error_code"),
                 "acquirer_reference_present": any((row.get("acquirer_data") or {}).values()),
                 "matches_current_intent": intent is not None and row.get("receipt") == intent.idempotency_key,
                 "matches_payment": row.get("payment_id") == payment.razorpay_payment_id}
                for row in refunds
            ]
            for row in attempts:
                if row.provider_refund_id and not any(item.get("id") == row.provider_refund_id for item in refunds):
                    actual = provider.fetch_refund(row.provider_refund_id)
                    report.setdefault("additional_attempt_refund_verifications", []).append({
                        "status": actual.get("status"), "amount_paise": actual.get("amount"),
                        "matches_payment": actual.get("payment_id") == payment.razorpay_payment_id,
                    })
        connection.rollback()
    if args.check_local_api:
        report["local_port_8000"] = check_local_api(booking_id)
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN READ ONLY")
            connection.exec_driver_sql("SET LOCAL statement_timeout='30s'")
            report["hosted_records_unchanged_after_local_auth_checks"] = (
                fingerprints(connection, metadata) == snapshot
            )
            connection.rollback()
    baseline = PRIVATE / "refund-debug-before.json"
    if not baseline.exists():
        baseline.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    report["hosted_records_unchanged_since_debug_start"] = json.loads(baseline.read_text()) == snapshot
    (PRIVATE / "refund-debug-latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Read-only refund inspection stopped (" + type(exc).__name__ + "); sensitive details suppressed.", file=sys.stderr)
        sys.exit(1)
