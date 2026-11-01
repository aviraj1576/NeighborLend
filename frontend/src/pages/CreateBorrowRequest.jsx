import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api/client';
import { detectUserLocation } from '../utils/location';
import './CreateBorrowRequest.css';

const CATEGORIES = [
  "Bicycle", "Book", "Drill", "Hammer", "Headphones", "Ladder",
  "Camera", "Tent & Camping Gear", "Musical Instrument", "Sports Equipment",
  "Furniture", "Electronics (Other)", "Party & Event Supplies", "Other",
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
    address_text: ''
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
      setFormData(prev => ({
        ...prev,
        latitude: loc.latitude,
        longitude: loc.longitude,
        address_text: loc.address || `Lat: ${loc.latitude.toFixed(4)}, Lon: ${loc.longitude.toFixed(4)}`
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
    <div className="create-request-page container">
      <div className="request-card glass">
        <h2 className="title gradient-text">Post an Item Request</h2>
        <p className="subtitle">Can't find what you need? Post a request and nearby lenders will reach out to you!</p>

        {error && <div className="error-banner">{error}</div>}

        <form onSubmit={handleSubmit} className="request-form">
          <div className="form-group">
            <label>Request Title *</label>
            <input
              type="text"
              name="title"
              placeholder="e.g., Need a Pressure Washer for 2 days"
              value={formData.title}
              onChange={handleChange}
              required
            />
          </div>

          <div className="form-group">
            <label>Category *</label>
            <select name="category" value={formData.category} onChange={handleChange}>
              {CATEGORIES.map(cat => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Description & Purpose</label>
            <textarea
              name="description"
              rows="4"
              placeholder="Describe what you plan to use it for and any specific requirements..."
              value={formData.description}
              onChange={handleChange}
            />
          </div>

          <div className="form-group">
            <label>Maximum Daily Budget (₹/day)</label>
            <input
              type="number"
              name="max_price_per_day"
              placeholder="e.g. 200"
              value={formData.max_price_per_day}
              onChange={handleChange}
            />
          </div>

          <div className="form-group">
            <label>Search Radius ({formData.radius_km} km)</label>
            <input
              type="range"
              name="radius_km"
              min="1"
              max="50"
              value={formData.radius_km}
              onChange={handleChange}
            />
          </div>

          <div className="location-section">
            <button type="button" className="btn-secondary" onClick={handleUseLocation}>
              📍 Use Current Location
            </button>
            <span className="location-text">
              {formData.latitude.toFixed(4)}, {formData.longitude.toFixed(4)}
            </span>
          </div>

          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Publishing Request...' : 'Publish Item Request'}
          </button>
        </form>
      </div>
    </div>
  );
}
