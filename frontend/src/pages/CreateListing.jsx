import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, CheckCircle2, Sparkles, MapPin, Calculator, RotateCcw, Loader2, Compass } from 'lucide-react';
import api from '../api/client';
import { detectUserLocation } from '../utils/location';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import SupportChatButton from '../components/SupportChatButton';
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
    lending_radius: 5,
    years_owned: '',
    price_bought: '',
  });

  // Temporary Rule-Based Price Calculator state (never saved to database)
  const [calcInputs, setCalcInputs] = useState({
    purchase_price: '',
    item_age: '',
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
              suggested_category: 'Other',
            });
            setFormData((prev) => ({ ...prev, title: data.ai_label }));
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
      const res = await api.post('/listings/suggest-price', {
        purchase_price: rawPrice,
        age_years: rawAge,
      });
      const data = res.data;
      setSuggestion(data);
      setFormData((prev) => ({
        ...prev,
        price_per_day: data.daily_rent,
        security_deposit: data.security_deposit,
      }));
    } catch (err) {
      console.warn('Backend suggest-price failed, evaluating client-side rule formula:', err);
      const currentVal = Math.round(rawPrice * Math.pow(0.85, rawAge) * 100) / 100;
      const dailyRent = Math.round((currentVal * 0.04) / 5) * 5;
      const deposit = Math.round((currentVal * 0.20) / 5) * 5;
      const fallbackData = {
        current_value: currentVal,
        daily_rent: dailyRent,
        security_deposit: deposit,
      };
      setSuggestion(fallbackData);
      setFormData((prev) => ({
        ...prev,
        price_per_day: dailyRent,
        security_deposit: deposit,
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
      setFormData((prev) => ({
        ...prev,
        lat: loc.latitude,
        lon: loc.longitude,
        address: prev.address && prev.address !== 'Current Location' ? prev.address : loc.address,
      }));
      setLocationNotice(
        `📍 Located: ${loc.address} (${loc.method === 'gps' ? 'High-accuracy GPS' : 'Network/IP Geolocation'})`,
      );
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
      const payload = {
        name: formData.title,
        category: formData.category,
        description: formData.description,
        years_owned: formData.years_owned ? Number(formData.years_owned) : 0,
        price_bought: formData.price_bought ? Number(formData.price_bought) : 0,
        price_per_day: Number(formData.price_per_day),
        security_deposit: Number(formData.security_deposit),
        lending_radius_km: Number(formData.lending_radius),
        latitude: formData.lat ? Number(formData.lat) : null,
        longitude: formData.lon ? Number(formData.lon) : null,
        address_text: formData.address,
        ai_label: aiData?.label || null,
        ai_confidence: aiData ? Number(aiData.confidence) / 100.0 : null,
        photo_urls: uploadedUrls,
      };

      await api.post('/listings', payload);
      navigate('/my-listings');
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const isNextDisabled = !previews.length || isLoading || Boolean(uploadError) || uploadedUrls.length !== files.length;

  return (
    <div className="create-listing-page app-page">
      <div className="wrap">
        <div className="wizard-header">
          <h1 className="t-h2">List your item</h1>
          <p className="t-lead measure">Upload photos, set the details, and publish to neighbors nearby.</p>
        </div>

        <div className="wizard-progress">
          <div className={`step-indicator ${step >= 1 ? 'active' : ''}`}>01 · Photos</div>
          <div className={`step-indicator ${step >= 2 ? 'active' : ''}`}>02 · Details</div>
          <div className={`step-indicator ${step === 3 ? 'active' : ''}`}>03 · Publish</div>
        </div>

        {/* Step 1: AI Scan */}
        {step === 1 && (
          <Card variant="default" className="wizard-step scan-step">
            <div className="scan-head">
              <h3 className="t-card">Identify your item</h3>
              <p className="t-small muted">Upload a photo and our AI will suggest a title and category.</p>
            </div>

            <div
              className={['dropzone', previews.length ? 'has-image' : ''].join(' ')}
              onDragOver={(e) => e.preventDefault()}
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
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={isLoading}
                    onClick={(e) => {
                      e.stopPropagation();
                      setPreviews([]);
                      setFiles([]);
                      setUploadedUrls([]);
                      setAiData(null);
                      setUploadError('');
                      setAiOffline(false);
                    }}
                  >
                    Choose different photos
                  </Button>
                </div>
              ) : (
                <div className="dropzone-content">
                  <UploadCloud size={44} className="upload-icon" />
                  <h3 className="t-card">Click or drag photos here</h3>
                  <p className="t-small muted">Supports JPG and PNG</p>
                </div>
              )}
            </div>

            {isLoading && (
              <div className="ai-loading">
                <Sparkles className="sparkle-icon" />
                <p className="t-body">AI is analyzing your image…</p>
              </div>
            )}

            {aiData && !isLoading && (
              <div className="ai-result success">
                <CheckCircle2 size={24} />
                <div className="ai-result-text">
                  <h4 className="t-card">AI identified: {aiData.label}</h4>
                  <div className="confidence-track">
                    <div className="confidence-bar" style={{ width: `${aiData.confidence}%` }} />
                  </div>
                  <span className="t-small muted">{aiData.confidence}% match</span>
                </div>
              </div>
            )}

            {aiOffline && (
              <div className="ai-result error">
                <p className="t-body">{uploadError || 'AI detection is unavailable. Photos were uploaded and you can enter details manually.'}</p>
              </div>
            )}

            {previews.length > 0 && !isLoading && !uploadError && (
              <p className="t-small muted photo-upload-status">{uploadedUrls.length} of {files.length} photos uploaded.</p>
            )}

            <SupportChatButton step="listing_photos" label="Photo upload trouble? Chat with us" />

            <div className="wizard-actions">
              <Button variant="secondary" onClick={() => {}} disabled>
                Back
              </Button>
              <Button variant="primary" onClick={() => setStep(2)} disabled={isNextDisabled}>
                Next step
              </Button>
            </div>
          </Card>
        )}

        {/* Step 2: Details */}
        {step === 2 && (
          <Card variant="default" className="wizard-step details-step">
            <div className="scan-head">
              <h3 className="t-card">Item details</h3>
              <p className="t-small muted">Give your item a clear name and fair price.</p>
            </div>

            <div className="form-grid">
              <Input
                id="title"
                name="title"
                label="Item name"
                type="text"
                placeholder="e.g. Bosch Power Drill"
                value={formData.title}
                onChange={handleInputChange}
                required
              />
              <Input
                id="category"
                name="category"
                label="Category"
                type="select"
                value={formData.category}
                onChange={handleInputChange}
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </Input>
              <Input
                id="description"
                name="description"
                label="Description"
                type="textarea"
                rows={4}
                placeholder="Describe the condition and what&rsquo;s included."
                value={formData.description}
                onChange={handleInputChange}
              />

              {/* Price calculator card */}
              <Card variant="default" className="price-calculator-card">
                <div className="calculator-head">
                  <Calculator size={20} className="calc-icon" />
                  <div>
                    <h4 className="t-card">Rental price calculator</h4>
                    <p className="t-small muted">Formula-driven estimate based on depreciation. Not saved until you publish.</p>
                  </div>
                </div>

                <div className="calc-inputs">
                  <Input
                    id="input-purchase-price"
                    label="Original purchase price (₹)"
                    type="number"
                    min="0"
                    step="any"
                    placeholder="e.g. 10000"
                    value={calcInputs.purchase_price}
                    onChange={(e) => {
                      setCalcInputs((prev) => ({ ...prev, purchase_price: e.target.value }));
                      if (calcError) setCalcError('');
                    }}
                  />
                  <Input
                    id="input-item-age"
                    label="Item age (years)"
                    type="number"
                    min="0"
                    step="0.5"
                    placeholder="e.g. 2"
                    value={calcInputs.item_age}
                    onChange={(e) => {
                      setCalcInputs((prev) => ({ ...prev, item_age: e.target.value }));
                      if (calcError) setCalcError('');
                    }}
                  />
                </div>

                {calcError && (
                  <div className="calc-error" role="alert">
                    {calcError}
                  </div>
                )}

                <Button
                  variant="primary"
                  type="button"
                  onClick={handleSuggestPrice}
                  disabled={isSuggesting}
                  className="suggest-btn"
                >
                  <Sparkles size={16} />
                  {isSuggesting ? 'Calculating…' : 'Suggest price'}
                </Button>

                {suggestion && (
                  <div className="suggestion-results">
                    <div className="results-head">
                      <span className="temporary-tag">Temporary calculation · Not saved to DB</span>
                    </div>
                    <div className="results-grid">
                      <div className="suggestion-card current-value-card">
                        <span className="t-label">Current value</span>
                        <div className="t-stat">₹{Number(suggestion.current_value).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}</div>
                        <span className="t-small muted">purchase price × (0.85^age)</span>
                      </div>
                      <div className="suggestion-card rent-card">
                        <span className="t-label">Daily rent</span>
                        <div className="t-stat">₹{suggestion.daily_rent}</div>
                        <span className="t-small muted">4% of current value (nearest ₹5)</span>
                      </div>
                      <div className="suggestion-card deposit-card">
                        <span className="t-label">Security deposit</span>
                        <div className="t-stat">₹{suggestion.security_deposit}</div>
                        <span className="t-small muted">20% of current value (nearest ₹5)</span>
                      </div>
                    </div>
                    <div className="suggestion-applied">
                      <CheckCircle2 size={16} className="text-success" />
                      <span className="t-small muted">Suggested rent &amp; deposit applied below. Edit freely before publishing.</span>
                    </div>
                  </div>
                )}

                <div className="form-group">
                  <div className="label-with-hint">
                    <label htmlFor="input-price-per-day">Price per day (₹)</label>
                    {suggestion && Number(formData.price_per_day) === Number(suggestion.daily_rent) ? (
                      <Badge variant="accent" className="badge-suggested">Suggested applied</Badge>
                    ) : suggestion && (
                      <Button variant="secondary" size="sm" onClick={() => setFormData((prev) => ({ ...prev, price_per_day: suggestion.daily_rent }))}>
                        Reset to ₹{suggestion.daily_rent}
                      </Button>
                    )}
                  </div>
                  <Input
                    id="input-price-per-day"
                    name="price_per_day"
                    type="number"
                    min="0"
                    step="any"
                    placeholder="e.g. 150"
                    value={formData.price_per_day}
                    onChange={handleInputChange}
                  />
                </div>

                <div className="form-group">
                  <div className="label-with-hint">
                    <label htmlFor="input-security-deposit">Security deposit (₹)</label>
                    {suggestion && Number(formData.security_deposit) === Number(suggestion.security_deposit) ? (
                      <Badge variant="accent" className="badge-suggested">Suggested applied</Badge>
                    ) : suggestion && (
                      <Button variant="secondary" size="sm" onClick={() => setFormData((prev) => ({ ...prev, security_deposit: suggestion.security_deposit }))}>
                        Reset to ₹{suggestion.security_deposit}
                      </Button>
                    )}
                  </div>
                  <Input
                    id="input-security-deposit"
                    name="security_deposit"
                    type="number"
                    min="0"
                    step="any"
                    placeholder="e.g. 1000"
                    value={formData.security_deposit}
                    onChange={handleInputChange}
                  />
                </div>

                <Input
                  id="input-price-bought"
                  name="price_bought"
                  label="Original purchase price (₹)"
                  type="number"
                  min="0"
                  step="any"
                  placeholder="e.g. 15000"
                  value={formData.price_bought}
                  onChange={handleInputChange}
                />
                <Input
                  id="input-years-owned"
                  name="years_owned"
                  label="Item age (years)"
                  type="number"
                  min="0"
                  step="0.5"
                  placeholder="e.g. 2"
                  value={formData.years_owned}
                  onChange={handleInputChange}
                />
              </Card>
            </div>

            <div className="wizard-actions">
              <Button variant="secondary" onClick={() => setStep(1)}>
                Back
              </Button>
              <Button variant="primary" onClick={() => setStep(3)}>
                Next step
              </Button>
            </div>
          </Card>
        )}

        {/* Step 3: Location & Publish */}
        {step === 3 && (
          <Card variant="default" className="wizard-step publish-step">
            <div className="scan-head">
              <h3 className="t-card">Location &amp; availability</h3>
              <p className="t-small muted">Borrowers within your lending radius can see and request this item.</p>
            </div>

            <div className="form-grid">
              <div className="form-group full-width">
                <label className="t-label">Pickup address</label>
                <div className="input-with-button">
                  <Input
                    id="address"
                    name="address"
                    type="text"
                    placeholder="Enter locality, colony, or click Find Location"
                    value={formData.address}
                    onChange={handleInputChange}
                  />
                  <Button
                    variant="secondary"
                    type="button"
                    onClick={handleGetLocation}
                    disabled={isLocating}
                    className="locate-btn"
                    title="Find My Location (GPS + Network)"
                  >
                    {isLocating ? <Loader2 size={16} className="animate-spin" /> : <Compass size={16} />}
                    <span>{isLocating ? 'Locating…' : 'Use GPS'}</span>
                  </Button>
                </div>
                {locationNotice && (
                  <span className="location-feedback-hint t-small muted">{locationNotice}</span>
                )}
              </div>

              <Input
                id="lat"
                name="lat"
                label="Latitude"
                type="text"
                value={formData.lat}
                onChange={handleInputChange}
              />
              <Input
                id="lon"
                name="lon"
                label="Longitude"
                type="text"
                value={formData.lon}
                onChange={handleInputChange}
              />

              <div className="form-group full-width">
                <div className="slider-label-row">
                  <label className="t-label">Lending radius: <strong>{formData.lending_radius} km</strong></label>
                  <span className="slider-badge">Borrowers within {formData.lending_radius} km can see this item</span>
                </div>
                <Input
                  id="lending_radius"
                  name="lending_radius"
                  type="range"
                  min="1"
                  max="50"
                  value={formData.lending_radius}
                  onChange={handleInputChange}
                  className="range-input"
                />
                <div className="radius-scale-markers">
                  <span className="t-small muted">1 km</span>
                  <span className="t-small muted">10 km</span>
                  <span className="t-small muted">25 km</span>
                  <span className="t-small muted">50 km</span>
                </div>
              </div>
            </div>

            <SupportChatButton step="listing_create" label="Need help publishing? Chat with us" />

            <div className="wizard-actions">
              <Button variant="secondary" onClick={() => setStep(2)}>
                Back
              </Button>
              <Button variant="primary" onClick={handleSubmit} disabled={isLoading} className="publish-btn">
                {isLoading ? <Loader2 size={16} className="animate-spin" /> : 'Publish listing'}
              </Button>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
};

export default CreateListing;
