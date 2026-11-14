export async function uploadEvidenceFiles(api, bookingId, files, stage) {
  if (!bookingId) throw new Error('Verified rental booking is not available. Refresh and try again.');
  const references = [];
  for (const file of files) {
    const form = new FormData();
    form.append('file', file);
    const { data } = await api.post(`/payments/bookings/${bookingId}/evidence?stage=${stage}`, form);
    if (!data?.url) throw new Error('The evidence upload response did not include a private evidence reference.');
    references.push(data.url);
  }
  return references;
}
