import React from 'react';
import { rupees } from './paymentFlow.js';

export default function PaymentBreakdown({ booking }) {
  const rows = [
    ['Rental fee', booking.rental_fee_paise],
    ['Refundable security deposit', booking.security_deposit_paise],
    ['Total payment', booking.total_amount_paise],
    ['Deposit held / pending allocation', booking.held_deposit_paise],
    ['Deposit refunded', booking.deposit_refunded_paise],
    ['Authorized simulated compensation', booking.deduction_paise],
  ];
  return (
    <div className="payment-breakdown">
      <h3>Payment breakdown</h3>
      <dl>{rows.map(([label, amount]) => (
        <div key={label}><dt>{label}</dt><dd>{rupees(amount || 0)}</dd></div>
      ))}</dl>
    </div>
  );
}
