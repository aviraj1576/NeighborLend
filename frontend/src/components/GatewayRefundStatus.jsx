import React from 'react';
import { rupees } from './paymentFlow.js';

export default function GatewayRefundStatus({ booking, result, user, busy, onInspect }) {
  if (booking.provider !== 'razorpay_test' || booking.payment_status !== 'captured') return null;
  const review = booking.gateway_review || result?.status === 'review_required';
  return <section aria-label="Gateway refund reconciliation">
    <h3>Gateway refund check</h3>
    {review ? <p role="alert">Gateway refund mismatch requires administrator review. The recorded lender allocation cannot be treated as available for payout. Do not send another refund.</p>
      : result?.status === 'verified' ? <p role="status">Gateway refunds match the recorded authorization.</p>
        : <p role="alert">Current gateway refund status is {result ? 'unavailable' : 'being checked'}. Refund dispatch requires a verified gateway inventory.</p>}
    {Number.isInteger(result?.amount_refunded_paise) && <p>Gateway refunded to borrower: {rupees(result.amount_refunded_paise)}. Authorized refund: {rupees(result.authorized_refund_paise)}.</p>}
    <p>Lender earnings are recorded in the simulated ledger. A borrower refund does not send rent to the lender.</p>
    {user?.is_admin === true && <button type="button" disabled={busy} onClick={onInspect}>Check gateway and record review</button>}
  </section>;
}
