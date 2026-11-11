"""Damage-claim regressions use disposable fixtures and no gateway transport."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select
from test_razorpay_escrow import assert_balanced, call, physical_return
from test_razorpay_escrow import flow as payment_flow

from app.payment_models import FinancialAudit, JournalTransaction, RentalDispute
from app.services.payments import PaymentService

flow = payment_flow


def returned(flow):
    assert call(flow, "payments/create-order").status_code == 200
    assert call(flow, "payments/mock-confirm").status_code == 200
    physical_return(flow)


def reject(flow):
    return flow["client"].post(
        "/api/borrow-requests/" + flow["request_id"] + "/return/confirm",
        json={"approved": False, "condition_note": "Casing damage for human review"},
        headers=flow["headers"]["lender"],
    )


@pytest.mark.parametrize("flow", ["realistic"], indirect=True)
def test_identical_claim_retry_acknowledges_one_durable_version_and_audit(flow):
    returned(flow)
    assert reject(flow).status_code == 200
    data = {"claimed_deduction_paise": 60000, "reason": "Return damage shown in photographs"}
    first = call(flow, "disputes/raise", data, "lender")
    second = call(flow, "disputes/raise", data, "lender")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["status"] == "raised"
    assert first.json()["claimed_deduction_paise"] == 60000
    assert first.json()["approved_deduction_paise"] is None
    with flow["factory"]() as db:
        assert len(db.scalars(select(RentalDispute)).all()) == 1
        assert (
            len(
                db.scalars(
                    select(FinancialAudit).where(FinancialAudit.action == "claim_submitted")
                ).all()
            )
            == 1
        )
    state = (
        flow["client"]
        .get("/api/payments/bookings/" + flow["booking"]["id"], headers=flow["headers"]["lender"])
        .json()
    )
    assert state["deposit_state"] == "frozen" and state["deduction_paise"] == 0
    assert state["refund"] is None and state["held_deposit_paise"] == 200000
    assert_balanced(flow)


def test_duplicate_return_rejection_does_not_repeat_decision_or_freeze(flow):
    returned(flow)
    assert reject(flow).status_code == reject(flow).status_code == 200
    with flow["factory"]() as db:
        assert (
            len(
                db.scalars(
                    select(FinancialAudit).where(FinancialAudit.action == "return_rejected")
                ).all()
            )
            == 1
        )
        assert (
            len(
                db.scalars(
                    select(JournalTransaction).where(JournalTransaction.reference.like("freeze:%"))
                ).all()
            )
            == 1
        )


@pytest.mark.parametrize("flow", ["realistic"], indirect=True)
def test_concurrent_identical_claims_are_one_version_then_real_revision_increments(flow):
    returned(flow)
    assert reject(flow).status_code == 200

    def submit(_):
        with flow["factory"]() as db:
            return PaymentService(db, flow["provider"]).claim(
                flow["booking"]["id"], flow["ids"]["lender"], 60000, "Human condition claim"
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(submit, range(2)))
    assert results[0] == results[1]
    changed = call(
        flow,
        "disputes/raise",
        {"claimed_deduction_paise": 50000, "reason": "Updated human evidence review"},
        "lender",
    )
    assert changed.status_code == 200
    assert changed.json()["claim_version"] == results[0]["claim_version"] + 1
    assert (
        call(
            flow,
            "disputes/respond",
            {"accepted": True, "claim_version": results[0]["claim_version"]},
        ).status_code
        == 409
    )


@pytest.mark.parametrize("role", ["borrower", "other"])
def test_claim_submission_preserves_role_authorization(flow, role):
    returned(flow)
    assert (
        call(
            flow,
            "disputes/raise",
            {"claimed_deduction_paise": 20000, "reason": "Human condition claim"},
            role,
        ).status_code
        == 403
    )
    with flow["factory"]() as db:
        assert db.scalar(select(RentalDispute)) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"reason": ""},
        {"reason": "   "},
        {"claimed_deduction_paise": "60000"},
        {"claimed_deduction_paise": -1},
        {"inspection_id": "invalid-reference"},
    ],
)
def test_claim_validation_returns_422_without_saving(flow, changes):
    returned(flow)
    result = call(
        flow,
        "disputes/raise",
        {"claimed_deduction_paise": 20000, "reason": "Human condition claim", **changes},
        "lender",
    )
    assert result.status_code == 422
    with flow["factory"]() as db:
        assert db.scalar(select(RentalDispute)) is None
