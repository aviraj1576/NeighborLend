import React, { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import './BorrowRequestDetail.css';

const BorrowRequestDetail = () => {
  const { id } = useParams();
  const { user } = useAuth();
  const [request, setRequest] = useState(null);
  const [disputeDescription, setDisputeDescription] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const fetchRequest = useCallback(async () => {
    try {
      const response = await api.get(`/borrow-requests/${id}`);
      setRequest(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not load this borrowing request.');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchRequest();
  }, [fetchRequest]);

  const reportReturn = async () => {
    setSubmitting(true);
    setError('');
    try {
      await api.post(`/borrow-requests/${id}/return`);
      await fetchRequest();
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not report the return.');
    } finally {
      setSubmitting(false);
    }
  };

  const reportDispute = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      await api.post(`/borrow-requests/${id}/dispute`, { description: disputeDescription });
      setDisputeDescription('');
      await fetchRequest();
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not report the dispute.');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="rental-detail-loading">Loading request…</div>;
  if (!request) return <div className="rental-detail-loading">{error || 'Request not found.'}</div>;

  const canManageRental = request.listing_id
    && user
    && [request.borrower_id, request.lender_id].includes(user.id);

  return (
    <section className="rental-detail-page container fade-in-up">
      <article className="rental-detail-card glass">
        <span className="rental-category">{request.category}</span>
        <h1>{request.title}</h1>
        <p className="rental-description">{request.description || 'No additional details provided.'}</p>
        <dl>
          <div><dt>Requested by</dt><dd>{request.borrower_name}</dd></div>
          <div><dt>Maximum daily price</dt><dd>{request.max_price_per_day ? `₹${request.max_price_per_day}` : 'Not specified'}</dd></div>
          <div><dt>Needed from</dt><dd>{request.needed_from ? new Date(request.needed_from).toLocaleDateString() : 'Flexible'}</dd></div>
          <div><dt>Needed until</dt><dd>{request.needed_until ? new Date(request.needed_until).toLocaleDateString() : 'Flexible'}</dd></div>
        </dl>
        {error && <div className="error-banner">{error}</div>}
        {canManageRental && (
          <div className="rental-lifecycle">
            <h2>Rental status</h2>
            <p>{request.returned_at ? 'Return reported' : 'Return not yet reported'}</p>
            {request.disputed_at && <p>A dispute has been reported for this rental.</p>}
            {!request.returned_at && (
              <button type="button" className="btn-primary" onClick={reportReturn} disabled={submitting}>
                Report item returned
              </button>
            )}
            {!request.disputed_at && (
              <form onSubmit={reportDispute}>
                <label htmlFor="dispute-description">Report a dispute</label>
                <textarea
                  id="dispute-description"
                  value={disputeDescription}
                  onChange={(event) => setDisputeDescription(event.target.value)}
                  maxLength={2000}
                  required
                />
                <button type="submit" className="btn-outline" disabled={submitting}>
                  Submit dispute
                </button>
              </form>
            )}
          </div>
        )}
      </article>
    </section>
  );
};

export default BorrowRequestDetail;
