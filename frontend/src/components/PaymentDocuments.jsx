import React, { useState } from 'react';
import { apiErrorMessage, downloadPaymentDocument } from './paymentFlow.js';

const h = React.createElement;

export default function PaymentDocuments({ booking, api }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (booking.payment_status !== 'captured') return null;
  async function download(refund) {
    setBusy(true);
    setError('');
    try {
      await downloadPaymentDocument(api, booking.id, refund);
    } catch (err) {
      setError(apiErrorMessage(err, 'Document unavailable. Refresh the verified payment status.'));
    } finally {
      setBusy(false);
    }
  }
  return h(
    'section',
    { 'aria-label': 'Payment documents' },
    h(
      'button',
      { type: 'button', disabled: busy, onClick: () => download(false) },
      'Download payment receipt',
    ),
    booking.refund?.status === 'processed' &&
      h(
        'button',
        {
          type: 'button',
          disabled: busy,
          onClick: () => download(true),
        },
        'Download refund acknowledgment',
      ),
    h('p', null, 'NeighborLend Test Mode documents (HTML; open to print or save as PDF).'),
    error && h('p', { role: 'alert' }, error),
  );
}
