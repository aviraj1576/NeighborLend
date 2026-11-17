import React, { useState, useEffect } from 'react';
import { Search, MapPin, SlidersHorizontal, Loader2, Globe, Compass, ChevronDown, List } from 'lucide-react';
import ListingCard from '../components/ListingCard';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Badge from '../components/ui/Badge';
import api from '../api/client';
import { requestBrowserLocation, POPULAR_LOCATIONS } from '../utils/location';
import './Browse.css';

const CATEGORIES = ['All', 'Tools', 'Electronics', 'Sports', 'Party', 'Books', 'Other'];

const Browse = () => {
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isLocating, setIsLocating] = useState(false);

  // Filters (field names and handlers preserved)
  const [searchQuery, setSearchQuery] = useState('');
  const [category, setCategory] = useState('All');
  const [radius, setRadius] = useState(50);
  const [location, setLocation] = useState({ lat: 30.3362, lon: 76.3922 }); // Default Patiala, Punjab
  const [locationName, setLocationName] = useState('Patiala, Punjab (Hub)');
  const [showLocationMenu, setShowLocationMenu] = useState(false);

  const fetchListings = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (searchQuery) params.append('q', searchQuery);
      if (category !== 'All') params.append('category', category);
      params.append('lat', location.lat);
      params.append('lon', location.lon);
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

  const [locationNotice, setLocationNotice] = useState('');

  const getUserLocation = async () => {
    setIsLocating(true);
    setLocationNotice('');
    try {
      const loc = await requestBrowserLocation();
      if (loc.error) {
        // No location: say so, and stop filtering by distance instead of guessing a place.
        setLocationNotice(
          loc.error === 'denied'
            ? 'Location is unavailable because location access is blocked. Showing all listings without distance filtering.'
            : 'Location is unavailable right now. Showing all listings without distance filtering.',
        );
        setRadius(100);
        return;
      }
      setLocation({ lat: loc.latitude, lon: loc.longitude });
      setLocationName(loc.address || 'My location');
    } catch (err) {
      console.error('Failed to detect location:', err);
      setLocationNotice('Location is unavailable right now. Showing all listings without distance filtering.');
      setRadius(100);
    } finally {
      setIsLocating(false);
    }
  };

  // Ask for the user's location when Browse opens, so distances are measured from them.
  useEffect(() => {
    getUserLocation();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSelectPresetLocation = (preset) => {
    setLocation({ lat: preset.lat, lon: preset.lon });
    setLocationName(preset.name);
    setShowLocationMenu(false);
  };

  return (
    <div className="browse-page">
      {/* Masthead */}
      <header className="browse-masthead">
        <div className="wrap">
          <div className="masthead-copy">
            <h1 className="masthead-title">Borrow what you need, from neighbors nearby.</h1>
            <p className="masthead-lead">
              Listings within {radius >= 100 ? 'all distances' : `${radius} km`} of
              <strong>{locationName}</strong>. Rates set by owners, no platform fees.
            </p>
          </div>
          <div className="masthead-actions">
            <Button variant="primary" asChild>
              <a href="/create-listing">List something to lend</a>
            </Button>
          </div>
        </div>
      </header>

      {/* Search + filters */}
      <section className="browse-search">
        <div className="wrap">
          <form onSubmit={handleSearch} className="search-form">
            <div className="search-input-group">
              <Search className="search-icon" size={18} />
              <Input
                id="search"
                name="q"
                type="text"
                aria-label="Search items"
                placeholder="What do you need?"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <Button variant="primary" type="submit">Search</Button>
            </div>
          </form>

          <div className="filters-row">
            <div className="categories-scroll">
              {CATEGORIES.map((cat) => (
                <Button
                  key={cat}
                  variant="secondary"
                  size="sm"
                  className={`category-pill ${category === cat ? 'active' : ''}`}
                  onClick={() => setCategory(cat)}
                >
                  {cat}
                </Button>
              ))}
            </div>

            <div className="location-filters">
              <div className="location-box">
                <div className="location-info" onClick={() => setShowLocationMenu(!showLocationMenu)} title="Change search hub">
                  <MapPin size={15} className="location-icon" />
                  <span className="location-name">{locationName}</span>
                  <ChevronDown size={13} className="dropdown-arrow" />
                </div>

                <button
                  type="button"
                  onClick={getUserLocation}
                  disabled={isLocating}
                  className="use-location-btn"
                  title="Detect my location using GPS & Network"
                >
                  {isLocating ? <Loader2 size={14} className="animate-spin" /> : <Compass size={14} />}
                  <span>{isLocating ? 'Finding…' : 'Use GPS'}</span>
                </button>

                {showLocationMenu && (
                  <div className="location-dropdown">
                    <div className="dropdown-title">Choose search hub:</div>
                    <button
                      type="button"
                      className="dropdown-item gps-item"
                      onClick={() => { setShowLocationMenu(false); getUserLocation(); }}
                    >
                      <Compass size={14} /> Detect current location
                    </button>
                    <div className="dropdown-divider" />
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

              <div className="radius-control-card">
                <div className="radius-top-bar">
                  <div className="radius-label">
                    <SlidersHorizontal size={15} />
                    <span>Distance:</span>
                    <strong className="radius-value-highlight">
                      {radius >= 100 ? 'Any distance' : `Within ${radius} km`}
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
                  aria-label="Search radius"
                  aria-valuetext={radius >= 100 ? 'Any distance' : `${radius} kilometres`}
                />

                <div className="radius-preset-pills">
                  {[15, 30, 50, 100].map((r) => (
                    <Button
                      key={r}
                      variant="secondary"
                      size="sm"
                      className={`radius-pill ${radius === r ? 'active' : ''}`}
                      onClick={() => setRadius(r)}
                    >
                      {r === 100 ? 'Any' : `${r} km`}
                    </Button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Results */}
      <section className="browse-results">
        <div className="wrap">
          <div className="results-header">
            <div>
              <h2 className="results-title">
                Items near you{category !== 'All' && ` in ${category}`}
              </h2>
              <p className="search-summary-text">
                Showing items {radius >= 100 ? 'at all distances' : `within ${radius} km`} from{' '}
                <strong>{locationName}</strong>
              </p>
            </div>
            <span className="results-count">
              {listings.length} item{listings.length !== 1 ? 's' : ''} found
            </span>
          </div>

          {locationNotice && (
            <p className="location-notice" role="status">{locationNotice}</p>
          )}

          {loading ? (
            <div className="listings-grid" aria-busy="true" aria-label="Loading listings">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <div key={i} className="skeleton-card" />
              ))}
            </div>
          ) : listings.length > 0 ? (
            <div className="listings-grid">
              {listings.map((listing) => (
                <ListingCard key={listing.id} listing={listing} />
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-icon">
                <List size={44} />
              </div>
              <h3 className="empty-title">No items within {radius >= 100 ? 'this search' : `${radius} km`}</h3>
              <p className="empty-lead">
                {radius < 100
                  ? `No available items were found within ${radius} km of ${locationName}. Try increasing your distance range or exploring all locations.`
                  : 'No items match your category or search term. Try resetting your search filters.'}
              </p>
              <div className="empty-actions">
                {radius < 100 && (
                  <Button variant="primary" onClick={() => setRadius(100)} asChild>
                    <a>Expand to any distance</a>
                  </Button>
                )}
                {locationName !== 'Patiala, Punjab (Hub)' && (
                  <Button variant="secondary" onClick={() => {
                    setLocation({ lat: 30.3362, lon: 76.3922 });
                    setLocationName('Patiala, Punjab (Hub)');
                    setRadius(50);
                  }}>
                    View Patiala hub
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
};

export default Browse;
