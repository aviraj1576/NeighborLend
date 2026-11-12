"""Existing receipt-without-photos contract; real routes, isolated DB, mock provider."""

import pytest
from test_razorpay_escrow import evidence, fund
from test_razorpay_escrow import flow as payment_flow

flow = payment_flow


@pytest.mark.parametrize("flow", ["mock", "postgres"], indirect=True)
def test_photo_free_receipt_keeps_payment_baseline_both_parties_and_return_evidence(flow):
    client, headers = flow["client"], flow["headers"]
    route = f"/api/borrow-requests/{flow['request_id']}"
    handover = route + "/handover"
    assert client.post(handover + "/borrower-confirm", headers=headers["borrower"], json={}).status_code == 409
    fund(flow)
    assert client.post(handover + "/borrower-confirm", headers=headers["borrower"], json={}).status_code == 409
    assert client.post(handover + "/lender-confirm", headers=headers["lender"]).status_code == 409
    assert client.post(handover + "/upload-photos", headers=headers["lender"], json={"photo_urls": []}).status_code == 422
    before = evidence(flow, "handover", "lender")
    assert client.post(handover + "/upload-photos", headers=headers["lender"], json={"photo_urls": [before]}).status_code == 200
    for role in ("lender", "other"):
        assert client.post(handover + "/borrower-confirm", headers=headers[role], json={}).status_code == 403
    received = client.post(handover + "/borrower-confirm", headers=headers["borrower"], json={"condition_note": "Reviewed lender baseline"})
    assert received.status_code == 200, received.text
    body = received.json()
    assert body["handover_confirmed_photos"] == []
    assert body["handover_photos"] == [before]
    assert body["handover_status"] == "borrower_confirmed"
    assert body["borrowing_started_at"] is None and body["return_due_at"] is None
    assert client.post(route + "/return/upload-photos", headers=headers["borrower"], json={"photo_urls": [before]}).status_code == 409
    assert client.post(handover + "/lender-confirm", headers=headers["borrower"]).status_code == 403
    active = client.post(handover + "/lender-confirm", headers=headers["lender"])
    assert active.status_code == 200 and active.json()["borrowing_started_at"] is not None
    assert client.post(route + "/return/upload-photos", headers=headers["borrower"], json={"photo_urls": []}).status_code == 422
    assert client.post(route + "/return/confirm", headers=headers["lender"], json={"approved": True}).status_code == 409
    returned = evidence(flow, "return", "borrower")
    assert client.post(route + "/return/upload-photos", headers=headers["borrower"], json={"photo_urls": [returned]}).status_code == 200
    approved = client.post(route + "/return/confirm", headers=headers["lender"], json={"approved": True})
    assert approved.status_code == 200, approved.text
    booking = client.get(f"/api/payments/bookings/{flow['booking']['id']}", headers=headers["borrower"]).json()
    assert booking["refund"]["status"] == "created"  # Authorized only; admin dispatch remains separate.
    assert booking["refund"]["amount_paise"] == 50000
    assert booking["deposit_refunded_paise"] == 0
    assert client.get(before, headers=headers["borrower"]).status_code == 200
    assert client.get(before, headers=headers["other"]).status_code == 403
