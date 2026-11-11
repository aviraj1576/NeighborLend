import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';

export default function PaymentReviewQueue() {
  const { user } = useAuth();
  const [cases, setCases] = useState([]);
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get('/disputes');
      setCases(data);
      setError('');
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not load platform review queue.');
    }
  }, []);
  useEffect(() => {
    if (user?.is_admin) refresh();
  }, [user?.is_admin, refresh]);
  if (!user?.is_admin) return <p>Administrator access required.</p>;
  return (
    <section className="container payment-card">
      <h1>Test payment platform review</h1>
      <p>Simulated deposits only. No real money charged.</p>
      {error && <p role="alert">{error}</p>}
      <button onClick={refresh}>Refresh cases</button>
      {!cases.length && <p>No unresolved cases.</p>}
      {cases.map((row) => (
        <p key={row.booking_id}>
          <Link to={`/borrow-requests/${row.borrow_request_id}`}>
            {row.dispute?.status || row.handover_status || 'Payment recovery'} — review rental
          </Link>
        </p>
      ))}
    </section>
  );
}
