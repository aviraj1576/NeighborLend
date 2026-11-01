import React, { useState, useEffect } from 'react';
import { Search, MapPin, SlidersHorizontal, Loader2, Globe, Compass, ChevronDown } from 'lucide-react';
import ListingCard from '../components/ListingCard';
import api from '../api/client';
import { detectUserLocation, POPULAR_LOCATIONS } from '../utils/location';
import './Browse.css';

const CATEGORIES = ['All', 'Tools', 'Electronics', 'Sports', 'Party', 'Books', 'Other'];

const Browse = () => {
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isLocating, setIsLocating] = useState(false);
  
  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [category, setCategory] = useState('All');
  // Default radius 50 km or 100 for Any distance
  const [radius, setRadius] = useState(50);
  const [location, setLocation] = useState({ lat: 28.6139, lon: 77.2090 }); // Default Delhi
  const [locationName, setLocationName] = useState('New Delhi (Default Hub)');
  const [showLocationMenu, setShowLocationMenu] = useState(false);

  const fetchListings = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (searchQuery) params.append('q', searchQuery);
      if (category !== 'All') params.append('category', category);
      params.append('lat', location.lat);
      params.append('lon', location.lon);
      // If radius < 100, filter by distance; if >= 100, include any distance
      if (radius < 100) {
        params.append('radius_km', radius);
      } else {
        params.append('radius_km', 9999);
      }

      const res = await api.get(`/listings/search?${params.toString()}`);
      setListings(res.data || []);
    } catch (err) {
      console.error('Failed to fetch listings:', err);
      setListings([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchListings();
  }, [category, radius, location]);

  const handleSearch = (e) => {
    e.preventDefault();
    fetchListings();
  };

  const getUserLocation = async () => {
    setIsLocating(true);
    try {
      const loc = await detectUserLocation();
      setLocation({ lat: loc.latitude, lon: loc.longitude });
      setLocationName(loc.address || loc.city || 'My Location');
      // If user is far from Delhi items, suggest Any Distance or set radius to 100 if listings are 0
    } catch (err) {
      console.error('Failed to detect location:', err);
    } finally {
      setIsLocating(false);
    }
  };

  const handleSelectPresetLocation = (preset) => {
    setLocation({ lat: preset.lat, lon: preset.lon });
    setLocationName(preset.name);
    setShowLocationMenu(false);
  };

  return (
    <div className="browse-page container fade-in-up">
      
      {/* Search Header */}
      <section className="search-section glass">
        <form onSubmit={handleSearch} className="search-form">
          <div className="search-input-group">
            <Search className="search-icon" size={20} />
            <input 
              type="text" 
              placeholder="What do you need?" 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="search-input"
            />
          </div>
          <button type="submit" className="btn-primary search-btn">Search</button>
        </form>

        <div className="filters-row">
          <div className="categories-scroll">
            {CATEGORIES.map(cat => (
              <button 
                key={cat}
                className={`category-pill ${category === cat ? 'active' : ''}`}
                onClick={() => setCategory(cat)}
              >
                {cat}
              </button>
            ))}
          </div>

          <div className="location-filters">
            {/* Location selector with GPS detect button */}
            <div className="location-box glass">
              <div className="location-info" onClick={() => setShowLocationMenu(!showLocationMenu)} title="Click to change location">
                <MapPin size={16} className="text-accent" />
                <span className="location-name truncate">{locationName}</span>
                <ChevronDown size={14} className="dropdown-arrow" />
              </div>

              <button 
                type="button"
                onClick={getUserLocation} 
                disabled={isLocating}
                className="use-location-btn"
                title="Detect my location using GPS & Network"
              >
                {isLocating ? <Loader2 size={14} className="animate-spin" /> : <Compass size={14} />}
                <span>{isLocating ? 'Finding...' : 'Use GPS'}</span>
              </button>

              {/* Location Preset Dropdown Menu */}
              {showLocationMenu && (
                <div className="location-dropdown glass fade-in">
                  <div className="dropdown-title">Choose Search Hub:</div>
                  <button 
                    type="button" 
                    className="dropdown-item gps-item"
                    onClick={() => { setShowLocationMenu(false); getUserLocation(); }}
                  >
                    <Compass size={14} /> Detect Current Location
                  </button>
                  <div className="dropdown-divider"></div>
                  {POPULAR_LOCATIONS.map((loc) => (
                    <button
                      key={loc.name}
                      type="button"
                      className={`dropdown-item ${locationName === loc.name ? 'active' : ''}`}
                      onClick={() => handleSelectPresetLocation(loc)}
                    >
                      {loc.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
            
            {/* Enhanced Distance Slider */}
            <div className="radius-control-card glass">
              <div className="radius-top-bar">
                <div className="radius-label">
                  <SlidersHorizontal size={15} />
                  <span>Distance:</span>
                  <strong className="radius-value-highlight">
                    {radius >= 100 ? 'Any distance (All)' : `Within ${radius} km`}
                  </strong>
                </div>
              </div>

              <input 
                type="range" 
                min="5" 
                max="100" 
                step="5"
                value={radius} 
                onChange={(e) => setRadius(Number(e.target.value))}
                className="radius-slider"
                title={`Filter items within ${radius >= 100 ? 'all distances' : `${radius} km`}`}
              />

              <div className="radius-preset-pills">
                {[15, 30, 50, 100].map((r) => (
                  <button
                    key={r}
                    type="button"
                    className={`radius-pill ${radius === r ? 'active' : ''}`}
                    onClick={() => setRadius(r)}
                  >
                    {r === 100 ? 'Any' : `${r}km`}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Results */}
      <section className="results-section">
        <div className="results-header">
          <div>
            <h2>Items near you {category !== 'All' && `in ${category}`}</h2>
            <p className="search-summary-text">
              Showing items {radius >= 100 ? 'at all distances' : `within ${radius} km`} from <strong>{locationName}</strong>
            </p>
          </div>
          <span className="results-count">{listings.length} item{listings.length !== 1 ? 's' : ''} found</span>
        </div>

        {loading ? (
          <div className="listings-grid">
            {[1, 2, 3, 4, 5, 6].map(i => (
              <div key={i} className="skeleton-card glass"></div>
            ))}
          </div>
        ) : listings.length > 0 ? (
          <div className="listings-grid">
            {listings.map(listing => (
              <ListingCard key={listing.id} listing={listing} />
            ))}
          </div>
        ) : (
          <div className="empty-state glass">
            <div className="empty-icon-wrapper">
              <Search size={48} />
            </div>
            <h3>No items within {radius >= 100 ? 'this search' : `${radius} km`}</h3>
            <p>
              {radius < 100 
                ? `No available items were found within ${radius} km of ${locationName}. Try increasing your distance range or exploring all locations.` 
                : 'No items match your category or search term. Try resetting your search filters.'}
            </p>
            <div className="empty-actions">
              {radius < 100 && (
                <button 
                  type="button"
                  className="btn-primary" 
                  onClick={() => setRadius(100)}
                >
                  <Globe size={16} /> Expand to Any Distance (All items)
                </button>
              )}
              {locationName !== 'New Delhi (Default Hub)' && (
                <button 
                  type="button"
                  className="btn-outline" 
                  onClick={() => {
                    setLocation({ lat: 28.6139, lon: 77.2090 });
                    setLocationName('New Delhi (Default Hub)');
                    setRadius(50);
                  }}
                >
                  View New Delhi Hub Items
                </button>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
};

export default Browse;

