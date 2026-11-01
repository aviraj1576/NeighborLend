import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Edit2, Play, Pause, Trash2 } from 'lucide-react';
import api from '../api/client';
import './MyListings.css';

const MyListings = () => {
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);

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
      setListings(listings.map(l => l.id === id ? { ...l, status: newStatus } : l));
    } catch (err) {
      console.error(err);
    }
  };

  const deleteListing = async (id) => {
    if (!window.confirm('Are you sure you want to delete this listing?')) return;
    try {
      await api.delete(`/listings/${id}`);
      setListings(listings.filter(l => l.id !== id));
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="my-listings-page container fade-in-up">
      <div className="page-header">
        <h1>My Listings</h1>
        <Link to="/create-listing" className="btn-primary add-listing-btn">
          <Plus size={20} />
          Create New
        </Link>
      </div>

      {loading ? (
        <div className="loading-state">Loading your listings...</div>
      ) : listings.length > 0 ? (
        <div className="dashboard-grid">
          {listings.map(listing => (
            <div key={listing.id} className="dashboard-card glass">
              
              <div className="card-header">
                <div className={`status-badge ${listing.status}`}>
                  {listing.status}
                </div>
                <div className="actions">
                  <button className="icon-action-btn" title="Edit">
                    <Edit2 size={16} />
                  </button>
                  <button 
                    className="icon-action-btn" 
                    title={listing.status === 'published' ? 'Pause' : 'Resume'}
                    onClick={() => toggleStatus(listing.id, listing.status)}
                  >
                    {listing.status === 'published' ? <Pause size={16} /> : <Play size={16} />}
                  </button>
                  <button 
                    className="icon-action-btn delete" 
                    title="Delete"
                    onClick={() => deleteListing(listing.id)}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>

              <div className="card-body">
                <h3>{listing.title}</h3>
                <span className="card-category">{listing.category}</span>
                <div className="card-price">₹{listing.price_per_day} / day</div>
              </div>

              <div className="card-footer">
                <div className="stat">
                  <span className="stat-val">{listing.views}</span>
                  <span className="stat-label">Views</span>
                </div>
                <div className="stat">
                  <span className="stat-val">{listing.requests}</span>
                  <span className="stat-label">Requests</span>
                </div>
              </div>

            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state glass">
          <div className="empty-icon-wrapper">
            <Plus size={48} />
          </div>
          <h3>You haven't listed anything yet</h3>
          <p>Turn your unused items into extra cash today.</p>
          <Link to="/create-listing" className="btn-primary mt-4">List an Item</Link>
        </div>
      )}
    </div>
  );
};

export default MyListings;
