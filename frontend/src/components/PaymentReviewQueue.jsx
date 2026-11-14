import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import { apiErrorMessage, refundReviewLabel } from './paymentFlow.js';

export default function PaymentReviewQueue() {
  const { user } = useAuth();
  const [cases, setCases] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const version = useRef(0);
  const refresh = useCallback(async () => {
    const current = ++version.current;
    setLoading(true);
    try {
      const { data } = await api.get('/disputes', { timeout: 15000 });
      if (current !== version.current) return;
      setCases(data);
      setError('');
    } catch (err) {
      if (current !== version.current) return;
      setCases([]);
      setError(apiErrorMessage(err, 'Could not load platform review queue.'));
    } finally {
      if (current === version.current) setLoading(false);
    }
  }, [user?.id]);
  useEffect(() => {
    if (user?.is_admin) refresh();
    return () => {
      version.current += 1;
    };
  }, [user?.is_admin, refresh]);
  if (!user?.is_admin) return <p>Administrator access required.</p>;
  return (
    <section className="wrap payment-card">
      <h1>Test payment platform review</h1>
      <p>Test Mode payments and simulated deposit accounting. No real money charged.</p>
      {error && <p role="alert">{error}</p>}
      <button onClick={refresh} disabled={loading}>
        Refresh cases
      </button>
      {loading && <p role="status">Loading review queue…</p>}
      {!loading && !error && !cases.length && <p>No unresolved cases.</p>}
      {cases.map((row) => (
        <p key={row.booking_id}>
          <Link to={`/borrow-requests/${row.borrow_request_id}`}>
            {(row.gateway_review ? 'Gateway refund mismatch' : '') || refundReviewLabel(row.refund) ||
              row.dispute?.status ||
              row.handover_status ||
              'Payment recovery'}{' '}
            — review rental
          </Link>
        </p>
      ))}
    </section>
  );
}
