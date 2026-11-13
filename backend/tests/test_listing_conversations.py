"""Listing isolation through real authenticated routes; disposable databases only."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from test_razorpay_escrow import call, physical_return
from test_razorpay_escrow import flow as payment_flow

from app.database import Base
from app.models import BorrowRequest, Conversation, Listing, ListingStatus, NegotiationOffer
from app.services.payments import snapshot_booking

flow = payment_flow


def add_ladder(flow):
    with flow["factory"]() as db:
        ladder = Listing(owner_id=flow["ids"]["lender"], name="Ladder", category="Tools",
                         price_per_day=125, security_deposit=400, status=ListingStatus.published)
        db.add(ladder)
        db.commit()
        return ladder.id


def open_chat(flow, listing_id, role="borrower"):
    result = flow["client"].post("/api/conversations", headers=flow["headers"][role],
                               json={"lender_id": flow["ids"]["lender"], "listing_id": listing_id})
    assert result.status_code == 200, result.text
    return result.json()


def offer_body(listing_id, price=125):
    return {"listing_id": listing_id, "daily_price": price,
            "start_date": (datetime.utcnow() + timedelta(days=10)).isoformat(),
            "end_date": (datetime.utcnow() + timedelta(days=12)).isoformat()}


def history(flow):
    """Full original rows, including payment, refund, handover, evidence and audit."""
    names = {"borrow_requests", "negotiation_offers", "messages", "rental_bookings",
             "payment_transactions", "journal_transactions", "escrow_ledger_entries",
             "refund_intents", "refund_attempts", "rental_disputes", "processed_webhooks",
             "financial_audit_records", "rental_evidence"}
    with flow["factory"]() as db:
        return {name: {row["id"]: dict(row) for row in db.execute(
            select(Base.metadata.tables[name])).mappings()} for name in names}


def assert_history_unchanged(before, after):
    for table, rows in before.items():
        for key, row in rows.items():
            assert after[table][key] == row, (table, key)


@pytest.mark.parametrize("flow", ["realistic"], indirect=True)
def test_accepted_camera_does_not_become_ladder_conversation(flow):
    client, headers = flow["client"], flow["headers"]["borrower"]
    with flow["factory"]() as db:
        camera = db.get(Listing, db.get(BorrowRequest, flow["request_id"]).listing_id)
        camera.name = "Camera"
        ladder = Listing(owner_id=flow["ids"]["lender"], name="Ladder", category="Tools",
                         price_per_day=125, security_deposit=400, status=ListingStatus.published)
        db.add(ladder)
        db.commit()
        camera_id, ladder_id = camera.id, ladder.id
    camera_response = client.post("/api/conversations", headers=headers,
                                  json={"lender_id": flow["ids"]["lender"], "listing_id": camera_id})
    ladder_response = client.post("/api/conversations", headers=headers,
                                  json={"lender_id": flow["ids"]["lender"], "listing_id": ladder_id})
    assert camera_response.status_code == ladder_response.status_code == 200
    camera_chat, ladder_chat = camera_response.json(), ladder_response.json()
    assert camera_chat["active_offer"]["daily_price"] == 500
    assert camera_chat["active_offer"]["security_deposit_paise"] == 200000
    assert ladder_chat["id"] != camera_chat["id"], (
        "Ladder reused Camera chat: active listing=" + str(ladder_chat["active_offer"]["listing_id"])
    )
    assert ladder_chat["active_offer"] is None
    assert ladder_chat["offers"] == []
    assert ladder_chat["listing_id"] == ladder_id
    assert ladder_chat["listing"]["price_per_day"] == 125
    assert ladder_chat["listing"]["security_deposit"] == 400


@pytest.mark.parametrize("flow", ["mock", "postgres"], indirect=True)
def test_independent_offers_reopen_and_payment_history(flow):
    # Entire lifecycle uses the synthetic provider, never Razorpay/Supabase.
    assert call(flow, "payments/create-order").status_code == 200
    assert call(flow, "payments/mock-confirm").status_code == 200
    physical_return(flow)
    result = flow["client"].post(f"/api/borrow-requests/{flow['request_id']}/return/confirm",
                                 json={"approved": True}, headers=flow["headers"]["lender"])
    assert result.status_code == 200, result.text
    assert call(flow, "payments/refund-deposit", role="lender").status_code == 200
    assert call(flow, "payments/refunds/execute").status_code == 200
    before = history(flow)
    camera_offer = next(iter(before["negotiation_offers"].values()))
    camera_chat = open_chat(flow, camera_offer["listing_id"])
    ladder_id = add_ladder(flow)
    ladder_chat = open_chat(flow, ladder_id)
    assert ladder_chat["id"] != camera_chat["id"]
    assert ladder_chat["offers"] == []
    client, headers = flow["client"], flow["headers"]
    created = client.post(f"/api/conversations/{ladder_chat['id']}/offers",
                          json={**offer_body(ladder_id), "security_deposit_paise": 1,
                                "total_amount_paise": 1}, headers=headers["borrower"])
    assert created.status_code == 200, created.text
    assert created.json()["security_deposit_paise"] == 40000  # Server authoritative.
    assert created.json()["total_amount_paise"] == 65000
    countered = client.post(f"/api/offers/{created.json()['id']}/counter",
                            json=offer_body(ladder_id, 100), headers=headers["lender"])
    assert countered.status_code == 200, countered.text
    assert countered.json()["security_deposit_paise"] == 40000
    accepted = client.post(f"/api/offers/{countered.json()['id']}/accept", headers=headers["borrower"])
    assert accepted.status_code == 200, accepted.text
    ladder_request_id = accepted.json()["borrow_request_id"]
    assert ladder_request_id != flow["request_id"]
    booking = client.get(f"/api/payments/by-request/{ladder_request_id}", headers=headers["borrower"])
    assert booking.status_code == 200
    assert booking.json()["security_deposit_paise"] == 40000
    assert booking.json()["rental_fee_paise"] == 20000
    assert booking.json()["handover_unlocked"] is False
    for request_id, chat_id in ((flow["request_id"], camera_chat["id"]), (ladder_request_id, ladder_chat["id"])):
        rental = client.get(f"/api/borrow-requests/{request_id}/handover", headers=headers["borrower"])
        assert rental.status_code == 200
        assert rental.json()["conversation_id"] == chat_id
    for listing_id, original in ((camera_offer["listing_id"], camera_chat), (ladder_id, ladder_chat)):
        reopened = open_chat(flow, listing_id)
        assert reopened["id"] == original["id"]
        assert {o["listing_id"] for o in reopened["offers"]} == {listing_id}
        fetched = client.get(f"/api/conversations/{reopened['id']}", headers=headers["lender"])
        assert fetched.json()["listing_id"] == listing_id
        assert fetched.json()["active_offer"]["listing_id"] == listing_id
    assert open_chat(flow, camera_offer["listing_id"])["active_offer"]["id"] == camera_offer["id"]
    assert_history_unchanged(before, history(flow))


@pytest.mark.parametrize("flow", ["mock", "postgres"], indirect=True)
def test_repeated_and_concurrent_clicks_reuse_one_thread(flow):
    listing_id = add_ladder(flow)
    barrier = Barrier(5)

    def click(_):
        barrier.wait(timeout=15)
        return open_chat(flow, listing_id)["id"]

    with ThreadPoolExecutor(max_workers=5) as pool:
        ids = list(pool.map(click, range(5)))
    assert len(set(ids)) == 1
    for _ in range(3):
        assert open_chat(flow, listing_id)["id"] == ids[0]
    fetched = flow["client"].get(f"/api/conversations/{ids[0]}", headers=flow["headers"]["borrower"])
    assert len(fetched.json()["messages"]) == 1
    assert "Ladder" in fetched.json()["messages"][0]["content"]
    with flow["factory"]() as db:
        assert db.query(Conversation).filter(Conversation.listing_id == listing_id).count() == 1


@pytest.mark.parametrize("flow", ["mock", "postgres"], indirect=True)
def test_listing_and_borrower_authorization(flow):
    listing_id = add_ladder(flow)
    chat = open_chat(flow, listing_id)
    other_chat = open_chat(flow, listing_id, "other")
    assert chat["id"] != other_chat["id"]
    client, headers = flow["client"], flow["headers"]
    route = f"/api/conversations/{chat['id']}"
    for suffix in ("", "/messages", "/offers"):
        assert client.get(route + suffix).status_code == 401
        assert client.get(route + suffix, headers=headers["other"]).status_code == 403
    assert client.post(route + "/messages", json={"content": "unrelated"}, headers=headers["other"]).status_code == 403
    assert client.post(route + "/offers", json=offer_body(listing_id), headers=headers["other"]).status_code == 403
    offer = client.post(route + "/offers", json=offer_body(listing_id), headers=headers["borrower"]).json()
    for action in ("accept", "counter", "reject"):
        response = client.post(f"/api/offers/{offer['id']}/{action}",
                               json=offer_body(listing_id), headers=headers["other"])
        assert response.status_code == 403
    for role, expected in (("borrower", {chat["id"]}), ("other", {other_chat["id"]})):
        items = client.get("/api/conversations", headers=headers[role]).json()
        assert {c["id"] for c in items if c["listing_id"] == listing_id} == expected
    wrong_owner = client.post("/api/conversations", headers=headers["borrower"],
                               json={"lender_id": flow["ids"]["other"], "listing_id": listing_id})
    assert wrong_owner.status_code == 404


@pytest.mark.parametrize("flow", ["mock", "postgres"], indirect=True)
def test_cross_listing_offer_and_counter_are_rejected(flow):
    ladder_id = add_ladder(flow)
    ladder = open_chat(flow, ladder_id)
    with flow["factory"]() as db:
        camera_id = db.get(BorrowRequest, flow["request_id"]).listing_id
    camera = open_chat(flow, camera_id)
    before = history(flow)
    client, headers = flow["client"], flow["headers"]
    assert client.post(f"/api/conversations/{ladder['id']}/offers", json=offer_body(camera_id, 500),
                       headers=headers["borrower"]).status_code == 409
    camera_offer = client.post(f"/api/conversations/{camera['id']}/offers", json=offer_body(camera_id, 500),
                               headers=headers["borrower"])
    assert camera_offer.status_code == 200, camera_offer.text
    ladder_offer = client.post(f"/api/conversations/{ladder['id']}/offers", json=offer_body(ladder_id),
                               headers=headers["borrower"])
    assert ladder_offer.status_code == 200
    assert client.get(f"/api/conversations/{camera['id']}", headers=headers["borrower"]).json()["active_offer"]["id"] == camera_offer.json()["id"]
    mismatch = client.post(f"/api/offers/{ladder_offer.json()['id']}/counter", json=offer_body(camera_id),
                           headers=headers["lender"])
    assert mismatch.status_code == 400
    # Even a malformed stored offer cannot turn another listing's chat into a booking.
    with flow["factory"]() as db:
        legitimate = db.get(NegotiationOffer, ladder_offer.json()["id"])
        malformed_offer = NegotiationOffer(conversation_id=camera["id"], listing_id=ladder_id,
                                           sender_id=legitimate.sender_id, daily_price=125,
                                           start_date=legitimate.start_date, end_date=legitimate.end_date,
                                           total_cost=250)
        db.add(malformed_offer)
        db.commit()
        malformed_id = malformed_offer.id
    malformed = client.post(f"/api/offers/{malformed_id}/accept", headers=headers["lender"])
    assert malformed.status_code == 409
    assert_history_unchanged(before, history(flow))


def test_payment_snapshot_cannot_reuse_camera_offer_or_booking(flow):
    ladder_id = add_ladder(flow)
    with flow["factory"]() as db:
        accepted = db.query(NegotiationOffer).filter_by(borrow_request_id=flow["request_id"]).one()
        camera_request = db.get(BorrowRequest, flow["request_id"])
        with pytest.raises(HTTPException) as error:
            snapshot_booking(db, SimpleNamespace(id=camera_request.id, listing_id=ladder_id), accepted, "mock")
        assert error.value.status_code == 409
        assert "another listing" in error.value.detail
        with pytest.raises(HTTPException) as error:
            snapshot_booking(db, camera_request, SimpleNamespace(id="different-offer", listing_id=accepted.listing_id), "mock")
        assert error.value.status_code == 409
        assert "another accepted offer" in error.value.detail


def test_unpublished_listing_cannot_start_new_chat_but_history_reopens(flow):
    ladder_id = add_ladder(flow)
    camera_id = None
    with flow["factory"]() as db:
        camera_id = db.get(BorrowRequest, flow["request_id"]).listing_id
        db.get(Listing, ladder_id).status = ListingStatus.draft
        db.get(Listing, camera_id).status = ListingStatus.draft
        db.commit()
    client, headers = flow["client"], flow["headers"]["borrower"]
    result = client.post("/api/conversations", headers=headers,
                         json={"lender_id": flow["ids"]["lender"], "listing_id": ladder_id})
    assert result.status_code == 409
    assert open_chat(flow, camera_id)["active_offer"]["status"] == "accepted"
    assert client.post("/api/conversations", headers=headers,
                        json={"lender_id": flow["ids"]["lender"], "listing_id": ""}).status_code == 422
