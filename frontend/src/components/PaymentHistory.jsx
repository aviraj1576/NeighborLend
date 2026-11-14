import React from 'react';
import FinancialTimeline from './FinancialTimeline.jsx';
import PaymentDocuments from './PaymentDocuments.jsx';

export default function PaymentHistory({ booking, api }) {
  return <section className="payment-history" aria-label="Payment and transaction history">
    <h3>Payment history</h3>
    <FinancialTimeline booking={booking} />
    <PaymentDocuments booking={booking} api={api} />
  </section>;
}
