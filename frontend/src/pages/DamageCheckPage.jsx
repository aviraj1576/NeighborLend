import React, { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import api from '../api/client';
import Button from '../components/ui/Button';
import Badge from '../components/ui/Badge';
import SupportChatButton from '../components/SupportChatButton';
import AuthImage from '../components/damage/AuthImage';
import SixPhotoCapture from '../components/damage/SixPhotoCapture';
import DamageReportView from '../components/damage/DamageReportView';
import BeforeAfterCompare from '../components/damage/BeforeAfterCompare';
import { LABELS, VIEWS, apiError, getCheck, userPhotoPath } from '../components/damage/damageApi';
import './DamageCheckPage.css';

const LINK_ERRORS = {
  403: 'This link belongs to a different lend. Sign in with the account that is part of this lend.',
  404: 'This link is invalid or no longer exists.',
  410: 'This link has expired, or the lend is already closed.',
};

const formatDate = (value) => (value ? new Date(value).toLocaleDateString() : '—');

export default function DamageCheckPage() {
  const { token } = useParams();
  const [link, setLink] = useState(null);
  const [lend, setLend] = useState(null);
  const [check, setCheck] = useState(null);
  const [failure, setFailure] = useState(null);
  const [loading, setLoading] = useState(true);
  const [capturing, setCapturing] = useState(false);
  const [photosReady, setPhotosReady] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState('');

  const load = useCallback(async () => {
    try {
      const resolved = (await api.get(`/damage-links/${token}`)).data;
      const [c, b] = await Promise.all([
        getCheck(resolved.check_id),
        api.get(`/borrow-requests/${resolved.borrow_request_id}`),
      ]);
      setLink(resolved);
      setCheck(c);
      setLend(b.data);
      setFailure(null);
    } catch (err) {
      const status = err.response?.status;
      setFailure({ status, message: LINK_ERRORS[status] || apiError(err, 'Could not open this link.') });
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  // Poll the AI analysis while it runs.
  useEffect(() => {
    if (!check || check.status !== 'processing') return undefined;
    const timer = window.setInterval(async () => {
      try { setCheck(await getCheck(check.id)); } catch { /* keep the current view */ }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [check]);

  const checkId = check?.id;
  const pathFor = useCallback((phase, view) => userPhotoPath(checkId, phase, view), [checkId]);

  const submitReturn = async () => {
    setSubmitting(true);
    setActionError('');
    try {
      await api.post(`/borrow-requests/${link.borrow_request_id}/return/submit`);
      setCapturing(false);
      await load();
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) {
      setActionError(apiError(err, 'Could not submit the return.'));
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="damage-page-loading">Opening damage check…</div>;

  if (failure) {
    return (
      <div className="damage-page app-page">
        <div className="wrap">
          <section className="damage-card card" role="alert">
            <h1 className="t-h1">Can’t open this link</h1>
            <p className="t-body">{failure.message}</p>
            <div className="damage-actions">
              <Button asChild variant="primary"><Link to="/my-borrow-requests">Go to my requests</Link></Button>
              <Button asChild variant="secondary"><Link to="/inbox">Open inbox</Link></Button>
              <SupportChatButton step="damage_link" />
            </div>
          </section>
        </div>
      </div>
    );
  }

  const isBorrower = link.role === 'borrower';
  const status = link.handover_status;
  const due = link.return_due_at ? new Date(link.return_due_at) : null;
  const hasAfter = check.after_views.length > 0;
  const canReturn = isBorrower && status === 'lender_confirmed';
  const early = due && due.getTime() > Date.now();

  return (
    <div className="damage-page app-page">
      <div className="wrap">
        <section className="damage-card card">
          <div className="damage-head">
            <Badge variant="outline">{isBorrower ? 'Borrower' : 'Lender'}</Badge>
            <h1 className="t-h1">Condition check{lend ? `: ${lend.title}` : ''}</h1>
          </div>
          <p className="t-body damage-sub">
            Photos taken by the lender before handover. They are only visible to the two people in this lend.
          </p>

          <h2 className="t-h2">Before handover</h2>
          <ul className="damage-grid">
            {VIEWS.filter((v) => check.before_views.includes(v)).map((view) => (
              <li key={view}>
                <AuthImage path={pathFor('before', view)} alt={`${LABELS[view]}, before`} className="dmg-thumb" />
                <span>{LABELS[view]}</span>
              </li>
            ))}
          </ul>

          {canReturn && (
            <div className="damage-return">
              <h2 className="t-h2">Return this item</h2>
              <p className="t-body">
                {early
                  ? `Due ${formatDate(link.return_due_at)}. Returning early? You can submit your return today.`
                  : 'Your return is due. Upload your 6 return photos to finish.'}
              </p>
              {!capturing && !photosReady && check.missing_after.length === VIEWS.length && (
                <Button variant="primary" onClick={() => setCapturing(true)}>
                  {early ? 'Return today' : 'Start return photos'}
                </Button>
              )}
              {(capturing || check.missing_after.length < VIEWS.length) && (
                <SixPhotoCapture checkId={check.id} phase="after" onComplete={() => setPhotosReady(true)} />
              )}
              {(photosReady || check.missing_after.length === 0) && (
                <Button variant="primary" disabled={submitting} onClick={submitReturn}>
                  {submitting ? 'Submitting…' : 'Submit return'}
                </Button>
              )}
              {actionError && <div className="error-banner" role="alert">{actionError}</div>}
              <SupportChatButton step="return_flow" entityType="borrow_request" entityId={link.borrow_request_id} />
            </div>
          )}

          {isBorrower && status === 'photos_uploaded' && (
            <p className="t-body damage-wait">
              Keep this page. After you confirm receipt, come back here on the return day to upload your return photos.
            </p>
          )}

          {isBorrower && status === 'borrower_confirmed' && (
            <p className="t-body damage-wait">Waiting for the lender to confirm the handover. The return step opens after that.</p>
          )}

          {status === 'return_photos_uploaded' && (
            <div className="damage-review">
              <h2 className="t-h2">Return submitted</h2>
              <p className="t-body">
                {isBorrower
                  ? 'The lender is reviewing your return. If they do not respond within 72 hours it is approved automatically.'
                  : 'Review the comparison below, then approve or raise a dispute from the lend page.'}
              </p>
              {!isBorrower && (
                <Button asChild variant="primary">
                  <Link to={`/borrow-requests/${link.borrow_request_id}`}>Review on the lend page</Link>
                </Button>
              )}
            </div>
          )}

          {status === 'disputed' && (
            <p className="t-body damage-wait">
              A dispute is open. NeighborLend admins are reviewing both photo sets and will notify you.
            </p>
          )}

          {hasAfter && check.missing_after.length === 0 && ['return_photos_uploaded', 'disputed'].includes(status) && (
            <>
              <h2 className="t-h2">Before and after</h2>
              <BeforeAfterCompare pathFor={pathFor} report={check.report} />
              <h2 className="t-h2">AI-assisted log</h2>
              <DamageReportView report={check.report} status={check.status} />
            </>
          )}
        </section>
      </div>
    </div>
  );
}
