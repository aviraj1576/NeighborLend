import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Edit2, Play, Pause, Trash2, X, Save, ImagePlus } from 'lucide-react';
import api from '../api/client';
import ListingCard from '../components/ListingCard';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import './MyListings.css';

const CATEGORIES = ['Tools', 'Electronics', 'Sports', 'Party', 'Books', 'Other'];
const editable = (status) => status === 'draft' || status === 'pending_review';

const MyListings = () => {
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [photoFiles, setPhotoFiles] = useState([]);
  const photoFilesRef = useRef(photoFiles);
  photoFilesRef.current = photoFiles;
  const [notice, setNotice] = useState(null);
  const [saving, setSaving] = useState(false);

  const fetchMyListings = async () => {
    try {
      const res = await api.get('/listings');
      setListings(res.data);
    } catch (err) {
      setNotice({ type: 'error', text: err.response?.data?.detail || 'Could not load your listings.' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchMyListings(); }, []);

  useEffect(() => () => photoFilesRef.current.forEach(({ preview }) => URL.revokeObjectURL(preview)), []);

  const startEdit = (listing) => {
    if (!editable(listing.status)) return;
    setNotice(null);
    setEditingId(listing.id);
    setPhotoFiles([]);
    setEditForm({
      name: listing.name || listing.title || '',
      category: listing.category || 'Other',
      description: listing.description || '',
      price_per_day: listing.price_per_day ?? '',
      security_deposit: listing.security_deposit ?? 0,
      address_text: listing.address_text || '',
      latitude: listing.latitude ?? '',
      longitude: listing.longitude ?? '',
      photo_urls: [...(listing.photos || [])],
    });
  };

  const cancelEdit = () => { photoFiles.forEach(({ preview }) => URL.revokeObjectURL(preview)); setEditingId(null); setEditForm({}); setPhotoFiles([]); };

  const saveEdit = async (id) => {
    setSaving(true);
    setNotice(null);
    try {
      const uploaded = [];
      for (const file of photoFiles) {
        const form = new FormData();
        form.append('file', file.file);
        const { data } = await api.post('/upload', form);
        if (!data?.url) throw new Error('Photo upload did not return a URL.');
        uploaded.push(data.url);
      }
      const payload = {
        ...editForm,
        price_per_day: Number(editForm.price_per_day),
        security_deposit: Number(editForm.security_deposit || 0),
        latitude: editForm.latitude === '' ? null : Number(editForm.latitude),
        longitude: editForm.longitude === '' ? null : Number(editForm.longitude),
        photo_urls: [...editForm.photo_urls, ...uploaded],
      };
      const { data } = await api.patch(`/listings/${id}`, payload);
      setListings((items) => items.map((item) => item.id === id ? data : item));
      cancelEdit();
      setNotice({ type: 'success', text: 'Listing changes saved.' });
    } catch (err) {
      setNotice({ type: 'error', text: err.response?.data?.detail || err.message || 'Could not save listing changes.' });
    } finally {
      setSaving(false);
    }
  };

  const publishDraft = async (listing) => {
    setNotice(null);
    try {
      const { data } = await api.patch(`/listings/${listing.id}`, { status: 'published' });
      setListings((items) => items.map((item) => item.id === listing.id ? data : item));
      setNotice({ type: 'success', text: 'Listing published. Editing is now permanently disabled.' });
    } catch (err) {
      setNotice({ type: 'error', text: err.response?.data?.detail || 'Could not publish listing.' });
    }
  };

  const toggleStatus = async (listing) => {
    const status = listing.status === 'published' ? 'paused' : 'published';
    try {
      const { data } = await api.patch(`/listings/${listing.id}`, { status });
      setListings((items) => items.map((item) => item.id === listing.id ? data : item));
    } catch (err) {
      setNotice({ type: 'error', text: err.response?.data?.detail || 'Could not change listing status.' });
    }
  };

  const deleteListing = async (id) => {
    if (!window.confirm('Are you sure you want to delete this listing? This action cannot be undone.')) return;
    try {
      await api.delete(`/listings/${id}`);
      setListings((items) => items.filter((item) => item.id !== id));
    } catch (err) {
      setNotice({ type: 'error', text: err.response?.data?.detail || 'Failed to delete listing. Please try again.' });
    }
  };

  const changeField = (event) => setEditForm((form) => ({ ...form, [event.target.name]: event.target.value }));

  return (
    <div className="my-listings-page app-page">
      <div className="wrap">
        <div className="page-header section-head--split">
          <div><h1 className="t-h2">My listings</h1><p className="t-lead measure">Manage the items you share with neighbors.</p></div>
          <Button variant="primary" className="add-listing-btn" asChild><Link to="/create-listing"><Plus size={18} /><span style={{ marginLeft: 'var(--s-2)' }}>List something</span></Link></Button>
        </div>

        {notice && <p className={`listing-notice listing-notice--${notice.type}`} role={notice.type === 'error' ? 'alert' : 'status'}>{notice.text}</p>}
        {loading ? <div className="dashboard-loading">Loading your listings…</div> : listings.length ? (
          <div className="dashboard-grid">
            {listings.map((listing) => (
              <div key={listing.id} className="dashboard-wrap">
                {editingId === listing.id ? (
                  <Card variant="default" className="edit-card">
                    <div className="edit-head"><h3 className="t-card">Edit listing</h3><Button variant="secondary" size="sm" onClick={cancelEdit} disabled={saving}><X size={16} /><span>Cancel</span></Button></div>
                    <div className="edit-form">
                      <label className="edit-field">Title<input name="name" maxLength="120" required value={editForm.name} onChange={changeField} /></label>
                      <label className="edit-field">Category<select name="category" value={editForm.category} onChange={changeField}>{CATEGORIES.map((category) => <option key={category}>{category}</option>)}</select></label>
                      <label className="edit-field">Description<textarea name="description" rows="4" value={editForm.description} onChange={changeField} /></label>
                      <div className="form-row">
                        <label className="edit-field">Price per day (₹)<input name="price_per_day" type="number" min="0" step="any" required value={editForm.price_per_day} onChange={changeField} /></label>
                        <label className="edit-field">Security deposit (₹)<input name="security_deposit" type="number" min="0" step="any" value={editForm.security_deposit} onChange={changeField} /></label>
                      </div>
                      <label className="edit-field">Pickup address<input name="address_text" value={editForm.address_text} onChange={changeField} /></label>
                      <div className="form-row">
                        <label className="edit-field">Latitude<input name="latitude" type="number" min="-90" max="90" step="any" value={editForm.latitude} onChange={changeField} /></label>
                        <label className="edit-field">Longitude<input name="longitude" type="number" min="-180" max="180" step="any" value={editForm.longitude} onChange={changeField} /></label>
                      </div>
                      <div className="edit-field"><span>Listing photos</span><div className="edit-photo-grid">
                        {editForm.photo_urls.map((url, index) => <div className="edit-photo" key={`${url}-${index}`}><img src={url} alt={`Listing photo ${index + 1}`} /><button type="button" aria-label={`Remove photo ${index + 1}`} onClick={() => setEditForm((form) => ({ ...form, photo_urls: form.photo_urls.filter((_, photoIndex) => photoIndex !== index) }))}><X size={15} /></button></div>)}
                        {photoFiles.map((file, index) => <div className="edit-photo" key={`${file.file.name}-${index}`}><img src={file.preview} alt={`New photo ${index + 1}`} /><button type="button" aria-label={`Remove new photo ${index + 1}`} onClick={() => { URL.revokeObjectURL(file.preview); setPhotoFiles((files) => files.filter((_, fileIndex) => fileIndex !== index)); }}><X size={15} /></button></div>)}
                      </div><label className="edit-add-photo"><ImagePlus size={17} /> Add photos<input type="file" accept="image/*" multiple onChange={(event) => { const additions = Array.from(event.target.files || []).filter((file) => file.type.startsWith('image/')).map((file) => ({ file, preview: URL.createObjectURL(file) })); setPhotoFiles((files) => [...files, ...additions]); event.target.value = ''; }} /></label></div>
                    </div>
                    <div className="edit-actions"><Button variant="secondary" onClick={cancelEdit} disabled={saving}>Cancel</Button><Button variant="primary" onClick={() => saveEdit(listing.id)} disabled={saving || !editForm.name.trim() || !editForm.category || !editForm.price_per_day}><Save size={16} /><span>{saving ? 'Saving…' : 'Save changes'}</span></Button></div>
                  </Card>
                ) : (
                  <div className="dashboard-item">
                    <ListingCard listing={listing} interactive={!editable(listing.status)} />
                    <div className="dashboard-item-actions">
                      {editable(listing.status) && <Button variant="secondary" size="sm" onClick={() => startEdit(listing)} title="Edit unpublished listing"><Edit2 size={15} /><span>Edit Listing</span></Button>}
                      {editable(listing.status) ? <Button variant="primary" size="sm" onClick={() => publishDraft(listing)}><Play size={15} /><span>Publish</span></Button> : <Button variant="secondary" size="sm" onClick={() => toggleStatus(listing)} title={listing.status === 'published' ? 'Pause listing' : 'Publish listing'}>{listing.status === 'published' ? <Pause size={15} /> : <Play size={15} />}<span>{listing.status === 'published' ? 'Pause' : 'Publish'}</span></Button>}
                      <Button variant="secondary" size="sm" className="delete-action-btn" onClick={() => deleteListing(listing.id)} title="Delete listing"><Trash2 size={15} /><span>Delete</span></Button>
                    </div>
                    {!editable(listing.status) && <p className="listing-edit-lock">Published listings can no longer be edited.</p>}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : <Card variant="default" className="empty-card"><div className="empty-body"><Plus size={44} className="empty-icon" /><h3 className="t-card">You haven’t listed anything yet</h3><p className="t-body">Turn your unused items into extra cash today.</p><div className="empty-actions" style={{ marginTop: 'var(--s-5)' }}><Button variant="primary" asChild><Link to="/create-listing">List an item</Link></Button></div></div></Card>}
      </div>
    </div>
  );
};

export default MyListings;
