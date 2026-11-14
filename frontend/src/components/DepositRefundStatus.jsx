import React from 'react';
import RefundPanel from './RefundPanel.jsx';
import { rupees } from './paymentFlow.js';

export default function DepositRefundStatus(props) {
  const booking = props.booking;
  const label = booking?.security_deposit_paise === 0
    ? 'No security deposit is required for this rental.'
    : booking?.payment_status !== 'captured'
      ? 'No security deposit is held until payment is captured.'
      : booking?.deposit_state === 'frozen' || booking?.dispute
        ? 'The deposit is frozen for independent human review. No deduction or refund is authorized yet.'
        : booking?.held_deposit_paise > 0
          ? `${rupees(booking.held_deposit_paise)} remains held in the simulated deposit ledger pending return review.`
          : 'No deposit balance is currently held. Review the payment history for settlement details.';
  if (!props.booking?.refund) return <section className="deposit-refund-status" aria-label="Deposit refund status">
    <h3>Security deposit</h3><p role="status">{label}</p>
  </section>;
  return <RefundPanel {...props} />;
}
