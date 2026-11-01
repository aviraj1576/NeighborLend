import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, CheckCircle2, Sparkles, MapPin, Search, Calculator, RotateCcw, Loader2, Compass } from 'lucide-react';
import api from '../api/client';
import { detectUserLocation } from '../utils/location';
import './CreateListing.css';

const CATEGORIES = ['Tools', 'Electronics', 'Sports', 'Party', 'Books', 'Other'];

const CreateListing = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [aiOffline, setAiOffline] = useState(false);
  const fileInputRef = useRef(null);

  // Form State
  const [files, setFiles] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [aiData, setAiData] = useState(null);
  const [uploadedUrls, setUploadedUrls] = useState([]);
  const [uploadError, setUploadError] = useState('');
  
  const [formData, setFormData] = useState({
    title: '',
    category: 'Other',
    description: '',
    price_per_day: '',
    security_deposit: '',
    lat: 28.6139,
    lon: 77.2090,
    address: '',
    lending_radius: 5
  });

  // Temporary Rule-Based Price Calculator state (never saved to database)
  const [calcInputs, setCalcInputs] = useState({
    purchase_price: '',
    item_age: ''
  });
  const [suggestion, setSuggestion] = useState(null);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [calcError, setCalcError] = useState('');

  // Step 1: Handle File
  const handleFileDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer.files?.length) {
      processFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleFileSelect = (e) => {
    if (e.target.files?.length) {
      processFiles(Array.from(e.target.files));
      e.target.value = '';
    }
  };

  const processFiles = async (selectedFiles) => {
    const imageFiles = selectedFiles.filter((selectedFile) => selectedFile.type.startsWith('image/'));
    if (!imageFiles.length) return;

    setFiles(imageFiles);
    setPreviews(imageFiles.map((selectedFile) => URL.createObjectURL(selectedFile)));
    setUploadedUrls([]);
    setUploadError('');
    setAiData(null);
    setIsLoading(true);
    setAiOffline(false);

    const urls = [];
    let failedUploads = 0;
    try {
      for (let index = 0; index < imageFiles.length; index += 1) {
        const form = new FormData();
        form.append('file', imageFiles[index]);
        try {
          const uploadRes = await api.post('/upload', form);
          const data = uploadRes.data;
          if (!data.url) throw new Error('Upload response did not include an image URL.');
          urls.push(data.url);

          if (index === 0 && data.ai_label) {
            setAiData({
              label: data.ai_label,
              confidence: (data.ai_confidence * 100).toFixed(0),
              suggested_category: 'Other'
            });
            setFormData(prev => ({ ...prev, title: data.ai_label }));
          }
        } catch (err) {
          failedUploads += 1;
          console.error('Image upload failed:', err);
        }
      }
      setUploadedUrls(urls);
      if (failedUploads) {
        setUploadError(`${failedUploads} photo${failedUploads === 1 ? '' : 's'} could not be uploaded. Select the photos again to retry.`);
        setAiOffline(true);
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Step 2: Handle Details & Rule-Based Price Suggestion
  const handleSuggestPrice = async () => {
    const rawPrice = parseFloat(calcInputs.purchase_price);
    const rawAge = calcInputs.item_age !== '' ? parseFloat(calcInputs.item_age) : 0;

    if (isNaN(rawPrice) || rawPrice <= 0) {
      setCalcError('Please enter a valid original purchase price (> ₹0).');
      return;
    }
    if (isNaN(rawAge) || rawAge < 0) {
      setCalcError('Item age must be 0 or greater.');
      return;
    }

    setCalcError('');
    setIsSuggesting(true);

    try {
      // Calculate via FastAPI backend endpoint
      const res = await api.post('/listings/suggest-price', {
        purchase_price: rawPrice,
        age_years: rawAge
      });
      const data = res.data;
      setSuggestion(data);
      // Auto-populate form with suggested values; owner can freely edit them below
      setFormData(prev => ({
        ...prev,
        price_per_day: data.daily_rent,
        security_deposit: data.security_deposit
      }));
    } catch (err) {
      console.warn('Backend suggest-price failed, evaluating client-side rule formula:', err);
      // Rule-based fallback:
      // Current value = purchase_price * (0.85 ** age_years)
      // Daily rent = 4% of current value, rounded to nearest 5
      // Refundable security deposit = 20% of current value, rounded to nearest 5
      const currentVal = Math.round(rawPrice * Math.pow(0.85, rawAge) * 100) / 100;
      const dailyRent = Math.round((currentVal * 0.04) / 5) * 5;
      const deposit = Math.round((currentVal * 0.20) / 5) * 5;
      const fallbackData = {
        current_value: currentVal,
        daily_rent: dailyRent,
        security_deposit: deposit
      };
      setSuggestion(fallbackData);
      setFormData(prev => ({
        ...prev,
        price_per_day: dailyRent,
        security_deposit: deposit
      }));
    } finally {
      setIsSuggesting(false);
    }
  };

  const handleInputChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  // Step 3: Location & Submit
  const [isLocating, setIsLocating] = useState(false);
  const [locationNotice, setLocationNotice] = useState('');

  const handleGetLocation = async () => {
    setIsLocating(true);
    setLocationNotice('');
    try {
      const loc = await detectUserLocation();
      setFormData(prev => ({
        ...prev,
        lat: loc.latitude,
        lon: loc.longitude,
        address: prev.address && prev.address !== 'Current Location' ? prev.address : loc.address
      }));
      setLocationNotice(`📍 Located: ${loc.address} (${loc.method === 'gps' ? 'High-accuracy GPS' : 'Network/IP Geolocation'})`);
    } catch (err) {
      console.error('Failed to get location:', err);
      setLocationNotice('Could not find location automatically. Please enter your address or coordinates.');
    } finally {
      setIsLocating(false);
    }
  };

  const handleSubmit = async () => {
    setIsLoading(true);
    try {
      // Ephemeral feature: Do not save purchase price, item age, or estimated value to DB
      const payload = {
        name: formData.title,
        category: formData.category,
        description: formData.description,
        years_owned: 0,
        price_bought: 0,
        price_per_day: Number(formData.price_per_day),
        security_deposit: Number(formData.security_deposit),
        lending_radius_km: Number(formData.lending_radius),
        latitude: formData.lat ? Number(formData.lat) : null,
        longitude: formData.lon ? Number(formData.lon) : null,
        address_text: formData.address,
        ai_label: aiData?.label || null,
        ai_confidence: aiData ? Number(aiData.confidence) / 100.0 : null,
        photo_urls: uploadedUrls
      };

      await api.post('/listings', payload);
      navigate('/my-listings');
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };


  return (
    <div className="create-listing-page container fade-in-up">
      <div className="wizard-container glass">
        
        {/* Progress Tracker */}
        <div className="wizard-progress">
          <div className={`step-indicator ${step >= 1 ? 'active' : ''}`}>1. AI Scan</div>
          <div className="step-line"></div>
          <div className={`step-indicator ${step >= 2 ? 'active' : ''}`}>2. Details</div>
          <div className="step-line"></div>
          <div className={`step-indicator ${step >= 3 ? 'active' : ''}`}>3. Publish</div>
        </div>

        {/* Step 1: AI Scan */}
        {step === 1 && (
          <div className="wizard-step">
            <h2>Identify your item</h2>
            <p className="text-muted">Upload a photo and our AI will do the heavy lifting.</p>
            
            <div 
              className={`dropzone ${previews.length ? 'has-image' : ''}`}
              onDragOver={e => e.preventDefault()}
              onDrop={handleFileDrop}
              onClick={() => !previews.length && fileInputRef.current?.click()}
            >
              <input type="file" ref={fileInputRef} onChange={handleFileSelect} hidden accept="image/*" multiple />
              
              {previews.length ? (
                <div className="preview-container">
                  <div className="preview-grid">
                    {previews.map((previewUrl, index) => (
                      <img key={previewUrl} src={previewUrl} alt={`Photo ${index + 1}`} className="image-preview" />
                    ))}
                  </div>
                  <button className="btn-outline reupload-btn" disabled={isLoading} onClick={(e) => {
                    e.stopPropagation();
                    setPreviews([]);
                    setFiles([]);
                    setUploadedUrls([]);
                    setAiData(null);
                    setUploadError('');
                    setAiOffline(false);
                  }}>
                    Choose different photos
                  </button>
                </div>
              ) : (
                <div className="dropzone-content">
                  <UploadCloud size={48} className="upload-icon" />
                  <h3>Click or drag photos here</h3>
                  <p>Supports JPG and PNG</p>
                </div>
              )}
            </div>

            {isLoading && (
              <div className="ai-loading">
                <Sparkles className="sparkle-icon" />
                <p>AI is analyzing your image...</p>
              </div>
            )}

            {aiData && !isLoading && (
              <div className="ai-result success">
                <CheckCircle2 size={24} />
                <div className="ai-result-text">
                  <h4>AI identified: {aiData.label}</h4>
                  <div className="confidence-bar-bg">
                    <div className="confidence-bar" style={{width: `${aiData.confidence}%`}}></div>
                  </div>
                  <span className="confidence-text">{aiData.confidence}% match</span>
                </div>
              </div>
            )}

            {aiOffline && (
              <div className="ai-result error">
                <p>{uploadError || 'AI detection is unavailable. Photos were uploaded and you can enter details manually.'}</p>
              </div>
            )}

            {previews.length > 0 && !isLoading && !uploadError && (
              <p className="text-muted photo-upload-status">{uploadedUrls.length} of {files.length} photos uploaded.</p>
            )}

            <div className="wizard-actions">
              <button 
                className="btn-primary" 
                onClick={() => setStep(2)}
                disabled={!previews.length || isLoading || Boolean(uploadError) || uploadedUrls.length !== files.length}
              >
                Next Step
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Details */}
        {step === 2 && (
          <div className="wizard-step">
            <h2>Item Details</h2>
            <div className="form-grid">
              <div className="form-group full-width">
                <label>Item Name</label>
                <input type="text" name="title" value={formData.title} onChange={handleInputChange} placeholder="e.g. Bosch Power Drill" />
              </div>
              
              <div className="form-group">
                <label>Category</label>
                <select name="category" value={formData.category} onChange={handleInputChange}>
                  {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              
              <div className="form-group full-width">
                <label>Description</label>
                <textarea name="description" value={formData.description} onChange={handleInputChange} rows={4} placeholder="Describe the condition, what's included, etc."></textarea>
              </div>

              {/* Rule-based Price Suggestion Calculator (Temporary / Ephemeral) */}
              <div className="form-group full-width price-suggestion-box glass">
                <div className="box-header">
                  <Calculator size={22} className="text-accent" />
                  <div>
                    <h4>Rental Price Calculator</h4>
                    <p className="suggestion-subtitle">
                      Calculate fair rental pricing based on item depreciation (formula-driven).
                    </p>
                  </div>
                </div>

                <div className="price-inputs-grid">
                  <div className="form-group">
                    <label htmlFor="input-purchase-price">Original Purchase Price (₹)</label>
                    <input 
                      id="input-purchase-price"
                      type="number" 
                      min="0"
                      step="any"
                      placeholder="e.g. 10000"
                      value={calcInputs.purchase_price} 
                      onChange={(e) => {
                        setCalcInputs(prev => ({ ...prev, purchase_price: e.target.value }));
                        if (calcError) setCalcError('');
                      }} 
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="input-item-age">Item Age (years)</label>
                    <input 
                      id="input-item-age"
                      type="number" 
                      min="0" 
                      step="0.5"
                      placeholder="e.g. 2"
                      value={calcInputs.item_age} 
                      onChange={(e) => {
                        setCalcInputs(prev => ({ ...prev, item_age: e.target.value }));
                        if (calcError) setCalcError('');
                      }} 
                    />
                  </div>
                </div>

                {calcError && (
                  <div className="price-calc-error">
                    {calcError}
                  </div>
                )}

                <div className="suggest-actions">
                  <button 
                    type="button"
                    id="btn-suggest-price"
                    className="btn-primary suggest-btn" 
                    onClick={handleSuggestPrice} 
                    disabled={isSuggesting}
                  >
                    <Sparkles size={18} />
                    {isSuggesting ? 'Calculating...' : 'Suggest Price'}
                  </button>
                </div>

                {/* Display All Three Calculated Values */}
                {suggestion && (
                  <div className="suggestion-results-container fade-in">
                    <div className="results-header">
                      <h5>Calculated Price Breakdown</h5>
                      <span className="temporary-tag">Temporary calculation &bull; Not saved to DB</span>
                    </div>

                    <div className="suggestion-results-grid">
                      {/* 1. Current Value */}
                      <div className="suggestion-card current-value-card">
                        <span className="card-label">Current Value</span>
                        <div className="card-value">₹{Number(suggestion.current_value).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}</div>
                        <span className="card-formula">purchase_price &times; (0.85<sup>age</sup>)</span>
                      </div>

                      {/* 2. Daily Rent */}
                      <div className="suggestion-card rent-card">
                        <span className="card-label">Daily Rent</span>
                        <div className="card-value">₹{suggestion.daily_rent}</div>
                        <span className="card-formula">4% of current value (nearest ₹5)</span>
                      </div>

                      {/* 3. Refundable Security Deposit */}
                      <div className="suggestion-card deposit-card">
                        <span className="card-label">Refundable Security Deposit</span>
                        <div className="card-value">₹{suggestion.security_deposit}</div>
                        <span className="card-formula">20% of current value (nearest ₹5)</span>
                      </div>
                    </div>

                    <div className="suggestion-applied-note">
                      <CheckCircle2 size={16} className="text-success" />
                      <span>Suggested daily rent & deposit applied below. You can edit them freely before publishing.</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Editable Rent & Deposit Inputs */}
              <div className="form-group">
                <div className="label-with-hint">
                  <label htmlFor="input-price-per-day">Price per Day (₹) *</label>
                  {suggestion && (
                    Number(formData.price_per_day) === Number(suggestion.daily_rent) ? (
                      <span className="badge-suggested">Suggested applied</span>
                    ) : (
                      <button 
                        type="button" 
                        className="reset-to-suggested-btn"
                        onClick={() => setFormData(prev => ({ ...prev, price_per_day: suggestion.daily_rent }))}
                        title="Reset to suggested price"
                      >
                        <RotateCcw size={12} /> Reset to ₹{suggestion.daily_rent}
                      </button>
                    )
                  )}
                </div>
                <input 
                  id="input-price-per-day"
                  type="number" 
                  name="price_per_day" 
                  min="0"
                  step="any"
                  placeholder="e.g. 150"
                  value={formData.price_per_day} 
                  onChange={handleInputChange} 
                  required
                />
              </div>

              <div className="form-group">
                <div className="label-with-hint">
                  <label htmlFor="input-security-deposit">Security Deposit (₹)</label>
                  {suggestion && (
                    Number(formData.security_deposit) === Number(suggestion.security_deposit) ? (
                      <span className="badge-suggested">Suggested applied</span>
                    ) : (
                      <button 
                        type="button" 
                        className="reset-to-suggested-btn"
                        onClick={() => setFormData(prev => ({ ...prev, security_deposit: suggestion.security_deposit }))}
                        title="Reset to suggested deposit"
                      >
                        <RotateCcw size={12} /> Reset to ₹{suggestion.security_deposit}
                      </button>
                    )
                  )}
                </div>
                <input 
                  id="input-security-deposit"
                  type="number" 
                  name="security_deposit" 
                  min="0"
                  step="any"
                  placeholder="e.g. 1000"
                  value={formData.security_deposit} 
                  onChange={handleInputChange} 
                />
              </div>
            </div>


            <div className="wizard-actions">
              <button className="btn-outline" onClick={() => setStep(1)}>Back</button>
              <button className="btn-primary" onClick={() => setStep(3)}>Next Step</button>
            </div>
          </div>
        )}

        {/* Step 3: Location */}
        {step === 3 && (
          <div className="wizard-step">
            <h2>Location & Availability</h2>
            <div className="form-grid">
              
              <div className="form-group full-width">
                <label>Pickup Address</label>
                <div className="input-with-button">
                  <input 
                    type="text" 
                    name="address" 
                    value={formData.address} 
                    onChange={handleInputChange} 
                    placeholder="Enter locality, colony, or click Find Location" 
                  />
                  <button 
                    type="button"
                    className="btn-primary locate-btn-styled" 
                    onClick={handleGetLocation} 
                    disabled={isLocating}
                    title="Find My Location (GPS + Network)"
                  >
                    {isLocating ? <Loader2 size={18} className="animate-spin" /> : <Compass size={18} />}
                    <span>{isLocating ? 'Locating...' : 'Use My GPS'}</span>
                  </button>
                </div>
                {locationNotice && (
                  <span className="location-feedback-hint">{locationNotice}</span>
                )}
              </div>

              <div className="form-group">
                <label>Latitude</label>
                <input type="text" name="lat" value={formData.lat} onChange={handleInputChange} />
              </div>
              <div className="form-group">
                <label>Longitude</label>
                <input type="text" name="lon" value={formData.lon} onChange={handleInputChange} />
              </div>

              <div className="form-group full-width">
                <div className="slider-label-row">
                  <label>Lending Radius: <strong>{formData.lending_radius} km</strong></label>
                  <span className="slider-badge">Borrowers within {formData.lending_radius} km can see and request this item</span>
                </div>
                <input 
                  type="range" 
                  name="lending_radius"
                  min="1" max="50" 
                  value={formData.lending_radius} 
                  onChange={handleInputChange}
                  className="full-width-slider"
                />
                <div className="radius-scale-markers">
                  <span>1 km (Neighbourhood)</span>
                  <span>10 km</span>
                  <span>25 km</span>
                  <span>50 km (City-wide)</span>
                </div>
              </div>


            </div>

            <div className="wizard-actions">
              <button className="btn-outline" onClick={() => setStep(2)}>Back</button>
              <button className="btn-primary publish-btn" onClick={handleSubmit} disabled={isLoading}>
                {isLoading ? <span className="spinner"></span> : 'Publish Listing'}
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
};

export default CreateListing;
