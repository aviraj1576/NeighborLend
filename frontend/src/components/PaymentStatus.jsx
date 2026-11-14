import React from 'react';
import { paymentLabel } from './paymentFlow.js';

export default function PaymentStatus({ booking, loading = false, error, onRefresh, busy = false }) {
  if (loading) return <p role="status">Loading payment status…</p>;
  if (!booking) return <p role="alert">{error || 'Payment status is unavailable.'}</p>;
  return (
    <div className="payment-status" aria-live="polite">
      <h2>{paymentLabel(booking)}</h2>
      <p>Payment: <strong>{booking.payment_status || 'unknown'}</strong> · Rental: <strong>{booking.booking_status || 'unknown'}</strong></p>
      <p>Handover is {booking.handover_unlocked ? 'unlocked after verified payment' : 'locked until payment is verified'}.</p>
      {error && <p role="alert" className="error-banner">{error}</p>}
      {booking.reconciliation?.balanced === false && <p role="alert">Financial reconciliation requires administrator review.</p>}
      {onRefresh && <button type="button" disabled={busy} onClick={onRefresh}>Refresh payment status</button>}
    </div>
  );
}
