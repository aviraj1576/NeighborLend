import React, { useCallback, useEffect, useRef, useState } from 'react';
import PaymentCheckout from './PaymentCheckout.jsx';
import PaymentBreakdown from './PaymentBreakdown.jsx';
import PaymentStatus from './PaymentStatus.jsx';
import PaymentHistory from './PaymentHistory.jsx';
import DepositRefundStatus from './DepositRefundStatus.jsx';
import DisputeSection from './DisputeSection.jsx';
import './PaymentModal.css';
import { apiErrorMessage, paymentPermissions, rupees, submitFinancialAction } from './paymentFlow.js';

export default function EscrowStatusCard({ request, user, api, onStatus, onBooking, onRentalChange }) {
  const [booking, setBooking] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [refundOutcome, setRefundOutcome] = useState('processed');
  const refreshVersion = useRef(0);
  const actionInFlight = useRef(false);
  const permissions = booking ? paymentPermissions(booking, user, request) : {};

  const refresh = useCallback(async ({ strict = false } = {}) => {
    const version = ++refreshVersion.current;
    try {
      const { data } = await api.get(`/payments/by-request/${request.id}`, { timeout: 15000 });
      if (version !== refreshVersion.current) return;
      setBooking(data);
      setLoaded(true);
      onBooking?.(data);
      onStatus(data.handover_unlocked === true);
      setError('');
    } catch (err) {
      if (version !== refreshVersion.current) {
        if (strict) throw err;
        return;
      }
      onStatus(false);
      setBooking((previous) => previous && { ...previous, operations_enabled: false, handover_unlocked: false });
      setError(apiErrorMessage(err, 'Payment service unavailable. Handover stays locked.'));
      setLoaded(true);
      if (strict) throw err;
    }
  }, [request.id, onStatus, onBooking, api]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 15000);
    return () => { clearInterval(timer); refreshVersion.current += 1; };
  }, [refresh, request.handover_status]);

  async function action(path, extra = {}) {
    if (actionInFlight.current || !booking?.id) return;
    actionInFlight.current = true;
    setBusy(true);
    setError('');
    try {
      await submitFinancialAction(api, path, { booking_id: booking.id, ...extra }, refresh, onRentalChange);
    } catch (err) {
      setError(apiErrorMessage(err, 'Financial operation pending. Check status before retrying.'));
    } finally {
      actionInFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <section className="payment-card" aria-label="Payment and simulated deposit">
      <strong className="test-mode-banner">
        {booking?.provider === 'razorpay_test' ? 'RAZORPAY TEST MODE — NO REAL MONEY' : 'TEST MODE — NO REAL MONEY'}
      </strong>
      <p>Simulated deposit accounting only; this is not regulated escrow and lender allocations are not provider payouts.</p>
      <PaymentStatus loading={!loaded} booking={booking} error={error} busy={busy} onRefresh={refresh} />
      {!loaded || !booking ? null : booking.legacy ? (
        <p role="status">{booking.message || 'Legacy rental has no verified payment snapshot.'}</p>
      ) : (
        <>
          {!booking.operations_enabled && <p role="status">Payment dispatch is disabled. Saved status and authorized review remain available.</p>}
          <PaymentBreakdown booking={booking} />
          {booking.lender_settlement && <p>Lender rental earnings payable: {rupees(booking.lender_settlement.rental_earnings_payable_paise)}. Simulated accounting; no transfer is sent.</p>}
          {permissions.checkout && <PaymentCheckout booking={booking} api={api} onChange={refresh} />}
          {permissions.reconcile && <button type="button" disabled={busy} onClick={() => action('/payments/reconcile')}>Reconcile gateway payment</button>}
          {permissions.cancel && <button type="button" disabled={busy} onClick={() => action('/payments/cancel')}>Cancel before receipt</button>}
          <DisputeSection
            booking={booking} user={user} api={api} request={request}
            returnReady={['return_photos_uploaded', 'return_confirmed'].includes(request.handover_status)}
            onChange={async (result) => {
              if (result?.claim) {
                refreshVersion.current += 1;
                const updated = { ...booking, dispute: result.claim };
                setBooking(updated);
                onBooking?.(updated);
              }
              await Promise.all([refresh({ strict: true }), onRentalChange?.({ strict: true })]);
            }}
          />
          <DepositRefundStatus
            key={`${booking.refund?.id}:${booking.refund?.status}`}
            booking={booking} user={user} busy={busy} allowed={permissions.refund}
            onAction={action} demoOutcome={refundOutcome} onDemoOutcome={setRefundOutcome}
          />
          <PaymentHistory booking={booking} api={api} />
        </>
      )}
    </section>
  );
}
