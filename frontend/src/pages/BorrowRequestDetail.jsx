import React, { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { MessageCircle, Star, Eye } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import { resolvePhotoUrl } from '../utils/photoUrl';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import SixPhotoCapture from '../components/damage/SixPhotoCapture';
import DamageReportView from '../components/damage/DamageReportView';
import BeforeAfterCompare from '../components/damage/BeforeAfterCompare';
import SupportChatButton from '../components/SupportChatButton';
import { apiError, getCheck, userPhotoPath } from '../components/damage/damageApi';
import './BorrowRequestDetail.css';

const HANDOVER_LABELS = {
  pending: 'Awaiting product handover',
  photos_uploaded: 'Photos uploaded — borrower to confirm receipt',
  borrower_confirmed: 'Borrower confirmed — lender to confirm handover',
  lender_confirmed: 'Handover complete',
  issue_reported: 'Issue reported',
  return_photos_uploaded: 'Return photos uploaded — awaiting lender confirmation',
  return_confirmed: 'Return confirmed',
  disputed: 'Dispute open — admins are reviewing',
  dispute_resolved: 'Dispute resolved',
};

const formatDateTime = (value) => (value ? new Date(value).toLocaleString() : '—');

const NON_RETURN_DISPUTE_DAYS = 7;

const extractToken = (text) => {
  const parts = String(text || '').trim().split(/[?#]/)[0].split('/').filter(Boolean);
  return parts.length ? parts[parts.length - 1] : '';
};

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

  const navigate = useNavigate();
  const [beforeComplete, setBeforeComplete] = useState(false);
  const [shareInfo, setShareInfo] = useState(null);
  const [copied, setCopied] = useState(false);
  const [pastedLink, setPastedLink] = useState('');
  const [damageCheck, setDamageCheck] = useState(null);
  const [damageDisputeReason, setDamageDisputeReason] = useState('');

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

  // Lender review: load the damage check, and poll while the AI comparison runs.
  const reviewCheckId = request?.damage_check_id;
  const reviewStates = ['return_photos_uploaded', 'disputed'];
  const reviewActive = Boolean(reviewCheckId && reviewStates.includes(request?.handover_status));
  const damagePathFor = useCallback((phase, view) => userPhotoPath(reviewCheckId, phase, view), [reviewCheckId]);

  useEffect(() => {
    if (!reviewActive) return;
    getCheck(reviewCheckId).then(setDamageCheck).catch(() => {});
  }, [reviewActive, reviewCheckId]);

  useEffect(() => {
    if (damageCheck?.status !== 'processing') return undefined;
    const timer = window.setInterval(() => {
      getCheck(damageCheck.id).then(setDamageCheck).catch(() => {});
    }, 3000);
    return () => window.clearInterval(timer);
  }, [damageCheck?.status, damageCheck?.id]);

  const refreshAfter = async () => {
    await fetchRequest();
    window.dispatchEvent(new Event('notifications:updated'));
  };

  const startDamageCheck = async () => {
    setSubmitting(true);
    setError('');
    try {
      await api.post(`/borrow-requests/${id}/damage-check/start`);
      await fetchRequest();
    } catch (err) {
      setError(apiError(err, 'Could not start the condition check.'));
    } finally {
      setSubmitting(false);
    }
  };

  const shareDamageCheck = async () => {
    setSubmitting(true);
    setError('');
    try {
      const res = await api.post(`/borrow-requests/${id}/damage-check/share`);
      setShareInfo(res.data);
      await refreshAfter();
    } catch (err) {
      setError(apiError(err, 'Could not share the condition check.'));
    } finally {
      setSubmitting(false);
    }
  };

  const copyDamageLink = async (token) => {
    const url = `${window.location.origin}/damage-check/${token}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt('Copy this link', url);
    }
  };

  const approveReturn = async () => {
    if (!window.confirm('Approve this return? The lend will be closed.')) return;
    setSubmitting(true);
    setError('');
    try {
      await api.post(`/borrow-requests/${id}/return/approve`);
      await refreshAfter();
    } catch (err) {
      setError(apiError(err, 'Could not approve the return.'));
    } finally {
      setSubmitting(false);
    }
  };

  const raiseDamageDispute = async () => {
    const reason = damageDisputeReason.trim();
    if (!reason) return;
    if (!window.confirm('Send this dispute to NeighborLend admins? They will review both photo sets and decide.')) return;
    setSubmitting(true);
    setError('');
    try {
      await api.post(`/borrow-requests/${id}/return/dispute`, { reason });
      setDamageDisputeReason('');
      await refreshAfter();
    } catch (err) {
      setError(apiError(err, 'Could not raise the dispute.'));
    } finally {
      setSubmitting(false);
    }
  };

  const openPastedLink = () => {
    const token = extractToken(pastedLink);
    if (!token) {
      setError('Paste the damage-check link first.');
      return;
    }
    navigate(`/damage-check/${token}`);
  };

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
  const dueAt = request.return_due_at ? new Date(request.return_due_at).getTime() : null;
  const earlyReturn = dueAt !== null && dueAt > Date.now();
  const notReturnedDispute = dueAt !== null && Date.now() > dueAt + NON_RETURN_DISPUTE_DAYS * 86400000;
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
    <div className="rental-detail-page app-page">
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

              {/* Step 1: Lender documents the item's condition (6-photo damage check) */}
              {request.handover_status === 'pending' && isLender && (
                <div className="handover-step">
                  <h3 className="t-card">Step 1: Document the item&rsquo;s condition</h3>
                  <p className="t-body">
                    Take 6 photos before handing the item over. The borrower receives a link to them and uses it again on return.
                  </p>
                  {!request.damage_check_id ? (
                    <Button variant="primary" disabled={submitting} onClick={startDamageCheck}>
                      {submitting ? 'Starting…' : 'Start condition check'}
                    </Button>
                  ) : (
                    <>
                      <SixPhotoCapture
                        checkId={request.damage_check_id}
                        phase="before"
                        onComplete={() => setBeforeComplete(true)}
                      />
                      <Button variant="primary" disabled={submitting || !beforeComplete} onClick={shareDamageCheck}>
                        {submitting ? 'Sharing…' : 'Share with borrower'}
                      </Button>
                    </>
                  )}
                  <div className="support-chat-slot">
                    <SupportChatButton step="handover_photos" entityType="borrow_request" entityId={request.id} />
                  </div>
                </div>
              )}

              {request.handover_status === 'photos_uploaded' && isLender && request.damage_link_token && (
                <div className="handover-step">
                  <h3 className="t-card">Condition photos shared</h3>
                  <p className="t-body">
                    The borrower was notified. The link below only works for you and the borrower.
                  </p>
                  <div className="damage-link-row">
                    <code className="damage-link">{`${window.location.origin}/damage-check/${request.damage_link_token}`}</code>
                    <Button variant="secondary" size="sm" onClick={() => copyDamageLink(request.damage_link_token)}>
                      {copied ? 'Copied' : 'Copy link'}
                    </Button>
                  </div>
                  <Link className="link handover-chat-link" to={`/damage-check/${request.damage_link_token}`}>
                    Open the photos
                  </Link>
                  {shareInfo && <p className="t-small muted">Link valid until {new Date(shareInfo.expires_at).toLocaleDateString()}.</p>}
                </div>
              )}

              {/* Step 2: Borrower confirms receipt */}
              {request.handover_status === 'photos_uploaded' && isBorrower && (
                <div className="handover-step">
                  <h3 className="t-card">Step 2: Confirm you received the item</h3>
                  <p className="t-body">
                    Review the lender&rsquo;s photos above. If the item looks correct, confirm you received it.
                  </p>
                  {request.damage_link_token && (
                    <Button asChild variant="secondary">
                      <Link to={`/damage-check/${request.damage_link_token}`}>View the lender&rsquo;s 6 condition photos</Link>
                    </Button>
                  )}
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
                  <div className="support-chat-slot">
                    <SupportChatButton step="handover_confirm" entityType="borrow_request" entityId={request.id} />
                  </div>
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

              {/* Step 4: Borrower returns the item using the damage-check link */}
              {request.handover_status === 'lender_confirmed' && !request.returned_at && isBorrower && request.damage_check_id && (
                <div className="handover-step return-section">
                  <h3 className="t-card">Step 4: Return the item</h3>
                  <p className="t-body">
                    {earlyReturn
                      ? 'Returning before the due date? You can return today.'
                      : 'Your return is due.'}{' '}
                    Take 6 return photos using your damage-check link.
                  </p>
                  {request.damage_link_token ? (
                    <Button asChild variant="primary">
                      <Link to={`/damage-check/${request.damage_link_token}`}>
                        {earlyReturn ? 'Return today' : 'Open return check'}
                      </Link>
                    </Button>
                  ) : (
                    <p className="t-body">Your damage-check link is missing. Paste it below.</p>
                  )}
                  <div className="damage-paste">
                    <Input
                      id="damage-link-paste"
                      label="Or paste your damage-check link"
                      value={pastedLink}
                      onChange={(e) => setPastedLink(e.target.value)}
                      placeholder="https://…/damage-check/…"
                    />
                    <Button variant="secondary" onClick={openPastedLink}>Open link</Button>
                  </div>
                  <div className="support-chat-slot">
                    <SupportChatButton step="return_flow" entityType="borrow_request" entityId={request.id} />
                  </div>
                </div>
              )}

              {/* Legacy Step 4 (lends without a damage check): borrower uploads return photos */}
              {request.handover_status === 'lender_confirmed' && !request.returned_at && isBorrower && !request.damage_check_id && (
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

              {/* Lender: item never returned, a week past the due date */}
              {request.handover_status === 'lender_confirmed' && isLender && request.damage_check_id && notReturnedDispute && (
                <div className="handover-step return-section">
                  <h3 className="t-card">Item not returned?</h3>
                  <p className="t-body">
                    The return was due on {formatDateTime(request.return_due_at)}. You can raise a dispute for NeighborLend admins to decide.
                  </p>
                  <Input
                    id="damage-dispute-reason"
                    label="What happened?"
                    type="textarea"
                    rows="3"
                    maxLength={2000}
                    value={damageDisputeReason}
                    onChange={(e) => setDamageDisputeReason(e.target.value)}
                  />
                  <Button variant="secondary" disabled={submitting || !damageDisputeReason.trim()} onClick={raiseDamageDispute}>
                    Raise dispute
                  </Button>
                </div>
              )}

              {/* Step 5: Lender reviews the return (before/after photos + AI log) */}
              {request.handover_status === 'return_photos_uploaded' && isLender && request.damage_check_id && (
                <div className="handover-step return-section">
                  <h3 className="t-card">Step 5: Review the return</h3>
                  <p className="t-body">
                    Compare the before and after photos and the AI-assisted log. Approve the return, or raise a dispute
                    for NeighborLend admins to decide. If you do nothing, the return is approved automatically 72 hours
                    after it was submitted.
                  </p>
                  {damageCheck ? (
                    <>
                      <BeforeAfterCompare pathFor={damagePathFor} report={damageCheck.report} />
                      <DamageReportView report={damageCheck.report} status={damageCheck.status} />
                    </>
                  ) : (
                    <p className="t-body">Loading photos…</p>
                  )}
                  <Button variant="primary" disabled={submitting} onClick={approveReturn}>
                    {submitting ? 'Working…' : 'Approve return'}
                  </Button>
                  <Input
                    id="damage-dispute-reason"
                    label="Not happy with the condition? Describe the problem"
                    type="textarea"
                    rows="3"
                    maxLength={2000}
                    value={damageDisputeReason}
                    onChange={(e) => setDamageDisputeReason(e.target.value)}
                  />
                  <Button variant="secondary" disabled={submitting || !damageDisputeReason.trim()} onClick={raiseDamageDispute}>
                    Raise dispute
                  </Button>
                  <div className="support-chat-slot">
                    <SupportChatButton step="dispute" entityType="borrow_request" entityId={request.id} />
                  </div>
                </div>
              )}

              {request.handover_status === 'return_photos_uploaded' && isBorrower && request.damage_check_id && (
                <div className="handover-step return-section">
                  <h3 className="t-card">Return submitted</h3>
                  <p className="t-body">
                    The lender is reviewing your return photos. If they do not respond within 72 hours it is approved automatically.
                  </p>
                </div>
              )}

              {/* Disputed: both parties see the photos while admins decide */}
              {request.handover_status === 'disputed' && (
                <div className="handover-step return-section">
                  <h3 className="t-card">Dispute open</h3>
                  <p className="t-body">
                    NeighborLend admins are reviewing both photo sets and will notify you of the decision.
                  </p>
                  {request.dispute_description && <p className="t-small muted">Reason given: {request.dispute_description}</p>}
                  {damageCheck && damageCheck.after_views?.length === 6 && (
                    <>
                      <BeforeAfterCompare pathFor={damagePathFor} report={damageCheck.report} />
                      <DamageReportView report={damageCheck.report} status={damageCheck.status} />
                    </>
                  )}
                  <div className="support-chat-slot">
                    <SupportChatButton step="dispute" entityType="borrow_request" entityId={request.id} />
                  </div>
                </div>
              )}

              {request.handover_status === 'dispute_resolved' && (
                <div className="handover-step return-section">
                  <h3 className="t-card">Dispute resolved</h3>
                  <p className="t-body">An admin has decided this dispute. The decision was sent to your inbox.</p>
                </div>
              )}

              {/* Legacy Step 5 (lends without a damage check): lender confirms return */}
              {request.handover_status === 'return_photos_uploaded' && isLender && !request.damage_check_id && (
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
