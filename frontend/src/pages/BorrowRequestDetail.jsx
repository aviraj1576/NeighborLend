import React, { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { MessageCircle, Star, Eye } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import { resolvePhotoUrl } from '../utils/photoUrl';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import './BorrowRequestDetail.css';

const HANDOVER_LABELS = {
  pending: 'Awaiting product handover',
  photos_uploaded: 'Photos uploaded — borrower to confirm receipt',
  borrower_confirmed: 'Borrower confirmed — lender to confirm handover',
  lender_confirmed: 'Handover complete',
  issue_reported: 'Issue reported',
  return_photos_uploaded: 'Return photos uploaded — awaiting lender confirmation',
  return_confirmed: 'Return confirmed',
};

const formatDateTime = (value) => (value ? new Date(value).toLocaleString() : '—');

const BorrowRequestDetail = () => {
  const { id } = useParams();
  const { user } = useAuth();
  const [request, setRequest] = useState(null);
  const [disputeDescription, setDisputeDescription] = useState('');
  const [issueDescription, setIssueDescription] = useState('');
  const [issueFormOpen, setIssueFormOpen] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

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

  const fetchRequest = useCallback(async () => {
    try {
      const response = await api.get(`/borrow-requests/${id}`);
      let nextRequest = response.data;
      const isParticipant = user && [nextRequest.borrower_id, nextRequest.lender_id].includes(user.id);
      if (isParticipant && nextRequest.listing_id && nextRequest.handover_status !== 'not_applicable') {
        const handover = await api.get(`/borrow-requests/${id}/handover`);
        nextRequest = { ...nextRequest, ...handover.data };
      }
      setRequest(nextRequest);
      setError('');
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not load this borrowing request.');
    } finally {
      setLoading(false);
    }
  }, [id, user?.id]);

  useEffect(() => {
    fetchRequest();
  }, [fetchRequest]);

  useEffect(() => {
    if (!request || !['pending', 'photos_uploaded', 'borrower_confirmed'].includes(request.handover_status)) return undefined;
    const isParticipant = user && [request.borrower_id, request.lender_id].includes(user.id);
    if (!isParticipant) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const response = await api.get(`/borrow-requests/${id}/handover`);
        setRequest((current) => (current ? { ...current, ...response.data } : current));
      } catch {
        // Keep current request visible if a quiet background refresh fails.
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

  const handleHandoverPhotos = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 10) { alert('Maximum 10 photos'); return; }
    setHandoverPhotos(files);
    setHandoverPreviews(files.map((f) => URL.createObjectURL(f)));
  };
  const handleConfirmPhotos = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 10) { alert('Maximum 10 photos'); return; }
    setConfirmPhotos(files);
    setConfirmPreviews(files.map((f) => URL.createObjectURL(f)));
  };
  const handleReturnPhotos = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 10) { alert('Maximum 10 photos'); return; }
    setReturnPhotos(files);
    setReturnPreviews(files.map((f) => URL.createObjectURL(f)));
  };

  const uploadHandoverPhotos = async () => {
    if (!handoverPhotos.length) return;
    setSubmitting(true);
    setError('');
    try {
      const urls = [];
      for (const file of handoverPhotos) {
        const form = new FormData();
        form.append('file', file);
        const res = await api.post('/upload', form);
        urls.push(res.data.url);
      }
      await api.post(`/borrow-requests/${id}/handover/upload-photos`, { photo_urls: urls });
      setHandoverPhotos([]);
      setHandoverPreviews([]);
      await fetchRequest();
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not upload photos.');
    } finally {
      setSubmitting(false);
    }
  };

  const confirmHandoverWithPhotos = async () => {
    setSubmitting(true);
    setError('');
    try {
      const urls = [];
      for (const file of confirmPhotos) {
        const form = new FormData();
        form.append('file', file);
        const res = await api.post('/upload', form);
        urls.push(res.data.url);
      }
      await api.post(`/borrow-requests/${id}/handover/borrower-confirm`, { photo_urls: urls });
      setConfirmPhotos([]);
      setConfirmPreviews([]);
      await fetchRequest();
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not confirm handover.');
    } finally {
      setSubmitting(false);
    }
  };

  const uploadReturnPhotos = async () => {
    if (!returnPhotos.length) return;
    setSubmitting(true);
    setError('');
    try {
      const urls = [];
      for (const file of returnPhotos) {
        const form = new FormData();
        form.append('file', file);
        const res = await api.post('/upload', form);
        urls.push(res.data.url);
      }
      await api.post(`/borrow-requests/${id}/return/upload-photos`, { photo_urls: urls });
      setReturnPhotos([]);
      setReturnPreviews([]);
      await fetchRequest();
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not upload return photos.');
    } finally {
      setSubmitting(false);
    }
  };

  const confirmReturn = async (approved) => {
    setSubmitting(true);
    setError('');
    try {
      await api.post(`/borrow-requests/${id}/return/confirm`, { approved });
      await fetchRequest();
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not confirm return.');
    } finally {
      setSubmitting(false);
    }
  };

  const rateLender = async () => {
    if (!lenderRating) { alert('Please select a rating'); return; }
    setSubmitting(true);
    setError('');
    try {
      await api.post(`/borrow-requests/${id}/rate-lender`, { rating: lenderRating, comment: lenderRatingComment });
      setRatingFormOpen(false);
      setLenderRating(0);
      setLenderRatingComment('');
      await fetchRequest();
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not submit rating.');
    } finally {
      setSubmitting(false);
    }
  };

  const rateBorrower = async () => {
    if (!borrowerRating) { alert('Please select a rating'); return; }
    setSubmitting(true);
    setError('');
    try {
      await api.post(`/borrow-requests/${id}/rate-borrower`, { rating: borrowerRating, comment: borrowerRatingComment });
      setRatingFormOpen(false);
      setBorrowerRating(0);
      setBorrowerRatingComment('');
      await fetchRequest();
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not submit rating.');
    } finally {
      setSubmitting(false);
    }
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
  const canUseReturnActions = canManageRental
    && (!handoverManaged || request.handover_status === 'lender_confirmed');

  const stars = (rating, onSelect, current) => (
    <div className="star-rating" role="radiogroup" aria-label="Rating">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          className={current >= star ? 'star filled' : 'star'}
          onClick={() => onSelect(star)}
          aria-label={`Rate ${star} of 5`}
        >
          ★
        </button>
      ))}
    </div>
  );

  return (
    <div className="rental-detail-page section" style={{ '--h': '2' }}>
      <div className="wrap">
        <section className="rental-detail-card card">
          <div className="rental-head">
            <Badge variant="outline" className="rental-category">{request.category}</Badge>
            <h1 className="t-h1">{request.title}</h1>
          </div>
          <p className="rental-description t-body">
            {request.description || 'No additional details provided.'}
          </p>

          <dl className="rental-meta">
            <div className="meta-row">
              <dt>Requested by</dt>
              <dd>{request.borrower_name}</dd>
            </div>
            <div className="meta-row">
              <dt>Maximum daily price</dt>
              <dd>{request.max_price_per_day ? `₹${request.max_price_per_day}` : 'Not specified'}</dd>
            </div>
            <div className="meta-row">
              <dt>Agreed from</dt>
              <dd>{request.needed_from ? new Date(request.needed_from).toLocaleDateString() : 'Flexible'}</dd>
            </div>
            <div className="meta-row">
              <dt>Agreed until</dt>
              <dd>{request.needed_until ? new Date(request.needed_until).toLocaleDateString() : 'Flexible'}</dd>
            </div>
          </dl>

          {error && (
            <div className="error-banner" role="alert">{error}</div>
          )}

          {handoverManaged && (
            <div className="rental-lifecycle handover-panel">
              <h2 className="t-h2">Product handover</h2>
              <p className={['handover-status', `status-${request.handover_status}`].join(' ')}>
                {HANDOVER_LABELS[request.handover_status] || request.handover_status}
              </p>
              {request.handover_marked_at && (
                <p className="handover-meta t-small muted">
                  Marked handed over: {formatDateTime(request.handover_marked_at)}
                </p>
              )}

              {/* Step 1: Lender uploads photos */}
              {request.handover_status === 'pending' && isLender && (
                <div className="handover-step">
                  <h3 className="t-card">Step 1: Upload product photos</h3>
                  <p className="t-body">Upload photos of the item before handing it over.</p>
                  <div className="photo-input">
                    <input
                      id="handover-photos"
                      type="file"
                      accept="image/*"
                      multiple
                      onChange={handleHandoverPhotos}
                      disabled={submitting}
                    />
                  </div>
                  {handoverPreviews.length && (
                    <div className="photo-previews">
                      {handoverPreviews.map((preview, i) => (
                        <img key={i} src={preview} alt={`Handover ${i + 1}`} className="photo-preview" />
                      ))}
                    </div>
                  )}
                  <Button
                    variant="primary"
                    disabled={submitting || !handoverPhotos.length}
                    onClick={uploadHandoverPhotos}
                  >
                    {submitting ? 'Uploading…' : `Upload ${handoverPhotos.length} photo(s)`}
                  </Button>
                </div>
              )}

              {/* Step 2: Borrower confirms receipt */}
              {request.handover_status === 'photos_uploaded' && isBorrower && (
                <div className="handover-step">
                  <h3 className="t-card">Step 2: Confirm you received the item</h3>
                  <p className="t-body">
                    Review the lender&rsquo;s photos above. If the item looks correct, confirm you received it.
                  </p>
                  {request.handover_photos && request.handover_photos.length > 0 && (
                    <div className="photo-previews lender-photos">
                      {request.handover_photos.map((url, i) => (
                        <img
                          key={i}
                          src={resolvePhotoUrl(url)}
                          alt={`Lender Photo ${i + 1}`}
                          className="photo-preview"
                        />
                      ))}
                    </div>
                  )}
                  <div className="photo-input">
                    <input
                      id="confirm-photos"
                      type="file"
                      accept="image/*"
                      multiple
                      onChange={handleConfirmPhotos}
                      disabled={submitting}
                    />
                  </div>
                  {confirmPreviews.length && (
                    <div className="photo-previews">
                      {confirmPreviews.map((preview, i) => (
                        <img key={i} src={preview} alt={`Confirm ${i + 1}`} className="photo-preview" />
                      ))}
                    </div>
                  )}
                  <Button
                    variant="primary"
                    disabled={submitting}
                    onClick={confirmHandoverWithPhotos}
                  >
                    {submitting ? 'Confirming…' : 'I received this item'}
                  </Button>
                  {!issueFormOpen && (
                    <Button variant="secondary" disabled={submitting} onClick={() => setIssueFormOpen(true)}>
                      Report an issue
                    </Button>
                  )}
                  {issueFormOpen && (
                    <form className="handover-issue-form" onSubmit={reportHandoverIssue}>
                      <Input
                        id="handover-issue-description"
                        label="Describe the issue"
                        type="textarea"
                        rows="4"
                        maxLength={2000}
                        value={issueDescription}
                        onChange={(event) => setIssueDescription(event.target.value)}
                        required
                      />
                      <div className="handover-issue-actions">
                        <Button variant="primary" type="submit" disabled={submitting || !issueDescription.trim()}>
                          {submitting ? 'Submitting…' : 'Submit issue'}
                        </Button>
                        <Button variant="secondary" type="button" disabled={submitting} onClick={() => setIssueFormOpen(false)}>
                          Cancel
                        </Button>
                      </div>
                    </form>
                  )}
                </div>
              )}

              {/* Step 3: Lender confirms handover complete */}
              {request.handover_status === 'borrower_confirmed' && isLender && (
                <div className="handover-step">
                  <h3 className="t-card">Step 3: Confirm handover complete</h3>
                  <p className="t-body">
                    Borrower has marked the item as received. Confirm the handover is complete.
                  </p>
                  <Button
                    variant="primary"
                    disabled={submitting}
                    onClick={() => runHandoverAction('lender-confirm', 'Confirm the handover is complete.')}
                  >
                    {submitting ? 'Confirming…' : 'Confirm handover complete'}
                  </Button>
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
                  <p>
                    Borrowing will not start until the issue is addressed. Use your existing conversation to
                    coordinate with the other party.
                  </p>
                  {request.conversation_id && (
                    <Link className="link handover-chat-link" to={`/messages/${request.conversation_id}`}>
                      <MessageCircle size={16} /> Open conversation
                    </Link>
                  )}
                </div>
              )}

              {/* Step 4: Borrower uploads return photos */}
              {request.handover_status === 'lender_confirmed' && !request.returned_at && isBorrower && (
                <div className="handover-step return-section">
                  <h3 className="t-card">Step 4: Upload return photos</h3>
                  <p className="t-body">Upload photos of the item being returned.</p>
                  <div className="photo-input">
                    <input
                      id="return-photos"
                      type="file"
                      accept="image/*"
                      multiple
                      onChange={handleReturnPhotos}
                      disabled={submitting}
                    />
                  </div>
                  {returnPreviews.length && (
                    <div className="photo-previews">
                      {returnPreviews.map((preview, i) => (
                        <img key={i} src={preview} alt={`Return ${i + 1}`} className="photo-preview" />
                      ))}
                    </div>
                  )}
                  <Button
                    variant="primary"
                    disabled={submitting || !returnPhotos.length}
                    onClick={uploadReturnPhotos}
                  >
                    {submitting ? 'Uploading…' : `Upload ${returnPhotos.length} return photo(s)`}
                  </Button>
                </div>
              )}

              {/* Step 5: Lender confirms return */}
              {request.handover_status === 'return_photos_uploaded' && isLender && (
                <div className="handover-step return-section">
                  <h3 className="t-card">Step 5: Confirm return</h3>
                  <p className="t-body">
                    Review the return photos and confirm the item was returned in good condition.
                  </p>
                  <Button variant="primary" disabled={submitting} onClick={() => confirmReturn(true)}>
                    {submitting ? 'Confirming…' : 'Confirm return — item OK'}
                  </Button>
                  <Button variant="secondary" disabled={submitting} onClick={() => confirmReturn(false)}>
                    Reject — start dispute
                  </Button>
                </div>
              )}

              {/* Step 6: Ratings after return confirmed */}
              {request.handover_status === 'return_confirmed' && !request.disputed_at && (
                <div className="handover-step rating-section">
                  <h3 className="t-card">Step 6: Rate each other</h3>
                  {isBorrower && !request.lender_rating && (
                    <div className="rating-form">
                      <h4 className="t-card">Rate the lender</h4>
                      {stars(lenderRating, setLenderRating, lenderRating)}
                      <Input
                        id="lender-comment"
                        label="Optional comment"
                        type="textarea"
                        rows="3"
                        maxLength={500}
                        value={lenderRatingComment}
                        onChange={(e) => setLenderRatingComment(e.target.value)}
                      />
                      <Button
                        variant="primary"
                        disabled={submitting || !lenderRating}
                        onClick={rateLender}
                      >
                        {submitting ? 'Submitting…' : 'Submit rating'}
                      </Button>
                    </div>
                  )}
                  {isLender && !request.borrower_rating && (
                    <div className="rating-form">
                      <h4 className="t-card">Rate the borrower</h4>
                      {stars(borrowerRating, setBorrowerRating, borrowerRating)}
                      <Input
                        id="borrower-comment"
                        label="Optional comment"
                        type="textarea"
                        rows="3"
                        maxLength={500}
                        value={borrowerRatingComment}
                        onChange={(e) => setBorrowerRatingComment(e.target.value)}
                      />
                      <Button
                        variant="primary"
                        disabled={submitting || !borrowerRating}
                        onClick={rateBorrower}
                      >
                        {submitting ? 'Submitting…' : 'Submit rating'}
                      </Button>
                    </div>
                  )}
                  {((request.lender_rating && isBorrower) || (request.borrower_rating && isLender)) && (
                    <p className="rating-done">Thanks for rating!</p>
                  )}
                </div>
              )}

              {/* Existing ratings */}
              {request.lender_rating && (
                <div className="rating-display">
                  <p><strong>Lender rating:</strong> {'★'.repeat(request.lender_rating)}{'☆'.repeat(5 - request.lender_rating)} ({request.lender_rating}/5)</p>
                  {request.lender_rating_comment && <p className="t-small muted">{request.lender_rating_comment}</p>}
                </div>
              )}
              {request.borrower_rating && (
                <div className="rating-display">
                  <p><strong>Borrower rating:</strong> {'★'.repeat(request.borrower_rating)}{'☆'.repeat(5 - request.borrower_rating)} ({request.borrower_rating}/5)</p>
                  {request.borrower_rating_comment && <p className="t-small muted">{request.borrower_rating_comment}</p>}
                </div>
              )}
            </div>
          )}

          {/* Return/Dispute section (legacy) — only if no handover managed */}
          {canUseReturnActions && !handoverManaged && (
            <div className="rental-lifecycle">
              <h2 className="t-h2">Rental status</h2>
              <p>{request.returned_at ? 'Return reported' : 'Return not yet reported'}</p>
              {request.disputed_at && <p>A dispute has been reported for this rental.</p>}
              {!request.returned_at && (
                <Button variant="primary" disabled={submitting} onClick={reportReturn}>
                  {submitting ? 'Reporting…' : 'Report item returned'}
                </Button>
              )}
              {!request.disputed_at && (
                <form onSubmit={reportDispute}>
                  <Input
                    id="dispute-description"
                    label="Report a dispute"
                    type="textarea"
                    rows="4"
                    maxLength={2000}
                    value={disputeDescription}
                    onChange={(event) => setDisputeDescription(event.target.value)}
                    required
                  />
                  <Button variant="secondary" type="submit" disabled={submitting}>
                    Submit dispute
                  </Button>
                </form>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

export default BorrowRequestDetail;
