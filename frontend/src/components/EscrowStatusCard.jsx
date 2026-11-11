import React, { useCallback, useEffect, useRef, useState } from 'react';
import PaymentModal from './PaymentModal.jsx';
import DisputeResolutionModal from './DisputeResolutionModal.jsx';
import RefundPanel from './RefundPanel.jsx';
import FinancialTimeline from './FinancialTimeline.jsx';
import { apiErrorMessage, paymentLabel, paymentPermissions, rupees } from './paymentFlow.js';

const h = React.createElement;

export default function EscrowStatusCard({
  request,
  user,
  api,
  onStatus,
  onBooking,
  onRentalChange,
}) {
  const [booking, setBooking] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [refundOutcome, setRefundOutcome] = useState('processed');
  const refreshVersion = useRef(0);
  const permissions = booking ? paymentPermissions(booking, user, request) : {};
  const refresh = useCallback(
    async ({ strict = false } = {}) => {
      const version = ++refreshVersion.current;
      try {
        const { data } = await api.get(`/payments/by-request/${request.id}`, { timeout: 15000 });
        if (version !== refreshVersion.current) return;
        setBooking(data);
        onBooking?.(data);
        onStatus(Boolean(data.handover_unlocked));
        setError('');
      } catch (err) {
        if (version !== refreshVersion.current) {
          if (strict) throw err;
          return;
        }
        onStatus(false);
        setBooking(
          (previous) =>
            previous && { ...previous, operations_enabled: false, handover_unlocked: false },
        );
        setError(apiErrorMessage(err, 'Payment service unavailable. Handover stays locked.'));
        if (strict) throw err;
      }
    },
    [request.id, onStatus, onBooking, api],
  );
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 15000);
    return () => clearInterval(timer);
  }, [refresh, request.handover_status]);
  async function action(path, extra = {}) {
    setBusy(true);
    setError('');
    try {
      await api.post(path, { booking_id: booking.id, ...extra });
      await refresh();
      await onRentalChange?.();
    } catch (err) {
      setError(apiErrorMessage(err, 'Financial operation pending. Check status before retrying.'));
    } finally {
      setBusy(false);
    }
  }
  return h(
    'section',
    { className: 'payment-card', 'aria-label': 'Test payment and simulated deposit' },
    h(
      'strong',
      { className: 'test-mode-banner' },
      booking?.provider === 'razorpay_test'
        ? 'RAZORPAY TEST MODE — NO REAL MONEY'
        : 'TEST MODE — NO REAL MONEY',
    ),
    h(
      'p',
      null,
      'Simulated deposit accounting. This is not regulated escrow; lender allocations are not actual payouts.',
    ),
    error && h('p', { role: 'alert', className: 'error-banner' }, error),
    h('button', { type: 'button', disabled: busy, onClick: refresh }, 'Refresh payment status'),
    !booking
      ? h('p', { role: 'status' }, 'Loading payment status…')
      : booking.legacy
        ? h('p', null, paymentLabel(booking))
        : h(
            'div',
            null,
            h('h2', null, paymentLabel(booking)),
            !booking.operations_enabled &&
              h(
                'p',
                { role: 'status' },
                'Payment dispatch is disabled. Authorized review and dispute recovery remain available.',
              ),
            h(
              'dl',
              null,
              ...[
                ['Rental fee', booking.rental_fee_paise],
                ['Deposit agreed', booking.security_deposit_paise],
                ['Total Test payment', booking.total_amount_paise],
                ['Deposit held / pending allocation', booking.held_deposit_paise],
                ['Deposit refunded', booking.deposit_refunded_paise],
                ['Authorized simulated lender compensation', booking.deduction_paise],
              ].map(([label, value]) =>
                h('div', { key: label }, h('dt', null, label), h('dd', null, rupees(value))),
              ),
            ),
            h(
              'p',
              null,
              `Rental: ${booking.booking_status}. Handover ${booking.handover_unlocked ? 'unlocked' : 'locked'}.`,
            ),
            permissions.checkout && h(PaymentModal, { booking, api, onChange: refresh }),
            permissions.reconcile &&
              h(
                'button',
                { disabled: busy, onClick: () => action('/payments/reconcile') },
                'Reconcile gateway payment',
              ),
            permissions.cancel &&
              h(
                'button',
                { disabled: busy, onClick: () => action('/payments/cancel') },
                'Cancel before receipt',
              ),
            h(DisputeResolutionModal, {
              booking,
              user,
              api,
              onChange: async (result) => {
                if (result?.claim) {
                  refreshVersion.current += 1; // Fence a poll started before the saved response.
                  const updated = { ...booking, dispute: result.claim };
                  setBooking(updated);
                  onBooking?.(updated);
                }
                await Promise.all([refresh({ strict: true }), onRentalChange?.({ strict: true })]);
              },
              request,
              returnReady: ['return_photos_uploaded', 'return_confirmed'].includes(
                request.handover_status,
              ),
            }),
            h(RefundPanel, {
              key: booking.refund?.id,
              booking,
              user,
              busy,
              allowed: permissions.refund,
              onAction: action,
              demoOutcome: refundOutcome,
              onDemoOutcome: setRefundOutcome,
            }),
            h(FinancialTimeline, { booking }),
          ),
  );
}
