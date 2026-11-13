import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MapPin } from 'lucide-react';
import api from '../api/client';
import { detectUserLocation } from '../utils/location';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Card from '../components/ui/Card';
import './CreateBorrowRequest.css';

const CATEGORIES = [
  'Bicycle',
  'Book',
  'Drill',
  'Hammer',
  'Headphones',
  'Ladder',
  'Camera',
  'Tent & Camping Gear',
  'Musical Instrument',
  'Sports Equipment',
  'Furniture',
  'Electronics (Other)',
  'Party & Event Supplies',
  'Other',
];

export default function CreateBorrowRequest() {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    title: '',
    category: 'Drill',
    description: '',
    max_price_per_day: '',
    radius_km: 10,
    latitude: 28.6139,
    longitude: 77.2090,
    address_text: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const [isLocating, setIsLocating] = useState(false);

  const handleUseLocation = async () => {
    setIsLocating(true);
    setError('');
    try {
      const loc = await detectUserLocation();
      setFormData((prev) => ({
        ...prev,
        latitude: loc.latitude,
        longitude: loc.longitude,
        address_text: loc.address || `Lat: ${loc.latitude.toFixed(4)}, Lon: ${loc.longitude.toFixed(4)}`,
      }));
    } catch {
      setError('Could not access device location. Please enter coordinates manually.');
    } finally {
      setIsLocating(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      await api.post('/borrow-requests/', {
        ...formData,
        max_price_per_day: formData.max_price_per_day ? parseFloat(formData.max_price_per_day) : null,
        radius_km: parseFloat(formData.radius_km),
        latitude: parseFloat(formData.latitude),
        longitude: parseFloat(formData.longitude),
      });
      navigate('/browse');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create borrow request');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="create-request-page app-page">
      <div className="wrap">
        <div className="request-header">
          <h2 className="t-h2">Post an item request</h2>
          <p className="t-lead measure">
            Can&rsquo;t find what you need? Post a request and nearby lenders will reach out to you.
          </p>
        </div>

        <Card variant="default" className="request-card">
          <div className="form-body">
            {error && (
              <div className="error-banner" role="alert">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="request-form">
              <Input
                id="title"
                name="title"
                label="Request title"
                type="text"
                placeholder="e.g. Need a pressure washer for 2 days"
                value={formData.title}
                onChange={handleChange}
                required
              />

              <Input
                id="category"
                name="category"
                label="Category"
                type="select"
                value={formData.category}
                onChange={handleChange}
              >
                {CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </Input>

              <Input
                id="description"
                name="description"
                label="Description &amp; purpose"
                type="textarea"
                rows="4"
                placeholder="Describe what you plan to use it for and any specific requirements."
                value={formData.description}
                onChange={handleChange}
              />

              <Input
                id="max_price_per_day"
                name="max_price_per_day"
                label="Maximum daily budget (₹/day)"
                type="number"
                placeholder="e.g. 200"
                value={formData.max_price_per_day}
                onChange={handleChange}
              />

              <div className="form-group">
                <label className="t-label">Search radius ({formData.radius_km} km)</label>
                <Input
                  id="radius_km"
                  name="radius_km"
                  type="range"
                  min="1"
                  max="50"
                  value={formData.radius_km}
                  onChange={handleChange}
                  className="range-input"
                />
                <div className="radius-markers">
                  <span className="t-small muted">1 km</span>
                  <span className="t-small muted">25 km</span>
                  <span className="t-small muted">50 km</span>
                </div>
              </div>

              <div className="location-section">
                <Button
                  variant="secondary"
                  type="button"
                  onClick={handleUseLocation}
                  disabled={isLocating}
                  className="use-location-btn"
                >
                  <MapPin size={16} />
                  <span>{isLocating ? 'Locating…' : 'Use current location'}</span>
                </Button>
                <span className="location-text t-small muted">
                  {formData.latitude.toFixed(4)}, {formData.longitude.toFixed(4)}
                </span>
              </div>

              <Button variant="primary" type="submit" disabled={loading} className="publish-btn">
                {loading ? 'Publishing request…' : 'Publish item request'}
              </Button>
            </form>
          </div>
        </Card>
      </div>
    </div>
  );
}
