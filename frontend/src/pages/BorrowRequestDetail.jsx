import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { MessageCircle, Upload, CheckCircle, Star, Eye } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import RentalEvidenceImage from '../components/RentalEvidenceImage.jsx';
import { apiErrorMessage, returnReviewState, uploadRentalEvidence } from '../components/paymentFlow.js';
import './BorrowRequestDetail.css';
import EscrowStatusCard from '../components/EscrowStatusCard.jsx';
import '../components/PaymentModal.css';

const HANDOVER_LABELS = {
  pending: 'Awaiting Product Handover',
  photos_uploaded: 'Photos Uploaded - Borrower to Confirm Receipt',
  borrower_confirmed: 'Borrower Confirmed - Lender to Confirm Handover',
  lender_confirmed: 'Handover Complete',
  issue_reported: 'Issue Reported',
  return_photos_uploaded: 'Return Photos Uploaded - Awaiting Lender Confirmation',
  return_confirmed: 'Return Confirmed',
};

const formatDateTime = (value) => value ? new Date(value).toLocaleString() : '—';

const BorrowRequestDetail = () => {
  const { id } = useParams();
  const { user } = useAuth();
  const [request, setRequest] = useState(null);
  const [paymentUnlocked, setPaymentUnlocked] = useState(false);
  const [paymentBooking, setPaymentBooking] = useState(null);
  const [conditionNote, setConditionNote] = useState('');
  const [disputeDescription, setDisputeDescription] = useState('');
  const [issueDescription, setIssueDescription] = useState('');
  const [issueFormOpen, setIssueFormOpen] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  // New state for photo uploads
  const [handoverPhotos, setHandoverPhotos] = useState([]);
  const [handoverPreviews, setHandoverPreviews] = useState([]);
  const [confirmPhotos, setConfirmPhotos] = useState([]);
  const [confirmPreviews, setConfirmPreviews] = useState([]);
  const [returnPhotos, setReturnPhotos] = useState([]);
  const [returnPreviews, setReturnPreviews] = useState([]);
  const [lenderRating, setLenderRating] = useState(0);
  const [borrowerRating, setBorrowerRating] = useState(0);
  const [lenderRatingComment, setLenderRatingComment] = useState('');
  const [borrowerRatingComment, setBorrowerRatingComment] = useState('');
  const [ratingFormOpen, setRatingFormOpen] = useState(false);
  const requestVersion = useRef(0);

  const fetchRequest = useCallback(async ({ strict = false } = {}) => {
    const version = ++requestVersion.current;
    try {
      let response;
      if (user) {
        try { response = await api.get(`/payments/requests/${id}/rental`, { timeout: 15000 }); }
        catch (err) {
          if (err.response?.status !== 403 && err.response?.status !== 404) throw err;
          response = await api.get(`/borrow-requests/${id}`, { timeout: 15000 });
        }
      } else response = await api.get(`/borrow-requests/${id}`, { timeout: 15000 });
      let nextRequest = response.data;
      const isParticipant = user && [nextRequest.borrower_id, nextRequest.lender_id].includes(user.id);
      if (isParticipant && nextRequest.listing_id && nextRequest.handover_status !== 'not_applicable') {
        const handover = await api.get(`/borrow-requests/${id}/handover`, { timeout: 15000 });
        nextRequest = { ...nextRequest, ...handover.data };
      }
      if (version !== requestVersion.current) return;
      setRequest(nextRequest);
      setError('');
    } catch (err) {
      if (version !== requestVersion.current) { if (strict) throw err; return; }
      setError(apiErrorMessage(err, 'Could not load this borrowing request.'));
      if (strict) throw err;
    } finally {
      setLoading(false);
    }
  }, [id, user?.id]);

  useEffect(() => {
    fetchRequest();
  }, [fetchRequest]);

  useEffect(() => {
    if (!request) return undefined;
    const isParticipant = user && [request.borrower_id, request.lender_id].includes(user.id);
    if (!isParticipant && !user?.is_admin) return undefined;
    const timer = window.setInterval(async () => {
      const version = ++requestVersion.current;
      try {
        const response = await api.get(`/payments/requests/${id}/rental`, { timeout: 15000 });
        if (version !== requestVersion.current) return;
        setRequest((current) => current ? { ...current, ...response.data } : current);
      } catch {
        // Keep the current request visible if a quiet background refresh fails.
      }
    }, 15000);
    return () => window.clearInterval(timer);
  }, [id, request?.handover_status, request?.borrower_id, request?.lender_id, user?.id]);

  const runHandoverAction = async (action, confirmMessage) => {
    if (!window.confirm(confirmMessage)) return;
    setSubmitting(true);
    setError('');
    try {
      await api.post(`/borrow-requests/${id}/handover/${action}`);
      await fetchRequest();
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not update the handover.');
    } finally {
      setSubmitting(false);
    }
  };

  // Photo upload handlers
  const handleHandoverPhotos = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 10) { alert('Maximum 10 photos'); return; }
    setHandoverPhotos(files);
    setHandoverPreviews(files.map(f => URL.createObjectURL(f)));
  };
  const handleConfirmPhotos = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 10) { alert('Maximum 10 photos'); return; }
    setConfirmPhotos(files);
    setConfirmPreviews(files.map(f => URL.createObjectURL(f)));
  };
  const handleReturnPhotos = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 10) { alert('Maximum 10 photos'); return; }
    setReturnPhotos(files);
    setReturnPreviews(files.map(f => URL.createObjectURL(f)));
  };

  const uploadHandoverPhotos = async () => {
    if (!handoverPhotos.length) return;
    setSubmitting(true); setError('');
    try {
      // First upload files to get URLs
      const urls = [];
      for (const file of handoverPhotos) {
        urls.push(await uploadRentalEvidence(api, paymentBooking?.id, file, 'handover'));
      }
      await api.post(`/borrow-requests/${id}/handover/upload-photos`, { photo_urls: urls });
      setHandoverPhotos([]); setHandoverPreviews([]);
      await fetchRequest();
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) { setError(err.response?.data?.detail || 'Could not upload photos.'); }
    finally { setSubmitting(false); }
  };

  const confirmHandoverWithPhotos = async () => {
    setSubmitting(true); setError('');
    try {
      // Upload files to /upload to get URLs
      const urls = [];
      for (const file of confirmPhotos) {
        urls.push(await uploadRentalEvidence(api, paymentBooking?.id, file, 'receipt'));
      }
      // Then confirm handover with photos using the correct endpoint
      await api.post(`/borrow-requests/${id}/handover/borrower-confirm`, { photo_urls: urls, condition_note: conditionNote });
      setConfirmPhotos([]); setConfirmPreviews([]);
      await fetchRequest();
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) { setError(err.response?.data?.detail || 'Could not confirm handover.'); }
    finally { setSubmitting(false); }
  };

  const uploadReturnPhotos = async () => {
    if (!returnPhotos.length) return;
    setSubmitting(true); setError('');
    try {
      const urls = [];
      for (const file of returnPhotos) {
        urls.push(await uploadRentalEvidence(api, paymentBooking?.id, file, 'return'));
      }
      await api.post(`/borrow-requests/${id}/return/upload-photos`, { photo_urls: urls });
      setReturnPhotos([]); setReturnPreviews([]);
      await fetchRequest();
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) { setError(err.response?.data?.detail || 'Could not upload return photos.'); }
    finally { setSubmitting(false); }
  };

  const confirmReturn = async (approved) => {
    setSubmitting(true); setError('');
    try {
      await api.post(`/borrow-requests/${id}/return/confirm`, { approved, condition_note: conditionNote });
      await fetchRequest();
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) { setError(err.response?.data?.detail || 'Could not confirm return.'); }
    finally { setSubmitting(false); }
  };

  const rateLender = async () => {
    if (!lenderRating) { alert('Please select a rating'); return; }
    setSubmitting(true); setError('');
    try {
      await api.post(`/borrow-requests/${id}/rate-lender`, { rating: lenderRating, comment: lenderRatingComment });
      setRatingFormOpen(false); setLenderRating(0); setLenderRatingComment('');
      await fetchRequest();
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) { setError(err.response?.data?.detail || 'Could not submit rating.'); }
    finally { setSubmitting(false); }
  };

  const rateBorrower = async () => {
    if (!borrowerRating) { alert('Please select a rating'); return; }
    setSubmitting(true); setError('');
    try {
      await api.post(`/borrow-requests/${id}/rate-borrower`, { rating: borrowerRating, comment: borrowerRatingComment });
      setRatingFormOpen(false); setBorrowerRating(0); setBorrowerRatingComment('');
      await fetchRequest();
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) { setError(err.response?.data?.detail || 'Could not submit rating.'); }
    finally { setSubmitting(false); }
  };

  const reportHandoverIssue = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      await api.post(`/borrow-requests/${id}/handover/report-issue`, { description: issueDescription });
      setIssueDescription('');
      setIssueFormOpen(false);
      await fetchRequest();
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not report the handover issue.');
    } finally {
      setSubmitting(false);
    }
  };

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
  const handoverManaged = request.handover_status && request.handover_status !== 'not_applicable';
  const isLender = user?.id === request.lender_id;
  const isBorrower = user?.id === request.borrower_id;
  const returnReview = returnReviewState(request, paymentBooking);
  const canUseReturnActions = canManageRental
    && (!handoverManaged || request.handover_status === 'lender_confirmed');

  return (
    <section className="rental-detail-page container fade-in-up">
      <article className="rental-detail-card glass">
        <span className="rental-category">{request.category}</span>
        <h1>{request.title}</h1>
        <p className="rental-description">{request.description || 'No additional details provided.'}</p>
        <dl>
          <div><dt>Requested by</dt><dd>{request.borrower_name}</dd></div>
          <div><dt>Maximum daily price</dt><dd>{request.max_price_per_day ? `₹${request.max_price_per_day}` : 'Not specified'}</dd></div>
          <div><dt>Agreed from</dt><dd>{request.needed_from ? new Date(request.needed_from).toLocaleDateString() : 'Flexible'}</dd></div>
          <div><dt>Agreed until</dt><dd>{request.needed_until ? new Date(request.needed_until).toLocaleDateString() : 'Flexible'}</dd></div>
        </dl>
        {error && <div className="error-banner" role="alert">{error}</div>}
        {(canManageRental || user?.is_admin) && <div className="photo-previews">
          {[...(request.handover_photos || []), ...(request.handover_confirmed_photos || []), ...(request.return_photos || [])].map((reference, i) =>
            <RentalEvidenceImage key={reference} reference={reference} api={api} alt={`Rental condition evidence ${i + 1}`} className="photo-preview" />)}
        </div>}
        {(canManageRental || user?.is_admin) && <p>{request.handover_condition_note} {request.return_condition_note}</p>}
        {canManageRental && <label>Condition note
          <textarea maxLength={2000} value={conditionNote} onChange={e => setConditionNote(e.target.value)} />
        </label>}
        {(canManageRental || user?.is_admin) && <EscrowStatusCard request={request} user={user} api={api} onStatus={setPaymentUnlocked} onBooking={setPaymentBooking} onRentalChange={fetchRequest} />}

        {handoverManaged && (
          <div className="rental-lifecycle handover-panel">
            <h2>Product handover</h2>
            <p className={`handover-status status-${request.handover_status}`}>
              {returnReview.label || HANDOVER_LABELS[request.handover_status] || request.handover_status}
            </p>
            {request.handover_marked_at && (
              <p className="handover-meta">Marked handed over: {formatDateTime(request.handover_marked_at)}</p>
            )}

            {/* Step 1: Lender uploads photos */}
            {request.handover_status === 'pending' && isLender && paymentUnlocked && (
              <div className="handover-step">
                <h3>Step 1: Upload Product Photos</h3>
                <p>Upload photos of the item before handing it over.</p>
                <input type="file" accept="image/*" multiple onChange={handleHandoverPhotos} disabled={submitting} />
                {handoverPreviews.length && (
                  <div className="photo-previews">
                    {handoverPreviews.map((preview, i) => (
                      <img key={i} src={preview} alt={`Handover ${i+1}`} className="photo-preview" />
                    ))}
                  </div>
                )}
                <button
                  type="button"
                  className="btn-primary"
                  disabled={submitting || !handoverPhotos.length}
                  onClick={uploadHandoverPhotos}
                >
                  {submitting ? 'Uploading…' : `Upload ${handoverPhotos.length} Photo(s)`}
                </button>
              </div>
            )}

            {/* Step 2: Borrower confirms receipt after seeing photos */}
            {request.handover_status === 'photos_uploaded' && isBorrower && paymentUnlocked && (
              <div className="handover-step">
                <h3>Step 2: Confirm You Received the Item</h3>
                <p>Review the lender's photos above. If the item looks correct, confirm you received it.</p>
                {request.handover_photos && request.handover_photos.length > 0 && (
                  <div className="photo-previews">
                    {request.handover_photos.map((url, i) => (
                      <RentalEvidenceImage key={i} reference={url} api={api} alt={`Lender Photo ${i+1}`} className="photo-preview" />
                    ))}
                  </div>
                )}
                <input type="file" accept="image/*" multiple onChange={handleConfirmPhotos} disabled={submitting} />
                {confirmPreviews.length && (
                  <div className="photo-previews">
                    {confirmPreviews.map((preview, i) => (
                      <img key={i} src={preview} alt={`Confirm ${i+1}`} className="photo-preview" />
                    ))}
                  </div>
                )}
                <button
                  type="button"
                  className="btn-primary"
                  disabled={submitting}
                  onClick={confirmHandoverWithPhotos}
                >
                  {submitting ? 'Confirming…' : 'I Received This Item'}
                </button>
                {!issueFormOpen && (
                  <button type="button" className="btn-outline" disabled={submitting} onClick={() => setIssueFormOpen(true)}>
                    Report an Issue
                  </button>
                )}
                {issueFormOpen && (
                  <form className="handover-issue-form" onSubmit={reportHandoverIssue}>
                    <label htmlFor="handover-issue-description">Describe the issue</label>
                    <textarea
                      id="handover-issue-description"
                      value={issueDescription}
                      onChange={(event) => setIssueDescription(event.target.value)}
                      maxLength={2000}
                      required
                    />
                    <div className="handover-issue-actions">
                      <button type="submit" className="btn-primary" disabled={submitting || !issueDescription.trim()}>
                        {submitting ? 'Submitting…' : 'Submit Issue'}
                      </button>
                      <button type="button" className="btn-outline" disabled={submitting} onClick={() => setIssueFormOpen(false)}>
                        Cancel
                      </button>
                    </div>
                  </form>
                )}
              </div>
            )}

            {/* Step 3: Lender confirms handover complete */}
            {request.handover_status === 'borrower_confirmed' && isLender && paymentUnlocked && (
              <div className="handover-step">
                <h3>Step 3: Confirm Handover Complete</h3>
                <p>Borrower has marked the item as received. Confirm the handover is complete.</p>
                <button
                  type="button"
                  className="btn-primary"
                  disabled={submitting}
                  onClick={() => runHandoverAction('lender-confirm', 'Confirm the handover is complete.')}
                >
                  {submitting ? 'Confirming…' : 'Confirm Handover Complete'}
                </button>
              </div>
            )}

            {request.handover_status === 'lender_confirmed' && (
              <div className="handover-active-details">
                <p>Handover confirmed: {formatDateTime(request.handover_confirmed_at)}</p>
                <p>Borrowing started: {formatDateTime(request.borrowing_started_at)}</p>
                <p>Return due: {formatDateTime(request.return_due_at)}</p>
                <p className="handover-active-label">Borrowing is active.</p>
              </div>
            )}

            {request.handover_status === 'issue_reported' && (
              <div className="handover-issue-details">
                <p><strong>Reported:</strong> {formatDateTime(request.handover_issue_reported_at)}</p>
                <p>{request.handover_issue_description}</p>
                <p>Borrowing will not start until the issue is addressed. Use your existing conversation to coordinate with the other party.</p>
                {request.conversation_id && (
                  <Link className="btn-outline handover-chat-link" to={`/messages/${request.conversation_id}`}>
                    <MessageCircle size={16} /> Open conversation
                  </Link>
                )}
              </div>
            )}

            {/* Step 4: Borrower uploads return photos */}
            {request.handover_status === 'lender_confirmed' && !request.returned_at && isBorrower && (
              <div className="handover-step return-section">
                <h3>Step 4: Upload Return Photos</h3>
                <p>Upload photos of the item being returned.</p>
                <input type="file" accept="image/*" multiple onChange={handleReturnPhotos} disabled={submitting} />
                {returnPreviews.length && (
                  <div className="photo-previews">
                    {returnPreviews.map((preview, i) => (
                      <img key={i} src={preview} alt={`Return ${i+1}`} className="photo-preview" />
                    ))}
                  </div>
                )}
                <button
                  type="button"
                  className="btn-primary"
                  disabled={submitting || !returnPhotos.length}
                  onClick={uploadReturnPhotos}
                >
                  {submitting ? 'Uploading…' : `Upload ${returnPhotos.length} Return Photo(s)`}
                </button>
              </div>
            )}

            {/* Step 5: Lender confirms return */}
            {returnReview.awaitingDecision && isLender && (
              <div className="handover-step return-section">
                <h3>Step 5: Confirm Return</h3>
                <p>Review the return photos and confirm the item was returned in good condition.</p>
                <button
                  type="button"
                  className="btn-primary"
                  disabled={submitting}
                  onClick={() => confirmReturn(true)}
                >
                  {submitting ? 'Confirming…' : 'Confirm Return - Item OK'}
                </button>
                <button
                  type="button"
                  className="btn-outline"
                  disabled={submitting}
                  onClick={() => confirmReturn(false)}
                >
                  Reject - Start Dispute
                </button>
              </div>
            )}

            {returnReview.disputed && request.returned_at && (
              <p role="status">{returnReview.reviewed
                ? 'Human review is recorded. Follow the authorized settlement status above; lender allocations remain simulated.'
                : 'Return condition is disputed. The deposit stays frozen until independent human review. Review the saved claim above; clean-return confirmation is unavailable.'}</p>
            )}

            {/* Step 6: Ratings after return confirmed */}
            {request.handover_status === 'return_confirmed' && !request.disputed_at && (
              <div className="handover-step rating-section">
                <h3>Step 6: Rate Each Other</h3>
                {isBorrower && !request.lender_rating && (
                  <div className="rating-form">
                    <h4>Rate the Lender</h4>
                    <div className="star-rating">
                      {[1,2,3,4,5].map(star => (
                        <span key={star} className={lenderRating >= star ? 'filled' : ''} onClick={() => setLenderRating(star)}>★</span>
                      ))}
                    </div>
                    <textarea
                      placeholder="Optional comment"
                      value={lenderRatingComment}
                      onChange={(e) => setLenderRatingComment(e.target.value)}
                      maxLength={500}
                    />
                    <button type="button" className="btn-primary" disabled={submitting || !lenderRating} onClick={rateLender}>
                      {submitting ? 'Submitting…' : 'Submit Rating'}
                    </button>
                  </div>
                )}
                {isLender && !request.borrower_rating && (
                  <div className="rating-form">
                    <h4>Rate the Borrower</h4>
                    <div className="star-rating">
                      {[1,2,3,4,5].map(star => (
                        <span key={star} className={borrowerRating >= star ? 'filled' : ''} onClick={() => setBorrowerRating(star)}>★</span>
                      ))}
                    </div>
                    <textarea
                      placeholder="Optional comment"
                      value={borrowerRatingComment}
                      onChange={(e) => setBorrowerRatingComment(e.target.value)}
                      maxLength={500}
                    />
                    <button type="button" className="btn-primary" disabled={submitting || !borrowerRating} onClick={rateBorrower}>
                      {submitting ? 'Submitting…' : 'Submit Rating'}
                    </button>
                  </div>
                )}
                {(request.lender_rating && isBorrower) || (request.borrower_rating && isLender) ? (
                  <p className="rating-done">Thanks for rating!</p>
                ) : null}
              </div>
            )}

            {/* Show existing ratings */}
            {request.lender_rating && (
              <div className="rating-display">
                <p><strong>Lender Rating:</strong> {'★'.repeat(request.lender_rating)} {'☆'.repeat(5 - request.lender_rating)} ({request.lender_rating}/5)</p>
                {request.lender_rating_comment && <p>{request.lender_rating_comment}</p>}
              </div>
            )}
            {request.borrower_rating && (
              <div className="rating-display">
                <p><strong>Borrower Rating:</strong> {'★'.repeat(request.borrower_rating)} {'☆'.repeat(5 - request.borrower_rating)} ({request.borrower_rating}/5)</p>
                {request.borrower_rating_comment && <p>{request.borrower_rating_comment}</p>}
              </div>
            )}
          </div>
        )}

        {/* Return/Dispute section (legacy) - only show if no handover managed */}
        {canUseReturnActions && !handoverManaged && (
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
