import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ReturnSubmission from './ReturnSubmission.jsx';
import ReturnInspection from './ReturnInspection.jsx';
import HandoverConfirmation from './HandoverConfirmation.jsx';
import DepositRefundStatus from './DepositRefundStatus.jsx';
import PaymentStatus from './PaymentStatus.jsx';
import PaymentBreakdown from './PaymentBreakdown.jsx';
import GatewayRefundStatus from './GatewayRefundStatus.jsx';
import RefundPanel from './RefundPanel.jsx';
import { paymentPermissions } from './paymentFlow.js';

const request = { id: 'rental', borrower_id: 'borrower', lender_id: 'lender', handover_status: 'lender_confirmed' };
const booking = {
  id: 'booking', borrow_request_id: 'rental', borrower_id: 'borrower', lender_id: 'lender',
  payment_status: 'captured', booking_status: 'active', security_deposit_paise: 50000,
  held_deposit_paise: 50000, deposit_state: 'held',
};
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, {
  request, booking, user: { id: 'borrower' }, api: {}, onChange() {}, ...props,
}));

test('gateway mismatch separates borrower refund from lender allocation', () => {
  const html = render(GatewayRefundStatus, {
    booking: { ...booking, provider: 'razorpay_test', booking_status: 'completed' },
    result: { status: 'review_required', amount_refunded_paise: 58000, authorized_refund_paise: 40000 },
  });
  assert.match(html, /Gateway refund mismatch/);
  assert.match(html, /580/);
  assert.match(html, /400/);
  assert.match(html, /does not send rent to the lender/);
  assert.doesNotMatch(html, /Check gateway and record review/);
});

test('admin gateway inspection remains available after a completed refund', () => {
  const html = render(GatewayRefundStatus, {
    user: { id: 'admin', is_admin: true },
    booking: { ...booking, provider: 'razorpay_test', booking_status: 'completed' },
    result: { status: 'verified' },
  });
  assert.match(html, /Check gateway and record review/);
  assert.match(html, /Gateway refunds match/);
});

test('unavailable gateway evidence is never displayed as reconciled', () => {
  const html = render(GatewayRefundStatus, {
    booking: { ...booking, provider: 'razorpay_test' }, result: { status: 'unavailable' },
  });
  assert.match(html, /unavailable/);
  assert.doesNotMatch(html, /Gateway refunds match/);
});

test('a saved gateway review keeps refund dispatch disabled and allocations explicit', () => {
  const changed = {
    ...booking, provider: 'razorpay_test', sandbox_only: true, test_mode: true, operations_enabled: true,
    rental_fee_paise: 18000, gateway_review: { status: 'review_required' },
    refund: { status: 'created', amount_paise: 40000, deduction_paise: 0, kind: 'clean_return' },
  };
  assert.equal(paymentPermissions(changed, { id: 'admin', is_admin: true }, request).refund, false);
  const html = render(RefundPanel, { booking: changed, user: { id: 'admin', is_admin: true }, allowed: true });
  assert.doesNotMatch(html, /Send approved Test refund|Retry same approved/);
  assert.match(html, /Agreed rental allocation/);
});

test('eligible borrower sees return upload, including an admin-authorized disputed return', () => {
  assert.match(render(ReturnSubmission), /Submit item return/);
  assert.match(render(ReturnSubmission, { booking: { ...booking, booking_status: 'disputed' } }), /Submit item return/);
});

for (const role of ['lender', 'other', 'admin']) {
  test(`${role} cannot submit borrower return evidence`, () => {
    assert.equal(render(ReturnSubmission, { user: { id: role, is_admin: role === 'admin' } }), '');
  });
}

for (const [name, changed] of [
  ['unavailable status', null],
  ['unpaid', { ...booking, payment_status: 'unpaid' }],
  ['cancelled', { ...booking, booking_status: 'cancelled' }],
  ['settled', { ...booking, booking_status: 'completed' }],
  ['refund authorized', { ...booking, refund: { status: 'created' } }],
  ['another rental', { ...booking, borrow_request_id: 'different-rental' }],
]) {
  test(`return upload stays hidden for ${name}`, () => {
    assert.equal(render(ReturnSubmission, { booking: changed }), '');
  });
}

test('lender inspection uses verified return state and hides clean decisions after rejection', () => {
  const props = {
    user: { id: 'lender' },
    request: { ...request, handover_status: 'return_photos_uploaded' },
    booking: { ...booking, booking_status: 'returned' },
  };
  assert.match(render(ReturnInspection, props), /Approve return/);
  for (const state of [
    { ...props, booking: null },
    { ...props, request: { ...props.request, disputed_at: '2026-11-14' } },
    { ...props, booking: { ...props.booking, dispute: { status: 'needs_claim' } } },
    { ...props, booking: { ...props.booking, deposit_state: 'frozen' } },
    { ...props, booking: { ...props.booking, refund: { status: 'created' } } },
    { ...props, booking: { ...props.booking, booking_status: 'completed' } },
    { ...props, request: { ...props.request, handover_status: 'return_confirmed' } },
  ]) assert.doesNotMatch(render(ReturnInspection, state), /Approve return|Reject and start/);
});

test('reviewed dispute displays its recorded decision without lender approval controls', () => {
  const html = render(ReturnInspection, {
    user: { id: 'lender' }, request: { ...request, handover_status: 'return_photos_uploaded', disputed_at: '2026-11-14' },
    booking: { ...booking, booking_status: 'completed', dispute: { status: 'settled_arbitrated' } },
  });
  assert.match(html, /Return reviewed/);
  assert.doesNotMatch(html, /review pending|Approve return/);
});

test('borrowers and independent admins do not receive lender inspection controls', () => {
  for (const id of ['borrower', 'admin']) assert.equal(render(ReturnInspection, {
    user: { id, is_admin: id === 'admin' }, request: { ...request, handover_status: 'return_photos_uploaded' },
  }), '');
});

test('handover controls require both verified status and the rental booking', () => {
  const props = { user: { id: 'lender' }, request: { ...request, handover_status: 'pending' }, bookingId: 'booking' };
  assert.doesNotMatch(render(HandoverConfirmation, props), /type="file"/);
  assert.match(render(HandoverConfirmation, { ...props, unlocked: true }), /type="file"/);
  assert.doesNotMatch(render(HandoverConfirmation, { ...props, unlocked: true, bookingId: null }), /type="file"/);
});

test('deposit labels distinguish uncaptured payment, no deposit, held liability and frozen review', () => {
  assert.match(render(DepositRefundStatus, { booking: { ...booking, payment_status: 'unpaid', held_deposit_paise: 0 } }), /No security deposit is held until payment is captured/);
  assert.match(render(DepositRefundStatus, { booking: { ...booking, security_deposit_paise: 0, held_deposit_paise: 0 } }), /No security deposit is required/);
  assert.match(render(DepositRefundStatus), /₹500\.00 remains held in the simulated deposit ledger/);
  assert.match(render(DepositRefundStatus, { booking: { ...booking, deposit_state: 'frozen' } }), /frozen for independent human review/);
});

test('initial payment-status failure still offers explicit recovery', () => {
  assert.match(render(PaymentStatus, { booking: null, error: 'Unavailable', onRefresh() {} }), /Unavailable/);
  assert.match(render(PaymentStatus, { booking: null, onRefresh() {} }), /Refresh payment status/);
});

test('cancellation refund distinguishes the refunded deposit from refunded rental fees', () => {
  const html = render(PaymentBreakdown, { booking: {
    ...booking, rental_fee_paise: 40000, total_amount_paise: 90000, deposit_refunded_paise: 90000,
    reconciliation: { processed_deposit_refund_paise: 50000 },
  } });
  assert.match(html, /Deposit refunded<\/dt><dd>₹500\.00/);
  assert.doesNotMatch(html, /Deposit refunded<\/dt><dd>₹900\.00/);
});

test('settled handover status does not claim verified payments still need verification', () => {
  const html = render(PaymentStatus, { booking: { ...booking, booking_status: 'completed' } });
  assert.match(html, /Handover is closed/);
  assert.doesNotMatch(html, /until payment is verified/);
});
