"""Payment documents, consent and existing rating workflow regressions."""

import pytest
from sqlalchemy import select
from test_razorpay_escrow import call, fund, physical_return
from test_razorpay_escrow import flow as payment_flow

from app.models import User
from app.payment_models import EscrowLedgerEntry, FinancialAudit, JournalTransaction, RefundIntent
from app.services.payments import PaymentService

flow = payment_flow


def document(flow, suffix="receipt", role="borrower"):
    return flow["client"].get(
        f"/api/payments/bookings/{flow['booking']['id']}/{suffix}",
        headers=flow["headers"][role],
    )


def rate(flow, role="borrower", rating=5):
    target = "lender" if role == "borrower" else "borrower"
    return flow["client"].post(
        f"/api/borrow-requests/{flow['request_id']}/rate-{target}",
        headers=flow["headers"][role],
        json={"rating": rating, "comment": "Synthetic review"},
    )


def state(flow):
    return (
        flow["client"]
        .get(f"/api/payments/bookings/{flow['booking']['id']}", headers=flow["headers"]["borrower"])
        .json()
    )


def test_checkout_consent_and_verified_customer_prefill(flow):
    assert call(flow, "payments/create-order", {"accepted_terms": False}).status_code == 422
    assert call(flow, "payments/create-order", {"accepted_terms": "true"}).status_code == 422
    order = call(flow, "payments/create-order", {"accepted_terms": True})
    assert order.status_code == 200, order.text
    assert order.json()["prefill"] == {"name": "borrower", "email": "borrower@example.test"}
    call(flow, "payments/create-order", {"accepted_terms": True})
    with flow["factory"]() as db:
        audits = db.scalars(
            select(FinancialAudit).where(FinancialAudit.action == "checkout_terms_accepted")
        ).all()
        assert len(audits) == 1
        assert '"source": "checkout_confirmation"' in audits[0].details


def test_unverified_customer_information_is_not_prefilled(flow):
    # Issue the API token first; then change verification to exercise the service
    # without bypassing the existing HTTP verification requirement.
    with flow["factory"]() as db:
        db.get(User, flow["ids"]["borrower"]).is_verified = False
        db.commit()
        order = PaymentService(db, flow["provider"]).order(
            flow["booking"]["id"], flow["ids"]["borrower"]
        )
        assert order["prefill"] == {}


def test_receipt_requires_capture_and_booking_authorization(flow):
    assert document(flow).status_code == 409
    assert document(flow, role="other").status_code == 403
    path = f"/api/payments/bookings/{flow['booking']['id']}/receipt"
    assert flow["client"].get(path).status_code == 401
    fund(flow)
    response = document(flow)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "attachment;" in response.headers["content-disposition"]
    assert "sandbox" in response.headers["content-security-policy"]
    assert "TEST MODE" in response.text and "INR 900.00" in response.text
    assert "Provider payment reference" in response.text
    assert "Razorpay-issued document or tax invoice" in response.text
    assert "password" not in response.text
    assert document(flow, role="lender").status_code == 200
    assert document(flow, role="admin").status_code == 200


def test_document_html_escapes_names_and_never_includes_contact_details(flow):
    fund(flow)
    with flow["factory"]() as db:
        db.get(User, flow["ids"]["borrower"]).name = '<script>alert("x")</script>'
        db.commit()
    response = document(flow)
    assert "<script>" not in response.text and "&lt;script&gt;" in response.text
    assert "borrower@example.test" not in response.text


@pytest.mark.parametrize("deduction", [0, 10000, 50000])
def test_ratings_and_refund_document_require_completed_settlement(flow, deduction):
    fund(flow)
    assert rate(flow).status_code == 409
    physical_return(flow)
    assert (
        call(
            flow,
            "disputes/raise",
            {"claimed_deduction_paise": deduction, "reason": "Synthetic evidence review"},
            "lender",
        ).status_code
        == 200
    )
    assert (
        call(
            flow,
            "disputes/settle",
            {
                "approved_deduction_paise": deduction,
                "reason": "Independent human review",
                "claim_version": 1,
            },
            "admin",
        ).status_code
        == 200
    )
    assert not state(flow)["rating_eligible"]
    assert rate(flow).status_code == 409
    assert document(flow, "refund-acknowledgment").status_code == 409
    assert call(flow, "payments/refunds/reconcile").status_code == 200
    assert state(flow)["rating_eligible"]
    acknowledgment = document(flow, "refund-acknowledgment")
    assert acknowledgment.status_code == 200, acknowledgment.text
    assert "Approved compensation" in acknowledgment.text
    assert document(flow, "refund-acknowledgment", "other").status_code == 403
    assert rate(flow).status_code == 200
    assert rate(flow).status_code == 409
    assert rate(flow, "lender", 4).status_code == 200
    with flow["factory"]() as db:
        lender = db.get(User, flow["ids"]["lender"])
        borrower = db.get(User, flow["ids"]["borrower"])
        assert lender.rating_count == 1 and lender.avg_rating == 5
        assert borrower.rating_count == 1 and borrower.avg_rating == 4


def test_pending_refund_blocks_ratings_even_after_lender_confirms_return(flow):
    fund(flow)
    physical_return(flow)
    with flow["factory"]() as db:
        service = PaymentService(db, flow["provider"])
        service.return_decision(flow["booking"]["id"], flow["ids"]["lender"], True)
        service.execute_refund(flow["booking"]["id"], flow["ids"]["admin"], "pending", admin=True)
    assert not state(flow)["rating_eligible"]
    assert rate(flow).status_code == 409
    assert document(flow, "refund-acknowledgment").status_code == 409
    assert call(flow, "payments/refunds/reconcile").status_code == 200
    assert rate(flow).status_code == 200


def test_stale_admin_decision_does_not_allocate_refund(flow):
    fund(flow)
    physical_return(flow)
    for amount in [10000, 20000]:
        assert (
            call(
                flow,
                "disputes/raise",
                {"claimed_deduction_paise": amount, "reason": "Revised synthetic claim"},
                "lender",
            ).status_code
            == 200
        )
    for version in [None, 1]:
        payload = {"approved_deduction_paise": 10000, "reason": "Reviewed stale claim"}
        if version is not None:
            payload["claim_version"] = version
        assert call(flow, "disputes/settle", payload, "admin").status_code == 409
    with flow["factory"]() as db:
        assert db.scalar(select(RefundIntent)) is None
    assert (
        call(
            flow,
            "disputes/settle",
            {
                "approved_deduction_paise": 10000,
                "reason": "Reviewed current claim",
                "claim_version": 2,
            },
            "admin",
        ).status_code
        == 200
    )


def test_unposted_journal_does_not_change_reconciled_deposit(flow):
    fund(flow)
    with flow["factory"]() as db:
        journal = JournalTransaction(
            booking_id=flow["booking"]["id"],
            reference="synthetic-draft",
            status="draft",
            debit_paise=100,
            credit_paise=100,
        )
        db.add(journal)
        db.flush()
        for side, account in [("DEBIT", "gateway_clearing"), ("CREDIT", "escrow_deposit_held")]:
            db.add(
                EscrowLedgerEntry(
                    journal_id=journal.id,
                    booking_id=flow["booking"]["id"],
                    account_type=account,
                    entry_type=side,
                    amount_paise=100,
                    description="Unposted synthetic draft",
                )
            )
        db.commit()
    result = state(flow)
    assert result["held_deposit_paise"] == 50000
    assert result["reconciliation"]["balanced"]
    assert result["reconciliation"]["remaining_liability_paise"] == 50000
