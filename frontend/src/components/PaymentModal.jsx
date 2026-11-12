import React, { useState } from 'react';
import { apiErrorMessage, checkout, rupees } from './paymentFlow.js';

const h = React.createElement;

export default function PaymentModal({ booking, api, onChange }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [demo, setDemo] = useState(Boolean(booking.pending_payment_id));
  const [pending, setPending] = useState(booking.pending_payment_id || null);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const sandboxConfirmed =
    booking.sandbox_only === true &&
    booking.test_mode === true &&
    booking.operations_enabled === true &&
    ['mock', 'razorpay_test'].includes(booking.provider);
  async function run(action) {
    setBusy(true);
    setError('');
    try {
      await action();
      await onChange();
    } catch (err) {
      setError(apiErrorMessage(err, 'Payment could not be verified.'));
    } finally {
      setBusy(false);
    }
  }
  return h(
    'div',
    { className: 'payment-checkout' },
    booking.provider === 'razorpay_test' &&
      h('strong', { className: 'test-mode-banner' }, 'RAZORPAY TEST MODE — NO REAL MONEY'),
    h(
      'p',
      null,
      `Rental ${rupees(booking.rental_fee_paise)} + refundable deposit ${rupees(booking.security_deposit_paise)} = ${rupees(booking.total_amount_paise)}`,
    ),
    h(
      'p',
      null,
      `Provider: ${booking.provider === 'mock' ? 'Local demo simulator' : 'Razorpay TEST mode'}`,
    ),
    error && h('p', { role: 'alert', className: 'error-banner' }, error),
    !sandboxConfirmed &&
      h(
        'p',
        { role: 'alert' },
        'Backend sandbox-only confirmation is required. Checkout is blocked.',
      ),
    h(
      'label',
      null,
      h('input', {
        type: 'checkbox',
        checked: acceptedTerms,
        disabled: busy,
        onChange: (event) => setAcceptedTerms(event.target.checked),
      }),
      'I accept the agreed rental period, rental fee, refundable deposit and human-reviewed dispute terms.',
    ),
    h(
      'button',
      {
        type: 'button',
        disabled: busy || !sandboxConfirmed || !acceptedTerms,
        onClick: () =>
          run(async () => {
            if (!sandboxConfirmed)
              throw new Error('Backend sandbox-only confirmation is required.');
            if (!acceptedTerms) throw new Error('Accept the rental terms before checkout.');
            const result = await checkout(api, booking.id);
            setDemo(result.mock);
          }),
      },
      busy ? 'Checking…' : 'Pay test rental + deposit',
    ),
    sandboxConfirmed &&
      demo &&
      h(
        'div',
        { role: 'group', 'aria-label': 'Local demo checkout', className: 'demo-checkout' },
        h('p', null, 'LOCAL MOCK CHECKOUT — no bank or Razorpay request occurs.'),
        ...['success', 'failed', 'pending', 'cancelled'].map((outcome) =>
          h(
            'button',
            {
              key: outcome,
              type: 'button',
              disabled: busy,
              onClick: () =>
                run(async () => {
                  const { data } = await api.post('/payments/mock-confirm', {
                    booking_id: booking.id,
                    outcome,
                  });
                  setPending(data.pending_payment_id || null);
                  if (data.payment_status === 'failed')
                    throw new Error(
                      outcome === 'cancelled'
                        ? 'Simulated checkout cancelled. No payment captured.'
                        : 'Simulated payment failed. Retry safely.',
                    );
                }),
            },
            `Simulate ${outcome}`,
          ),
        ),
        pending &&
          h(
            'button',
            {
              type: 'button',
              disabled: busy,
              onClick: () =>
                run(async () => {
                  await api.post('/payments/mock-confirm', {
                    booking_id: booking.id,
                    outcome: 'success',
                    payment_id: pending,
                  });
                  setPending(null);
                }),
            },
            'Confirm delayed demo payment',
          ),
      ),
  );
}
