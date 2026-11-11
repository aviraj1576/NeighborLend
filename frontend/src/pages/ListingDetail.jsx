import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { MapPin, Star, Shield, AlertCircle, Clock, Check, MessageSquare } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import { resolvePhotoUrl } from '../utils/photoUrl';
import './ListingDetail.css';

const ListingDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [listing, setListing] = useState(null);
  const [photoIndex, setPhotoIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [startingChat, setStartingChat] = useState(false);

  useEffect(() => {
    const fetchListing = async () => {
      try {
        const res = await api.get(`/listings/${id}`);
        setListing(res.data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchListing();
  }, [id]);

  if (loading) return <div className="loading-state">Loading...</div>;
  if (!listing) return <div className="loading-state">Listing not found</div>;

  const isOwner = user && listing.owner && user.username === listing.owner.username;
  const photos = listing.photos?.length ? listing.photos : (listing.image_url ? [listing.image_url] : []);
  const imageUrl = resolvePhotoUrl(photos[photoIndex] || photos[0]);

  const handleChatWithOwner = async () => {
    if (!user) {
      navigate('/login');
      return;
    }
    if (isOwner) {
      alert("You cannot start a conversation on your own listing.");
      return;
    }
    setStartingChat(true);
    try {
      const res = await api.post('/conversations', { lender_id: listing.owner_id });
      navigate(`/messages/${res.data.id}`);
    } catch (err) {
      console.error('Failed to open chat:', err);
      alert(err.response?.data?.detail || 'Failed to start conversation.');
    } finally {
      setStartingChat(false);
    }
  };

  return (
    <div className="listing-detail-page fade-in-up">
      <div className="detail-hero">
        {imageUrl ? (
          <img src={imageUrl} alt={listing.title} className="detail-hero-image" />
        ) : (
          <div className="detail-hero-placeholder"></div>
        )}

        {photos.length > 1 && (
          <div className="detail-photo-thumbnails" aria-label="Listing photos">
            {photos.map((photo, index) => (
              <button
                key={photo}
                type="button"
                className={`detail-photo-thumbnail ${photoIndex === index ? 'active' : ''}`}
                onClick={() => setPhotoIndex(index)}
                aria-label={`Show photo ${index + 1}`}
                aria-pressed={photoIndex === index}
              >
                <img src={resolvePhotoUrl(photo)} alt="" />
              </button>
            ))}
          </div>
        )}
        
        <div className="container detail-hero-content">
          <div className="detail-info-card glass">
            <span className="category-badge">{listing.category}</span>
            <h1 className="detail-title">{listing.title}</h1>
            <div className="detail-price-row">
              <span className="price-large gradient-text">₹{listing.price_per_day}</span>
              <span className="price-unit">/ day</span>
            </div>
            <div className="deposit-info">
              <Shield size={16} className="text-warning" />
              <span>Refundable Deposit: ₹{listing.security_deposit} · Test booking only; total is confirmed server-side before payment.</span>
            </div>
          </div>
        </div>
      </div>

      <div className="container detail-body">
        <div className="detail-main">
          
          <section className="detail-section glass">
            <h3>Description</h3>
            <p className="description-text">{listing.description}</p>
          </section>

          {listing.ai_label && (
            <section className="detail-section glass ai-verification">
              <div className="ai-verification-header">
                <Check size={20} className="text-success" />
                <h3>AI Verified</h3>
              </div>
              <p>Our AI identified this item as <strong>{listing.ai_label}</strong> with {Math.round(listing.ai_confidence * 100)}% confidence.</p>
            </section>
          )}

          <section className="detail-section glass">
            <h3>Location</h3>
            <div className="location-info">
              <MapPin className="text-accent" />
              <span>{listing.address}</span>
            </div>
            {/* Map placeholder */}
            <div className="map-placeholder">
              Map View (Lat: {listing.lat}, Lon: {listing.lon})
            </div>
          </section>

        </div>

        <div className="detail-sidebar">
          
          <div className="action-card glass">
            {isOwner ? (
              <div className="owner-actions">
                <button className="btn-primary full-width mb-3">Edit Listing</button>
                <button className="btn-outline text-danger full-width">Delete Listing</button>
              </div>
            ) : (
              <div className="borrower-actions">
                <button 
                  className="btn-primary full-width mb-3"
                  onClick={handleChatWithOwner}
                  disabled={startingChat}
                >
                  <MessageSquare size={18} style={{ marginRight: '8px', verticalAlign: 'middle', display: 'inline' }} />
                  {startingChat ? 'Connecting...' : 'Chat with Owner'}
                </button>
                <button 
                  className="btn-outline full-width"
                  onClick={handleChatWithOwner}
                  disabled={startingChat}
                >
                  Negotiate Price
                </button>
              </div>
            )}
          </div>

          <div className="owner-card glass">
            <div className="owner-header">
              <div className="owner-avatar-large">
                {(listing.owner?.username || listing.owner_username || 'U')[0].toUpperCase()}
              </div>
              <div>
                <h4>{listing.owner?.username || listing.owner_username}</h4>
                <div className="member-since">Member since {listing.owner?.member_since || '2023'}</div>
              </div>
            </div>
            
            <div className="owner-stats">
              <div className="stat">
                <Star className="text-warning" size={18} fill="currentColor" />
                <span>{listing.owner?.rating || listing.owner_avg_rating || 5.0} Rating</span>
              </div>
              <div className="stat">
                <Shield className="text-success" size={18} />
                <span>{listing.owner?.trust_score || listing.owner_trust_score || 100} Trust Score</span>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
};

export default ListingDetail;
