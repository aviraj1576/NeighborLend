import React from 'react';
import RefundPanel from './RefundPanel.jsx';

export default function DepositRefundStatus(props) {
  if (!props.booking?.refund) return <section className="deposit-refund-status" aria-label="Deposit refund status">
    <h3>Security deposit</h3><p role="status">The deposit remains held under the rental settlement until return review is complete.</p>
  </section>;
  return <RefundPanel {...props} />;
}
