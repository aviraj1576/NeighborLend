import React, { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { MessageCircle } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Badge from '../components/ui/Badge';
import EscrowStatusCard from '../components/EscrowStatusCard';
import HandoverConfirmation from '../components/HandoverConfirmation';
import ReturnSubmission from '../components/ReturnSubmission';
import ReturnInspection from '../components/ReturnInspection';
import './BorrowRequestDetail.css';

const dateTime = (value) => value ? new Date(/Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString('en-IN') : '—';

export default function BorrowRequestDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [request, setRequest] = useState(null);
  const [bookingId, setBookingId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [disputeDescription, setDisputeDescription] = useState('');
  const [rating, setRating] = useState(0);
  const [ratingComment, setRatingComment] = useState('');

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get(`/borrow-requests/${id}`);
      let next = data;
      const participant = user && [data.borrower_id, data.lender_id].includes(user.id);
      if (participant && data.listing_id && data.handover_status !== 'not_applicable') {
        const privateData = await api.get(`/borrow-requests/${id}/handover`);
        next = { ...data, ...privateData.data };
      }
      if (participant && data.listing_id) {
        try {
          const payment = await api.get(`/payments/by-request/${id}`);
          setBookingId(payment.data?.legacy ? null : payment.data?.id || null);
        } catch { setBookingId(null); }
      }
      setRequest(next); setError('');
    } catch (err) { setError(err.response?.data?.detail || 'Could not load this borrowing request.'); }
    finally { setLoading(false); }
  }, [id, user?.id]);

  useEffect(() => { refresh(); }, [refresh]);

  async function submitRating(forLender) {
    if (busy || !rating) return;
    setBusy(true); setError('');
    try {
      await api.post(`/borrow-requests/${id}/rate-${forLender ? 'lender' : 'borrower'}`, { rating, comment: ratingComment });
      setRating(0); setRatingComment(''); await refresh(); window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) { setError(err.response?.data?.detail || 'Could not submit rating.'); }
    finally { setBusy(false); }
  }

  async function legacyAction(path, payload = {}) {
    if (busy) return;
    setBusy(true); setError('');
    try { await api.post(path, payload); await refresh(); window.dispatchEvent(new Event('notifications:updated')); }
    catch (err) { setError(err.response?.data?.detail || 'Could not update the rental.'); }
    finally { setBusy(false); }
  }

  if (loading) return <div className="rental-detail-loading">Loading request…</div>;
  if (!request) return <div className="rental-detail-loading">{error || 'Request not found.'}</div>;

  const participant = user && [request.borrower_id, request.lender_id].includes(user.id);
  const isBorrower = user?.id === request.borrower_id;
  const isLender = user?.id === request.lender_id;
  const managed = request.handover_status && request.handover_status !== 'not_applicable';
  const canManage = Boolean(request.listing_id && participant);
  const canRate = request.handover_status === 'return_confirmed' && !request.disputed_at;
  const ratingTarget = isBorrower ? 'lender' : 'borrower';
  const alreadyRated = isBorrower ? request.lender_rating : request.borrower_rating;

  return <div className="rental-detail-page app-page"><div className="wrap">
    <section className="rental-detail-card card">
      <div className="rental-head"><Badge variant="outline" className="rental-category">{request.category}</Badge><h1 className="t-h1">{request.title}</h1></div>
      <p className="rental-description t-body">{request.description || 'No additional details provided.'}</p>
      <dl className="rental-meta">
        <div className="meta-row"><dt>Requested by</dt><dd>{request.borrower_name || '—'}</dd></div>
        <div className="meta-row"><dt>Maximum daily price</dt><dd>{request.max_price_per_day ? `₹${request.max_price_per_day}` : 'Not specified'}</dd></div>
        <div className="meta-row"><dt>Agreed from</dt><dd>{request.needed_from ? new Date(request.needed_from).toLocaleDateString('en-IN') : 'Flexible'}</dd></div>
        <div className="meta-row"><dt>Agreed until</dt><dd>{request.needed_until ? new Date(request.needed_until).toLocaleDateString('en-IN') : 'Flexible'}</dd></div>
      </dl>
      {error && <div className="error-banner" role="alert">{error}</div>}

      {canManage && <EscrowStatusCard request={request} user={user} api={api} onRentalChange={refresh} />}
      {managed && <>
        <HandoverConfirmation request={request} user={user} api={api} bookingId={bookingId} onChange={refresh} />
        {request.handover_status === 'lender_confirmed' && <div className="handover-active-details">
          <p>Handover confirmed: {dateTime(request.handover_confirmed_at)}</p>
          <p>Borrowing started: {dateTime(request.borrowing_started_at)}</p>
          <p>Return due: {dateTime(request.return_due_at)}</p>
          <p className="handover-active-label">Borrowing is active.</p>
        </div>}
        <ReturnSubmission request={request} api={api} bookingId={bookingId} onChange={refresh} />
        <ReturnInspection request={request} user={user} api={api} onChange={refresh} />
        {request.handover_status === 'return_confirmed' && <p className="rating-done" role="status">Return approved. Deposit settlement status is shown above.</p>}
      </>}

      {canRate && participant && !alreadyRated && <div className="handover-step rating-form">
        <h2 className="t-card">Rate the {ratingTarget}</h2>
        <div className="star-rating" role="radiogroup" aria-label="Choose a rating">
          {[1, 2, 3, 4, 5].map((value) => <button key={value} type="button" className={rating >= value ? 'star filled' : 'star'} aria-label={`${value} of 5`} aria-checked={rating === value} role="radio" onClick={() => setRating(value)}>★</button>)}
        </div>
        <Input id="rental-rating-comment" label="Optional comment" type="textarea" rows="3" maxLength={500} value={ratingComment} onChange={(event) => setRatingComment(event.target.value)} />
        <Button disabled={busy || !rating} onClick={() => submitRating(isBorrower)}>{busy ? 'Submitting…' : 'Submit rating'}</Button>
      </div>}
      {(request.lender_rating || request.borrower_rating) && <div className="rating-display">
        {request.lender_rating && <p><strong>Lender rating:</strong> {'★'.repeat(request.lender_rating)} ({request.lender_rating}/5) {request.lender_rating_comment}</p>}
        {request.borrower_rating && <p><strong>Borrower rating:</strong> {'★'.repeat(request.borrower_rating)} ({request.borrower_rating}/5) {request.borrower_rating_comment}</p>}
      </div>}

      {canManage && !managed && <section className="rental-lifecycle" aria-label="Legacy rental status">
        <h2 className="t-h2">Rental status</h2><p>{request.returned_at ? 'Return reported' : 'Return not yet reported'}</p>
        {request.disputed_at && <p role="status">A dispute has been reported for this rental.</p>}
        {!request.returned_at && <Button disabled={busy} onClick={() => legacyAction(`/borrow-requests/${id}/return`)}>{busy ? 'Reporting…' : 'Report item returned'}</Button>}
        {!request.disputed_at && <form onSubmit={(event) => { event.preventDefault(); legacyAction(`/borrow-requests/${id}/dispute`, { description: disputeDescription }); }}>
          <Input id="dispute-description" label="Report a dispute" type="textarea" rows="4" maxLength={2000} value={disputeDescription} onChange={(event) => setDisputeDescription(event.target.value)} required />
          <Button variant="secondary" type="submit" disabled={busy || !disputeDescription.trim()}>{busy ? 'Submitting…' : 'Submit dispute'}</Button>
        </form>}
      </section>}
      {request.conversation_id && request.handover_status === 'issue_reported' && <Link className="link handover-chat-link" to={`/messages/${request.conversation_id}`}><MessageCircle size={16} /> Open conversation</Link>}
    </section>
  </div></div>;
}
