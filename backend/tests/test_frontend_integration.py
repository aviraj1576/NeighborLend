"""Actual upstream form/API contracts exercised only against isolated fixtures."""
import pytest
from test_razorpay_escrow import evidence, fund
from test_razorpay_escrow import flow as payment_flow

from app.models import User

flow = payment_flow


def test_private_rental_includes_lender_identity_and_payment_gate(flow):
    client = flow["client"]
    request_id = flow["request_id"]
    for role in ("borrower", "lender", "admin"):
        response = client.get(f"/api/payments/requests/{request_id}/rental", headers=flow["headers"][role])
        assert response.status_code == 200
        assert response.json()["lender_username"] == "lender"
        assert response.json()["lender_id"] == flow["ids"]["lender"]
    assert client.get(f"/api/payments/requests/{request_id}/rental", headers=flow["headers"]["other"]).status_code == 403
    unpaid = client.get(f"/api/payments/by-request/{request_id}", headers=flow["headers"]["borrower"]).json()
    assert unpaid["handover_unlocked"] is False
    fund(flow)  # Synthetic provider, local DB only; never Razorpay.
    paid = client.get(f"/api/payments/by-request/{request_id}", headers=flow["headers"]["lender"]).json()
    assert paid["handover_unlocked"] is True and paid["payment_status"] == "captured"


@pytest.mark.parametrize("flow", ["mock", "postgres"], indirect=True)
def test_admin_listing_owner_retains_lender_evidence_and_confirmation_controls(flow):
    with flow["factory"]() as db:
        db.get(User, flow["ids"]["lender"]).is_admin = True
        db.commit()
    fund(flow)
    client, request_id = flow["client"], flow["request_id"]
    route = f"/api/borrow-requests/{request_id}/handover"
    # A different admin does not become the physical lender.
    assert client.post(route + "/upload-photos", json={"photo_urls": ["evidence:forged"]},
                       headers=flow["headers"]["admin"]).status_code == 403
    assert client.post(route + "/borrower-confirm", json={},
                       headers=flow["headers"]["borrower"]).status_code == 409
    before = evidence(flow, "handover", "lender")
    assert before.startswith("/api/payments/evidence/")
    assert client.post(route + "/upload-photos", json={"photo_urls": [before]},
                       headers=flow["headers"]["lender"]).status_code == 200
    assert client.post(route + "/lender-confirm", headers=flow["headers"]["lender"]).status_code == 409
    receipt = evidence(flow, "receipt", "borrower")
    received = client.post(route + "/borrower-confirm", json={"photo_urls": [receipt], "condition_note": "Checked against lender photos"},
                           headers=flow["headers"]["borrower"])
    assert received.status_code == 200
    assert received.json()["handover_status"] == "borrower_confirmed"
    assert received.json()["borrowing_started_at"] is None
    assert client.post(route + "/lender-confirm", headers=flow["headers"]["borrower"]).status_code == 403
    active = client.post(route + "/lender-confirm", headers=flow["headers"]["lender"])
    assert active.status_code == 200
    assert active.json()["handover_status"] == "lender_confirmed"
    assert active.json()["borrowing_started_at"] is not None


def test_independent_admin_can_review_private_return_and_settle_but_cannot_act_as_lender(flow):
    from test_razorpay_escrow import call, physical_return

    fund(flow)
    physical_return(flow)
    client, request_id, booking_id = flow["client"], flow["request_id"], flow["booking"]["id"]
    assert client.get("/api/disputes", headers=flow["headers"]["borrower"]).status_code == 403
    assert client.get("/api/disputes", headers=flow["headers"]["lender"]).status_code == 403
    rental = client.get(f"/api/payments/requests/{request_id}/rental", headers=flow["headers"]["admin"])
    assert rental.status_code == 200 and rental.json()["return_photos"]
    assert client.get(rental.json()["return_photos"][0], headers=flow["headers"]["admin"]).status_code == 200
    assert client.post(f"/api/borrow-requests/{request_id}/return/confirm", json={"approved": True},
                       headers=flow["headers"]["admin"]).status_code == 403
    rejected = client.post(f"/api/borrow-requests/{request_id}/return/confirm", json={"approved": False},
                           headers=flow["headers"]["lender"])
    assert rejected.status_code == 200
    queue = client.get("/api/disputes", headers=flow["headers"]["admin"])
    assert queue.status_code == 200 and any(row["booking_id"] == booking_id for row in queue.json())
    claim = call(flow, "disputes/raise", {"claimed_deduction_paise": 10000, "reason": "Synthetic damage evidence"}, "lender")
    assert claim.status_code == 200
    assert call(flow, "disputes/settle", {"approved_deduction_paise": 10000, "reason": "Participant decision"}, "lender").status_code == 403
    approved = call(flow, "disputes/settle", {"approved_deduction_paise": 10000, "reason": "Independent evidence review",
                                            "claim_version": claim.json()["claim_version"]}, "admin")
    assert approved.status_code == 200 and approved.json()["amount_paise"] == 40000
    settled = call(flow, "payments/refunds/execute")
    assert settled.status_code == 200 and settled.json()["deduction_paise"] == 10000
    assert settled.json()["deposit_refunded_paise"] == 40000
    assert settled.json()["rating_eligible"] is True


def test_frontend_rating_flag_requires_completed_refund_then_accepts_participant_rating(flow):
    from test_razorpay_escrow import call, physical_return

    fund(flow)
    physical_return(flow)
    client, request_id = flow["client"], flow["request_id"]
    assert client.post(f"/api/borrow-requests/{request_id}/return/confirm", json={"approved": True},
                       headers=flow["headers"]["lender"]).status_code == 200
    before = client.get(f"/api/payments/by-request/{request_id}", headers=flow["headers"]["borrower"])
    assert before.json()["rating_eligible"] is False
    route = f"/api/borrow-requests/{request_id}/rate-lender"
    assert client.post(route, json={"rating": 5}, headers=flow["headers"]["borrower"]).status_code == 409
    assert call(flow, "payments/refunds/execute").json()["rating_eligible"] is True
    assert client.post(route, json={"rating": 5}, headers=flow["headers"]["admin"]).status_code == 403
    assert client.post(route, json={"rating": 5}, headers=flow["headers"]["borrower"]).status_code == 200


def test_legacy_rating_eligibility_is_reported_without_inventing_payment_funding(flow):
    from app.models import BorrowRequest

    with flow["factory"]() as db:
        original = db.get(BorrowRequest, flow["request_id"])
        legacy = BorrowRequest(borrower_id=flow["ids"]["borrower"], listing_id=original.listing_id,
                               title="Legacy completed rental", category="Tools", handover_status="return_confirmed")
        db.add(legacy)
        db.commit()
        identity = legacy.id
    response = flow["client"].get(f"/api/payments/by-request/{identity}", headers=flow["headers"]["borrower"])
    assert response.status_code == 200
    assert response.json()["legacy"] is True
    assert response.json()["rating_eligible"] is True
    assert response.json()["handover_unlocked"] is False
    assert flow["client"].get(f"/api/payments/by-request/{identity}", headers=flow["headers"]["other"]).status_code == 403
