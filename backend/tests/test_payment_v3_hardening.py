"""Provider trust boundary and journal replay regression checks on isolated DBs."""

import pytest
from sqlalchemy import select
from test_payment_providers import config
from test_razorpay_escrow import call, fund, razorpay_flow
from test_razorpay_escrow import flow as payment_flow

from app.payment_models import EscrowLedgerEntry, JournalTransaction, RentalBooking
from app.services.escrow_service import post
from app.services.razorpay_service import ProviderError, RazorpayTestProvider

flow = payment_flow


@pytest.mark.parametrize(
    "response", [None, [], {"items": None}, {"items": [{}, 1]}, {"items": [{}] * 101}]
)
def test_malformed_gateway_collections_fail_with_recoverable_provider_error(response):
    provider = RazorpayTestProvider(
        config(
            razorpay_key_id="rzp_test_fixture",
            razorpay_key_secret="synthetic-secret",
            razorpay_webhook_secret="synthetic-webhook",
        ),
        transport=lambda *args: response,
    )
    with pytest.raises(ProviderError, match="invalid_provider_response"):
        provider.order_payments("order_fixture")


def test_wrong_identifier_kind_and_blank_secret_rejected_before_transport():
    provider = RazorpayTestProvider(
        config(
            razorpay_key_id="rzp_test_fixture",
            razorpay_key_secret="synthetic-secret",
            razorpay_webhook_secret="synthetic-webhook",
        ),
        transport=lambda *args: pytest.fail("No network call is permitted"),
    )
    for method, identifier in (
        (provider.fetch_order, "pay_fixture"),
        (provider.fetch_payment, "rfnd_fixture"),
        (provider.fetch_refund, "order_fixture"),
    ):
        with pytest.raises(ProviderError, match="invalid_provider_identifier"):
            method(identifier)
    with pytest.raises(ProviderError, match="test_credentials_required"):
        RazorpayTestProvider(
            config(
                razorpay_key_id="rzp_test_fixture",
                razorpay_key_secret=" ",
                razorpay_webhook_secret=" ",
            )
        )


def test_journal_replay_cannot_silently_reallocate_an_existing_reference(flow):
    fund(flow)
    with flow["factory"]() as db:
        booking = db.get(RentalBooking, flow["booking"]["id"])
        journal = db.scalar(select(JournalTransaction))
        entries = db.scalars(select(EscrowLedgerEntry)).all()
        lines = [(row.account_type, row.entry_type, row.amount_paise) for row in entries]
        assert post(db, booking, journal.reference, lines, "same allocation") is journal
        wrong = [("wrong_account", side, amount) for _, side, amount in lines]
        with pytest.raises(ValueError, match="idempotency reference conflicts"):
            post(db, booking, journal.reference, wrong, "conflicting allocation")
        assert len(db.scalars(select(EscrowLedgerEntry)).all()) == len(entries)


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
def test_authoritative_order_amount_must_be_integer_paise(flow):
    _, signature = razorpay_flow(flow)
    assert call(flow, "payments/create-order").status_code == 200
    from app.main import app
    from app.routers.payments import payment_provider

    provider = app.dependency_overrides[payment_provider]()
    original = provider.fetch_order

    def corrupt(order_id):
        result = original(order_id)
        result["amount"] = float(result["amount"])
        return result

    provider.fetch_order = corrupt
    response = call(
        flow,
        "payments/verify",
        {"order_id": "order_fixture", "payment_id": "pay_fixture", "signature": signature},
    )
    assert response.status_code == 409
    with flow["factory"]() as db:
        assert db.get(RentalBooking, flow["booking"]["id"]).payment_status != "captured"
        assert db.scalar(select(JournalTransaction)) is None
