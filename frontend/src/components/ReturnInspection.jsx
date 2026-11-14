import React, { useState } from 'react';
import Button from './ui/Button.jsx';
import RentalEvidenceImage from './RentalEvidenceImage.jsx';

export default function ReturnInspection({ request, user, api, onChange }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (request.handover_status !== 'return_photos_uploaded' || user?.id !== request.lender_id) return null;
  async function decide(approved) {
    if (busy) return;
    setBusy(true); setError('');
    try { await api.post(`/borrow-requests/${request.id}/return/confirm`, { approved }); await onChange?.(); }
    catch (err) { setError(err.response?.data?.detail || 'Return decision could not be confirmed.'); }
    finally { setBusy(false); }
  }
  return <section className="handover-step return-section" aria-label="Lender return inspection">
    <h3 className="t-card">Review returned item</h3>
    <p>Review the borrower’s private return evidence before approving the return.</p>
    <div className="photo-previews lender-photos">{(request.return_photos || []).map((reference, i) => <RentalEvidenceImage key={reference} reference={reference} api={api} alt={`Return evidence ${i + 1}`} className="photo-preview" />)}</div>
    {error && <p role="alert" className="error-banner">{error}</p>}
    <Button disabled={busy} onClick={() => decide(true)}>{busy ? 'Saving…' : 'Approve return'}</Button>
    <Button variant="secondary" disabled={busy} onClick={() => decide(false)}>Reject and start dispute review</Button>
  </section>;
}
