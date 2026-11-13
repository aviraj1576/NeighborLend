import React from 'react';
import { useNavigate } from 'react-router-dom';
import { MapPin, Star, Package } from 'lucide-react';
import { resolvePhotoUrl } from '../utils/photoUrl';
import Card from './ui/Card';
import Badge from './ui/Badge';
import './ListingCard.css';

const ListingCard = ({ listing }) => {
  const navigate = useNavigate();

  const handleClick = () => {
    navigate(`/listing/${listing.id}`);
  };

  const titleText = listing.title || listing.name || 'Untitled Item';
  const ownerName = listing.owner?.username || listing.owner?.name || listing.owner_username || listing.owner_name || 'Owner';
  const ownerInitial = ownerName[0]?.toUpperCase() || 'U';
  const rawRating = listing.owner?.rating ?? listing.owner?.avg_rating ?? listing.owner_avg_rating;
  const ownerRating = typeof rawRating === 'number' ? (rawRating > 0 ? rawRating.toFixed(1) : '5.0') : '5.0';

  let locationText = listing.address || listing.address_text;
  if (!locationText && listing.latitude != null && listing.longitude != null) {
    locationText = `${listing.latitude.toFixed(4)}°, ${listing.longitude.toFixed(4)}°`;
  }
  if (!locationText) {
    locationText = 'Location unavailable';
  }

  const imageUrl = resolvePhotoUrl(listing.image_url || listing.photos?.[0]);
  const pricePerDay = typeof listing.price_per_day === 'number' ? listing.price_per_day.toFixed(0) : (listing.price_per_day ?? '—');

  return (
    <Card
      variant="default"
      className="listing-card"
      onClick={handleClick}
    >
      <div className="listing-photo-wrap">
        {imageUrl ? (
          <img src={imageUrl} alt={titleText} className="listing-photo" loading="lazy" />
        ) : (
          <div className="listing-photo-placeholder" role="img" aria-label="No photo yet">
            <Package size={32} aria-hidden="true" />
          </div>
        )}
        <div className="listing-overlay">
          <Badge variant="outline" className="listing-category-badge">
            {listing.category || 'Item'}
          </Badge>
          <span className="listing-price-badge">₹{pricePerDay}/day</span>
        </div>
      </div>

      <div className="listing-content">
        <h3 className="listing-title">{titleText}</h3>

        <div className="listing-location">
          <MapPin size={13} className="location-icon" />
          <span>{locationText}</span>
          {listing.distance_km != null && (
            <span className="distance-badge">• {listing.distance_km.toFixed(1)} km</span>
          )}
        </div>

        <div className="listing-owner">
          <div className="owner-avatar">
            <span className="owner-initial">{ownerInitial}</span>
          </div>
          <span className="owner-name">{ownerName}</span>
          <div className="owner-rating">
            <Star size={12} className="star-icon" />
            <span>{ownerRating}</span>
          </div>
        </div>
      </div>
    </Card>
  );
};

export default ListingCard;
