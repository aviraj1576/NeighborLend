import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { MapPin, Star, Shield, AlertCircle, Clock, Check, MessageSquare, ChevronLeft } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import { resolvePhotoUrl } from '../utils/photoUrl';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
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

  if (loading) return <div className="detail-loading">Loading listing…</div>;
  if (!listing) return <div className="detail-loading">Listing not found.</div>;

  const isOwner = user && listing.owner && user.username === listing.owner.username;
  const photos = listing.photos?.length ? listing.photos : (listing.image_url ? [listing.image_url] : []);
  const imageUrl = resolvePhotoUrl(photos[photoIndex] || photos[0]);

  const handleChatWithOwner = async () => {
    if (!user) {
      navigate('/login');
      return;
    }
    if (isOwner) return;
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
    <div className="listing-detail-page">

      {/* ===== Hero: full-bleed photograph + info card overlay ===== */}
      <section className="detail-hero section" style={{ '--h': '1' }} id="content">
        <div className="wrap">
          <div className="hero-grid">
            <div className="hero-photo">
              {imageUrl ? (
                <img src={imageUrl} alt={listing.title} className="detail-image entered" />
              ) : (
                <div className="detail-placeholder entered">
                  <span className="photo-initial">
                    {(listing.title || 'I')[0]?.toUpperCase()}
                  </span>
                </div>
              )}
              {photos.length > 1 && (
                <div className="photo-thumbs">
                  {photos.map((photo, index) => (
                    <button
                      key={photo}
                      type="button"
                      className={`photo-thumb ${photoIndex === index ? 'active' : ''}`}
                      onClick={() => setPhotoIndex(index)}
                      aria-label={`Show photo ${index + 1}`}
                      aria-pressed={photoIndex === index}
                    >
                      <span className="thumb-initial">
                        {(photo || 'P')[0]?.toUpperCase()}
                      </span>
                    </button>
                  ))}
                </div>
              )}
              <button
                type="button"
                className="back-link"
                onClick={() => navigate(-1)}
                aria-label="Back to browse"
              >
                <ChevronLeft size={16} /> Back
              </button>
            </div>

            <div className="hero-info">
              <div className="info-card card card--open">
                <Badge variant="outline" className="category-badge">
                  {listing.category || 'Item'}
                </Badge>
                <h1 className="detail-title t-h1">{listing.title}</h1>
                <div className="price-row">
                  <span className="price-large t-stat">₹{listing.price_per_day}</span>
                  <span className="price-unit">/ day</span>
                </div>
                <div className="deposit-row">
                  <Shield size={14} className="deposit-icon" />
                  <span>Refundable deposit ₹{listing.security_deposit ?? 0}</span>
                </div>
                <div className="location-row">
                  <MapPin size={14} className="location-icon" />
                  <span>{listing.address || 'Nearby'}</span>
                </div>
                <div className="btn-row" style={{ marginTop: 'var(--s-6)' }}>
                  {!isOwner && (
                    <Button variant="primary" onClick={handleChatWithOwner} disabled={startingChat}>
                      {startingChat ? 'Connecting…' : 'Chat with owner'}
                    </Button>
                  )}
                  <Button variant="secondary" asChild style={{ marginLeft: 'var(--s-3)' }}>
                    <Link to="/browse">Back to browse</Link>
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===== Body: description, AI verification, location ===== */}
      <section className="detail-body section" style={{ '--h': '2' }}>
        <div className="wrap grid grid--top">
          <div className="detail-main span-8">
            <section className="detail-section">
              <h2 className="t-h2">Description</h2>
              <p className="description-text measure">{listing.description}</p>
            </section>

            {listing.ai_label && (
              <section className="detail-section ai-verified">
                <div className="ai-row">
                  <Check size={18} className="ai-icon" />
                  <div>
                    <h3 className="t-h3">AI verified</h3>
                    <p>
                      Our AI identified this item as{' '}
                      <strong>{listing.ai_label}</strong> with{' '}
                      {Math.round((listing.ai_confidence || 0) * 100)}% confidence.
                    </p>
                  </div>
                </div>
              </section>
            )}

            <section className="detail-section location-section">
              <h2 className="t-h2">Location</h2>
              <div className="location-info">
                <MapPin size={16} className="location-icon" />
                <span>{listing.address || 'Neighborhood location'}</span>
              </div>
              <div className="map-placeholder entered">
                Map view — {listing.lat}, {listing.lon}
              </div>
            </section>
          </div>

          <div className="detail-sidebar span-4">
            {/* Owner card */}
            <Card variant="default" className="owner-card">
              <div className="owner-head">
                <div className="owner-avatar">
                  {(listing.owner?.username || listing.owner_username || 'U')[0]?.toUpperCase()}
                </div>
                <div className="owner-meta">
                  <h3 className="t-card">{listing.owner?.username || listing.owner_username}</h3>
                  <p className="member-since">Member since {listing.owner?.member_since || '2023'}</p>
                </div>
              </div>
              <div className="owner-stats">
                <div className="stat">
                  <Star size={16} className="stat-icon" />
                  <span>{listing.owner?.rating || listing.owner_avg_rating || 5.0} rating</span>
                </div>
                <div className="stat">
                  <Shield size={16} className="stat-icon" />
                  <span>{listing.owner?.trust_score || listing.owner_trust_score || 100} trust</span>
                </div>
              </div>
            </Card>

            {/* Actions */}
            <Card variant="default" className="actions-card">
              {isOwner ? (
                <div className="owner-actions">
                  <Button variant="secondary" onClick={() => navigate(`/listing/${id}/edit`)}>
                    Edit listing
                  </Button>
                  <Button variant="secondary" className="delete-btn" onClick={() => {}}>
                    Delete listing
                  </Button>
                </div>
              ) : (
                <div className="borrower-actions">
                  <Button variant="primary" onClick={handleChatWithOwner} disabled={startingChat}>
                    {startingChat ? 'Connecting…' : 'Chat with owner'}
                  </Button>
                  <Button variant="secondary" onClick={handleChatWithOwner}>
                    Negotiate price
                  </Button>
                </div>
              )}
            </Card>
          </div>
        </div>
      </section>
    </div>
  );
};

export default ListingDetail;
