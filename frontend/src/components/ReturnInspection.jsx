import React, { useState } from 'react';
import Button from './ui/Button.jsx';
import RentalEvidenceImage from './RentalEvidenceImage.jsx';

export default function ReturnInspection({ request, user, api, onChange, usesDamageCheck }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [disputing, setDisputing] = useState(false);
  const [reason, setReason] = useState('');
  if (request.handover_status !== 'return_photos_uploaded' || user?.id !== request.lender_id) return null;

  async function run(operation) {
    if (busy) return;
    setBusy(true); setError('');
    try { await operation(); await onChange?.(); window.dispatchEvent(new Event('notifications:updated')); }
    catch (err) { setError(err.response?.data?.detail || 'Return decision could not be saved.'); }
    finally { setBusy(false); }
  }

  const approve = () => run(() => api.post(`/borrow-requests/${request.id}/return/confirm`, { approved: true }));
  const dispute = () => run(() => (usesDamageCheck
    ? api.post(`/borrow-requests/${request.id}/return/dispute`, { reason: reason.trim() })
    : api.post(`/borrow-requests/${request.id}/return/confirm`, { approved: false, condition_note: reason.trim() })));

  return <section className="handover-step return-section" aria-label="Lender return inspection">
    <h3 className="t-card">Review returned item</h3>
    <p>{usesDamageCheck
      ? 'Compare the before and after photos and the AI report above. Approve to release the security deposit to the borrower, or raise a dispute for an admin to decide.'
      : 'Review the borrower’s private return evidence before approving the return.'}</p>
    {!usesDamageCheck && <div className="photo-previews lender-photos">{(request.return_photos || []).map((reference, i) => <RentalEvidenceImage key={reference} reference={reference} api={api} alt={`Return evidence ${i + 1}`} className="photo-preview" />)}</div>}
    {error && <p role="alert" className="error-banner">{error}</p>}
    {!disputing ? <>
      <Button disabled={busy} onClick={approve}>{busy ? 'Saving…' : 'Approve return & release deposit'}</Button>
      <Button variant="secondary" disabled={busy} onClick={() => setDisputing(true)}>Raise a dispute</Button>
    </> : <form onSubmit={(event) => { event.preventDefault(); dispute(); }}>
      <label htmlFor="return-dispute-reason">What is wrong with the returned item?</label>
      <textarea id="return-dispute-reason" rows={3} maxLength={2000} required value={reason} onChange={(e) => setReason(e.target.value)} style={{ width: '100%' }} />
      <Button type="submit" disabled={busy || !reason.trim()}>{busy ? 'Sending…' : 'Send dispute to admin'}</Button>
      <Button type="button" variant="secondary" disabled={busy} onClick={() => setDisputing(false)}>Cancel</Button>
    </form>}
  </section>;
}
