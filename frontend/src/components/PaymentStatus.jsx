import React from 'react';
import { paymentLabel } from './paymentFlow.js';

export default function PaymentStatus({ booking, loading = false, error, onRefresh, busy = false }) {
  if (loading) return <p role="status">Loading payment status…</p>;
  if (!booking) return <div>
    <p role="alert">{error || 'Payment status is unavailable.'}</p>
    {onRefresh && <button type="button" disabled={busy} onClick={onRefresh}>Refresh payment status</button>}
  </div>;
  return (
    <div className="payment-status" aria-live="polite">
      <h2>{paymentLabel(booking)}</h2>
      <p>Payment: <strong>{booking.payment_status || 'unknown'}</strong> · Rental: <strong>{booking.booking_status || 'unknown'}</strong></p>
      <p>{['completed', 'cancelled'].includes(booking.booking_status)
        ? 'Handover is closed for this completed or cancelled rental.'
        : booking.handover_unlocked
          ? 'Handover is unlocked after verified payment.'
          : booking.payment_status === 'captured'
            ? 'Handover is paused while return or dispute settlement is reviewed.'
            : 'Handover is locked until payment is verified.'}</p>
      {error && <p role="alert" className="error-banner">{error}</p>}
      {booking.reconciliation?.balanced === false && <p role="alert">Financial reconciliation requires administrator review.</p>}
      {onRefresh && <button type="button" disabled={busy} onClick={onRefresh}>Refresh payment status</button>}
    </div>
  );
}
