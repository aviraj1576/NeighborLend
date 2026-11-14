import React, { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import api from '../api/client';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Badge from '../components/ui/Badge';
import AuthImage from '../components/damage/AuthImage';
import BeforeAfterCompare from '../components/damage/BeforeAfterCompare';
import DamageReportView from '../components/damage/DamageReportView';
import { LABELS, VIEWS, adminPhotoPath, apiError } from '../components/damage/damageApi';
import './Admin.css';

const OUTCOMES = [
  { value: 'lender', label: 'In favor of the lender' },
  { value: 'borrower', label: 'In favor of the borrower' },
  { value: 'partial', label: 'Partial (note required)' },
];

const fmt = (v) => (v ? new Date(v).toLocaleString() : '—');

export default function AdminDisputeDetail() {
  const { disputeId } = useParams();
  const [dispute, setDispute] = useState(null);
  const [error, setError] = useState('');
  const [outcome, setOutcome] = useState('lender');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setDispute((await api.get(`/admin/disputes/${disputeId}`)).data);
      setError('');
    } catch (err) {
      setError(apiError(err, 'Could not load this dispute.'));
    }
  }, [disputeId]);

  useEffect(() => { load(); }, [load]);

  const pathFor = useCallback((phase, view) => adminPhotoPath(disputeId, phase, view), [disputeId]);

  const resolve = async () => {
    if (outcome === 'partial' && !note.trim()) {
      setError('A note is required for a partial outcome.');
      return;
    }
    if (!window.confirm('Record this decision, notify both parties and close the lend? This cannot be undone.')) return;
    setSaving(true);
    setError('');
    try {
      await api.post(`/admin/disputes/${disputeId}/resolve`, { outcome, note: note.trim() || null });
      await load();
    } catch (err) {
      setError(apiError(err, 'Could not resolve this dispute.'));
    } finally {
      setSaving(false);
    }
  };

  if (!dispute) {
    return (
      <div className="admin-page app-page"><div className="wrap">
        <section className="admin-card card">
          <Link className="link" to="/admin/disputes">&larr; All disputes</Link>
          {error ? <div className="error-banner" role="alert">{error}</div> : <p className="t-body">Loading…</p>}
        </section>
      </div></div>
    );
  }

  const open = dispute.status === 'open';
  const hasPhotos = dispute.before_views.length > 0 && dispute.after_views.length > 0;

  return (
    <div className="admin-page app-page">
      <div className="wrap">
        <section className="admin-card card">
          <Link className="link" to="/admin/disputes">&larr; All disputes</Link>
          <div className="admin-head">
            <h1 className="t-h1">{dispute.title}</h1>
            <Badge variant={open ? 'accent' : 'success'}>{open ? 'Open' : 'Resolved'}</Badge>
          </div>

          <dl className="admin-meta">
            <div><dt>Lender</dt><dd>{dispute.lender?.name}</dd></div>
            <div><dt>Borrower</dt><dd>{dispute.borrower?.name}</dd></div>
            <div><dt>Raised by</dt><dd>{dispute.raised_by_name}</dd></div>
            <div><dt>Raised</dt><dd>{fmt(dispute.created_at)}</dd></div>
            <div><dt>Rental</dt><dd>{fmt(dispute.lend.needed_from)} to {fmt(dispute.lend.needed_until)}</dd></div>
            <div><dt>Return due</dt><dd>{fmt(dispute.lend.return_due_at)}</dd></div>
            <div><dt>Returned</dt><dd>{fmt(dispute.lend.returned_at)}</dd></div>
            <div><dt>Damage-check link</dt><dd className="admin-mono">{dispute.damage_link_token ? `/damage-check/${dispute.damage_link_token}` : '—'}</dd></div>
          </dl>

          <div className="admin-reason">
            <h2 className="t-h2">Lender&rsquo;s reason</h2>
            <p className="t-body">{dispute.reason}</p>
          </div>

          {error && <div className="error-banner" role="alert">{error}</div>}

          <h2 className="t-h2">Before and after, side by side</h2>
          {hasPhotos ? (
            <div className="dmg-pairs">
              {VIEWS.map((view) => (
                <div className="dmg-pair" key={view}>
                  <h4>{LABELS[view]}</h4>
                  <div className="dmg-pair-imgs">
                    <figure>
                      {dispute.before_views.includes(view)
                        ? <AuthImage path={pathFor('before', view)} alt={`${LABELS[view]}, before`} />
                        : <div className="dmg-img-missing">No photo</div>}
                      <figcaption>Before (lender)</figcaption>
                    </figure>
                    <figure>
                      {dispute.after_views.includes(view)
                        ? <AuthImage path={pathFor('after', view)} alt={`${LABELS[view]}, after`} />
                        : <div className="dmg-img-missing">No photo</div>}
                      <figcaption>After (borrower)</figcaption>
                    </figure>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="t-body">
              {dispute.before_views.length > 0
                ? 'The borrower never submitted return photos. Only the before photos exist.'
                : 'No photos were recorded for this lend.'}
            </p>
          )}

          {hasPhotos && (
            <>
              <h2 className="t-h2">Slider comparison</h2>
              <BeforeAfterCompare pathFor={pathFor} report={dispute.report} />
            </>
          )}

          <h2 className="t-h2">AI-assisted log</h2>
          {dispute.report
            ? <DamageReportView report={dispute.report} status={dispute.check_status} />
            : <p className="t-body">No AI report ({dispute.check_status || 'no check'}).</p>}
          {dispute.lender_decision && (
            <p className="t-small muted">
              Lender&rsquo;s own decision on the warning: {dispute.lender_decision.decision}
              {dispute.lender_decision.comment ? ` — ${dispute.lender_decision.comment}` : ''}
            </p>
          )}

          <h2 className="t-h2">Decision</h2>
          {open ? (
            <fieldset className="admin-decision" disabled={saving}>
              <legend className="sr-only">Choose an outcome</legend>
              {OUTCOMES.map((o) => (
                <label key={o.value} className="admin-radio">
                  <input
                    type="radio" name="outcome" value={o.value}
                    checked={outcome === o.value} onChange={() => setOutcome(o.value)}
                  />
                  {o.label}
                </label>
              ))}
              <Input
                id="resolution-note"
                label={outcome === 'partial' ? 'Note for both parties (required)' : 'Note for both parties (optional)'}
                type="textarea"
                rows="4"
                maxLength={2000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
              <Button variant="primary" onClick={resolve} disabled={saving}>
                {saving ? 'Saving…' : 'Resolve and notify both parties'}
              </Button>
            </fieldset>
          ) : (
            <div className="admin-resolved">
              <p className="t-body"><strong>Outcome:</strong> {dispute.outcome}</p>
              {dispute.resolution_note && <p className="t-body"><strong>Note:</strong> {dispute.resolution_note}</p>}
              <p className="t-small muted">Resolved by {dispute.resolved_by_name || 'an admin'} on {fmt(dispute.resolved_at)}.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
