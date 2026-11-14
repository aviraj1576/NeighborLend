import React, { useEffect, useState } from 'react';
import Button from './ui/Button.jsx';
import Input from './ui/Input.jsx';
import RentalEvidenceImage from './RentalEvidenceImage.jsx';
import { uploadEvidenceFiles } from './rentalEvidenceUpload.js';
import { apiErrorMessage } from './paymentFlow.js';

export default function HandoverConfirmation({ request, user, api, bookingId, unlocked = false, onChange }) {
  const [files, setFiles] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [issue, setIssue] = useState('');
  const [showIssue, setShowIssue] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const lender = user?.id === request.lender_id;
  const borrower = user?.id === request.borrower_id;
  useEffect(() => () => previews.forEach((url) => URL.revokeObjectURL(url)), [previews]);

  async function run(operation) {
    if (busy || !unlocked || !bookingId) return;
    setBusy(true); setError('');
    try { await operation(); await onChange?.(); }
    catch (err) { setError(apiErrorMessage(err, 'Could not update handover.')); }
    finally { setBusy(false); }
  }
  function selectFiles(event) {
    const selected = Array.from(event.target.files || []);
    if (selected.length > 10) { setError('Select up to 10 photos.'); return; }
    previews.forEach((url) => URL.revokeObjectURL(url));
    setFiles(selected); setPreviews(selected.map((file) => URL.createObjectURL(file)));
  }

  if ((!lender && !borrower) || !['pending', 'photos_uploaded', 'borrower_confirmed', 'issue_reported'].includes(request.handover_status)) return null;
  const canAct = unlocked && Boolean(bookingId);
  return <section className="rental-lifecycle handover-panel" aria-label="Product handover">
    <h2 className="t-h2">Product handover</h2>
    <p className={`handover-status status-${request.handover_status}`}>
      {request.handover_status === 'pending' ? 'Awaiting lender product photos' : request.handover_status === 'photos_uploaded' ? 'Photos uploaded — borrower to confirm receipt' : request.handover_status === 'borrower_confirmed' ? 'Borrower confirmed — lender to complete handover' : 'Handover issue reported'}
    </p>
    {error && <p className="error-banner" role="alert">{error}</p>}
    {!canAct && <p role="status">Handover stays locked until verified payment status is available.</p>}
    {request.handover_status === 'pending' && lender && canAct && <div className="handover-step">
      <h3 className="t-card">Lender: upload product photos</h3><p>Payment must be verified before the item can be handed over.</p>
      <input aria-label="Product handover photos" type="file" accept="image/jpeg,image/png" multiple disabled={busy} onChange={selectFiles} />
      <div className="photo-previews">{previews.map((src, i) => <img key={src} src={src} alt={`Preview ${i + 1}`} className="photo-preview" />)}</div>
      <Button disabled={busy || !files.length} onClick={() => run(async () => {
        const photo_urls = await uploadEvidenceFiles(api, bookingId, files, 'handover');
        await api.post(`/borrow-requests/${request.id}/handover/upload-photos`, { photo_urls });
        setFiles([]); previews.forEach((url) => URL.revokeObjectURL(url)); setPreviews([]);
      })}>{busy ? 'Uploading…' : `Upload ${files.length} photo(s)`}</Button>
    </div>}
    {request.handover_status === 'photos_uploaded' && borrower && canAct && <div className="handover-step">
      <h3 className="t-card">Borrower: review and confirm receipt</h3>
      <div className="photo-previews">{(request.handover_photos || []).map((reference) => <RentalEvidenceImage key={reference} reference={reference} api={api} alt="Lender handover evidence" className="photo-preview" />)}</div>
      <label>Optional receipt photos<input aria-label="Receipt photos" type="file" accept="image/jpeg,image/png" multiple disabled={busy} onChange={selectFiles} /></label>
      <div className="photo-previews">{previews.map((src, i) => <img key={src} src={src} alt={`Receipt preview ${i + 1}`} className="photo-preview" />)}</div>
      <Button disabled={busy} onClick={() => run(async () => {
        const photo_urls = files.length ? await uploadEvidenceFiles(api, bookingId, files, 'receipt') : [];
        await api.post(`/borrow-requests/${request.id}/handover/borrower-confirm`, { photo_urls });
        setFiles([]); previews.forEach((url) => URL.revokeObjectURL(url)); setPreviews([]);
      })}>{busy ? 'Confirming…' : 'I received this item'}</Button>
      {!showIssue ? <Button variant="secondary" disabled={busy} onClick={() => setShowIssue(true)}>Report an issue</Button> : <form onSubmit={(event) => { event.preventDefault(); run(() => api.post(`/borrow-requests/${request.id}/handover/report-issue`, { description: issue })); }}>
        <Input id="handover-issue" label="Describe the issue" type="textarea" rows="3" maxLength={2000} required value={issue} onChange={(event) => setIssue(event.target.value)} />
        <Button type="submit" disabled={busy || !issue.trim()}>Submit issue</Button>
      </form>}
    </div>}
    {request.handover_status === 'borrower_confirmed' && lender && canAct && <div className="handover-step">
      <h3 className="t-card">Confirm product handover</h3><p>The borrower has confirmed receipt. Confirm to activate the rental.</p>
      <Button disabled={busy} onClick={() => run(() => api.post(`/borrow-requests/${request.id}/handover/lender-confirm`))}>{busy ? 'Confirming…' : 'Confirm handover complete'}</Button>
    </div>}
    {request.handover_status === 'issue_reported' && <div className="handover-issue-details"><p>{request.handover_issue_description || 'The borrower reported an issue.'}</p>{request.conversation_id && <a className="link handover-chat-link" href={`/messages/${request.conversation_id}`}>Open conversation</a>}</div>}
  </section>;
}
