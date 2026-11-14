import React from 'react';
import PaymentModal from './PaymentModal.jsx';

export default function PaymentCheckout({ booking, api, onChange }) {
  return <section className="payment-checkout-card" aria-label="Secure test payment">
    <h3>Pay rental and security deposit</h3>
    <p>Checkout uses the configured test provider. Payment is confirmed by the backend before handover unlocks.</p>
    <PaymentModal booking={booking} api={api} onChange={onChange} />
  </section>;
}
