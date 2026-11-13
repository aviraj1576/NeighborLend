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
