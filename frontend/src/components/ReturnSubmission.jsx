import React, { useEffect, useState } from 'react';
import Button from './ui/Button.jsx';
import { uploadEvidenceFiles } from './rentalEvidenceUpload.js';
import { apiErrorMessage } from './paymentFlow.js';

export default function ReturnSubmission({ request, user, booking, api, onChange }) {
  const [files, setFiles] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => () => previews.forEach((url) => URL.revokeObjectURL(url)), [previews]);
  if (user?.id !== request.borrower_id || user?.id !== booking?.borrower_id || !booking?.id ||
    booking.borrow_request_id !== request.id || booking.payment_status !== 'captured' ||
    !['funded', 'active', 'disputed'].includes(booking.booking_status) || booking.refund ||
    request.handover_status !== 'lender_confirmed' || request.returned_at) return null;
  function selectFiles(event) {
    const selected = Array.from(event.target.files || []);
    if (selected.length > 10) { setError('Select up to 10 photos.'); return; }
    previews.forEach((url) => URL.revokeObjectURL(url));
    setFiles(selected); setPreviews(selected.map((file) => URL.createObjectURL(file))); setError('');
  }
  async function submit() {
    if (busy || !files.length) return;
    setBusy(true); setError('');
    try {
      const photo_urls = await uploadEvidenceFiles(api, booking.id, files, 'return');
      await api.post(`/borrow-requests/${request.id}/return/upload-photos`, { photo_urls });
      await onChange?.();
      setFiles([]); previews.forEach((url) => URL.revokeObjectURL(url)); setPreviews([]);
    } catch (err) { setError(apiErrorMessage(err, 'Return photos could not be submitted.')); }
    finally { setBusy(false); }
  }
  return <section className="handover-step return-section" aria-label="Submit return evidence">
    <h3 className="t-card">Submit item return</h3>
    <p>Add clear photos of the item as returned. The lender will review them.</p>
    <input aria-label="Return photos" type="file" accept="image/jpeg,image/png" multiple disabled={busy} onChange={selectFiles} />
    <div className="photo-previews">{previews.map((src, i) => <img key={src} src={src} alt={`Return preview ${i + 1}`} className="photo-preview" />)}</div>
    {error && <p role="alert" className="error-banner">{error}</p>}
    <Button disabled={busy || !files.length} onClick={submit}>{busy ? 'Uploading…' : `Submit ${files.length} return photo(s)`}</Button>
  </section>;
}
