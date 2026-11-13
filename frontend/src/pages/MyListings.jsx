import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Edit2, Play, Pause, Trash2, X, Save } from 'lucide-react';
import api from '../api/client';
import ListingCard from '../components/ListingCard';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import Input from '../components/ui/Input';
import './MyListings.css';

const MyListings = () => {
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});

  useEffect(() => {
    const fetchMyListings = async () => {
      try {
        const res = await api.get('/listings');
        setListings(res.data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchMyListings();
  }, []);

  const toggleStatus = async (id, currentStatus) => {
    const newStatus = currentStatus === 'published' ? 'paused' : 'published';
    try {
      await api.patch(`/listings/${id}`, { status: newStatus });
      setListings((items) => items.map((l) => (l.id === id ? { ...l, status: newStatus } : l)));
    } catch (err) {
      console.error(err);
    }
  };

  const deleteListing = async (id) => {
    if (!window.confirm('Are you sure you want to delete this listing?')) return;
    try {
      await api.delete(`/listings/${id}`);
      setListings((items) => items.filter((l) => l.id !== id));
    } catch (err) {
      console.error(err);
    }
  };

  const startEdit = (listing) => {
    setEditingId(listing.id);
    setEditForm({
      name: listing.title || listing.name,
      description: listing.description,
      price_per_day: listing.price_per_day,
      security_deposit: listing.security_deposit,
      lending_radius_km: listing.lending_radius_km,
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm({});
  };

  const saveEdit = async (id) => {
    try {
      const payload = {
        ...editForm,
        price_per_day: editForm.price_per_day ? Number(editForm.price_per_day) : undefined,
        security_deposit: editForm.security_deposit ? Number(editForm.security_deposit) : undefined,
        lending_radius_km: editForm.lending_radius_km ? Number(editForm.lending_radius_km) : undefined,
      };
      await api.patch(`/listings/${id}`, payload);
      setListings((items) => items.map((l) => (l.id === id ? { ...l, ...payload } : l)));
      cancelEdit();
    } catch (err) {
      console.error(err);
    }
  };

  const handleEditChange = (e) => {
    const { name, value } = e.target;
    setEditForm((prev) => ({ ...prev, [name]: value }));
  };

  return (
    <div className="my-listings-page app-page">
      <div className="wrap">
        <div className="page-header section-head--split">
          <div>
            <h2 className="t-h2">My listings</h2>
            <p className="t-lead measure">Manage the items you share with neighbors.</p>
          </div>
          <Link to="/create-listing">
            <Button variant="primary" className="add-listing-btn">
              <Plus size={18} />
              <span style={{ marginLeft: 'var(--s-2)' }}>List something</span>
            </Button>
          </Link>
        </div>

        {loading ? (
          <div className="dashboard-loading">Loading your listings…</div>
        ) : listings.length > 0 ? (
          <div className="dashboard-grid">
            {listings.map((listing) => (
              <div key={listing.id} className="dashboard-wrap">
                {editingId === listing.id ? (
                  <Card variant="default" className="edit-card">
                    <div className="edit-head">
                      <h3 className="t-card">Edit listing</h3>
                      <Button variant="secondary" size="sm" onClick={cancelEdit} className="cancel-edit">
                        <X size={16} />
                        <span style={{ marginLeft: 'var(--s-2)' }}>Cancel</span>
                      </Button>
                    </div>
                    <div className="edit-form">
                      <div className="form-row">
                        <Input
                          id="edit-name"
                          name="name"
                          label="Item name"
                          type="text"
                          value={editForm.name}
                          onChange={handleEditChange}
                          required
                        />
                        <Input
                          id="edit-category"
                          name="category"
                          label="Category"
                          type="text"
                          placeholder="e.g. Tools"
                          value={editForm.category || listing.category}
                          onChange={(e) => setEditForm((prev) => ({ ...prev, category: e.target.value }))}
                        />
                      </div>
                      <Input
                        id="edit-description"
                        name="description"
                        label="Description"
                        type="textarea"
                        rows={3}
                        value={editForm.description}
                        onChange={handleEditChange}
                      />
                      <div className="form-row">
                        <Input
                          id="edit-price"
                          name="price_per_day"
                          label="Price per day (₹)"
                          type="number"
                          min="0"
                          step="any"
                          value={editForm.price_per_day}
                          onChange={handleEditChange}
                        />
                        <Input
                          id="edit-deposit"
                          name="security_deposit"
                          label="Security deposit (₹)"
                          type="number"
                          min="0"
                          step="any"
                          value={editForm.security_deposit}
                          onChange={handleEditChange}
                        />
                        <Input
                          id="edit-radius"
                          name="lending_radius_km"
                          label="Lending radius (km)"
                          type="number"
                          min="1"
                          max="50"
                          value={editForm.lending_radius_km}
                          onChange={handleEditChange}
                        />
                      </div>
                    </div>
                    <div className="edit-actions">
                      <Button variant="secondary" onClick={cancelEdit}>
                        Cancel
                      </Button>
                      <Button variant="primary" onClick={() => saveEdit(listing.id)}>
                        <Save size={16} />
                        <span style={{ marginLeft: 'var(--s-2)' }}>Save</span>
                      </Button>
                    </div>
                  </Card>
                ) : (
                  <ListingCard listing={listing} />
                )}
              </div>
            ))}
          </div>
        ) : (
          <Card variant="default" className="empty-card">
            <div className="empty-body">
              <Plus size={44} className="empty-icon" />
              <h3 className="t-card">You haven&rsquo;t listed anything yet</h3>
              <p className="t-body">Turn your unused items into extra cash today.</p>
              <div className="empty-actions" style={{ marginTop: 'var(--s-5)' }}>
                <Link to="/create-listing">
                  <Button variant="primary">List an item</Button>
                </Link>
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
};

export default MyListings;
