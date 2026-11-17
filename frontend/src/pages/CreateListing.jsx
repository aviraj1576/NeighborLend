import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, CheckCircle2, Sparkles, MapPin, Calculator, RotateCcw, Loader2, Compass, Camera, X, Trash2 } from 'lucide-react';
import api from '../api/client';
import { detectUserLocation } from '../utils/location';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import SupportChatButton from '../components/SupportChatButton';
import './CreateListing.css';

const CATEGORIES = ['Tools', 'Electronics', 'Sports', 'Party', 'Books', 'Other'];

const mapLabelToCategory = (label) => {
  if (!label) return 'Other';
  const l = label.toLowerCase();
  if (/drill|hammer|wrench|screwdriver|tool|saw|pliers|ladder/.test(l)) return 'Tools';
  if (/laptop|phone|camera|headphone|keyboard|drone|microwave|kettle|blender|electronic/.test(l)) return 'Electronics';
  if (/bike|bicycle|scooter|tent|basketball|ball|sports|camping|barbell/.test(l)) return 'Sports';
  if (/party|speaker|guitar|music/.test(l)) return 'Party';
  if (/book|novel|textbook/.test(l)) return 'Books';
  return 'Other';
};

const compressImage = async (file, maxWidth = 1600, maxHeight = 1600, quality = 0.85) => {
  if (typeof window === 'undefined' || !window.FileReader) return file;
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onerror = () => resolve(file);
    reader.onload = (e) => {
      const img = new Image();
      img.onerror = () => resolve(file);
      img.onload = () => {
        let width = img.width;
        let height = img.height;
        if (width <= maxWidth && height <= maxHeight && file.size < 600 * 1024) {
          resolve(file);
          return;
        }
        if (width > height) {
          if (width > maxWidth) {
            height = Math.round((height * maxWidth) / width);
            width = maxWidth;
          }
        } else {
          if (height > maxHeight) {
            width = Math.round((width * maxHeight) / height);
            height = maxHeight;
          }
        }
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          resolve(file);
          return;
        }
        ctx.drawImage(img, 0, 0, width, height);
        canvas.toBlob(
          (blob) => {
            if (!blob) {
              resolve(file);
              return;
            }
            const cleanName = (file.name || 'photo.jpg').replace(/\.[^/.]+$/, '') + '.jpg';
            const compressedFile = new File([blob], cleanName, {
              type: 'image/jpeg',
              lastModified: Date.now(),
            });
            resolve(compressedFile);
          },
          'image/jpeg',
          quality
        );
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  });
};

const apiErrorMessage = (err, fallback) => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : 'Listing';
      return `${field}: ${item.msg}`;
    }).join(' ');
  }
  return err?.message || fallback;
};

const CreateListing = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const submissionLockRef = useRef(false);
  const [aiOffline, setAiOffline] = useState(false);
  const fileInputRef = useRef(null);
  const cameraFallbackRef = useRef(null);
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const previewUrlsRef = useRef([]);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraError, setCameraError] = useState('');

  const stopCamera = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraOpen(false);
  };

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    previewUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  const openCamera = async () => {
    setCameraError('');
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError('Live camera is unavailable in this browser. Use the camera or photo library picker instead.');
      cameraFallbackRef.current?.click();
      return;
    }
    if (!window.isSecureContext) {
      setCameraError('Camera access requires a secure connection (HTTPS or localhost). Use the photo picker instead.');
      cameraFallbackRef.current?.click();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
      streamRef.current = stream;
      setCameraOpen(true);
      requestAnimationFrame(() => {
        if (videoRef.current) videoRef.current.srcObject = stream;
      });
    } catch (error) {
      const messages = {
        NotAllowedError: 'Camera permission was denied. Allow camera access in your browser settings or use the photo picker.',
        NotFoundError: 'No camera was found. Use the photo picker to choose an image.',
        NotReadableError: 'The camera is busy or unavailable. Close other camera apps and try again.',
      };
      setCameraError(messages[error.name] || 'The camera could not be opened. Use the photo picker or try again.');
    }
  };

  const capturePhoto = () => {
    const video = videoRef.current;
    if (!video?.videoWidth) { setCameraError('Camera is still starting. Please try again in a moment.'); return; }
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) { setCameraError('This photo could not be captured. Please try again.'); return; }
      const captured = new File([blob], `listing-photo-${Date.now()}.jpg`, { type: 'image/jpeg' });
      processFiles([...files, captured]);
      stopCamera();
    }, 'image/jpeg', 0.92);
  };

  const removePhoto = (index) => processFiles(files.filter((_, fileIndex) => fileIndex !== index));

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
    lat: 30.3362,
    lon: 76.3922,
    address: 'Patiala, Punjab',
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
      processFiles([...files, ...Array.from(e.dataTransfer.files)]);
    }
  };

  const handleFileSelect = (e) => {
    if (e.target.files?.length) {
      processFiles([...files, ...Array.from(e.target.files)]);
      e.target.value = '';
    }
  };

  const processFiles = async (selectedFiles) => {
    const imageFiles = selectedFiles.filter((selectedFile) => selectedFile.type.startsWith('image/'));
    previewUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    if (!imageFiles.length) {
      setFiles([]); setPreviews([]); setUploadedUrls([]); setAiData(null); setUploadError(''); setAiOffline(false);
      return;
    }

    setFiles(imageFiles);
    const nextPreviews = imageFiles.map((selectedFile) => URL.createObjectURL(selectedFile));
    previewUrlsRef.current = nextPreviews;
    setPreviews(nextPreviews);
    setUploadedUrls([]);
    setUploadError('');
    setAiData(null);
    setIsLoading(true);
    setAiOffline(false);

    const urls = [];
    let failedUploads = 0;
    let firstUploadError = '';
    try {
      const filesToUpload = await Promise.all(imageFiles.map((file) => compressImage(file)));

      for (let index = 0; index < filesToUpload.length; index += 1) {
        const form = new FormData();
        form.append('file', filesToUpload[index]);
        try {
          let uploadRes;
          try {
            uploadRes = await api.post('/upload', form);
          } catch (initialErr) {
            // Retry once on transient network or gateway glitch
            await new Promise((resolve) => setTimeout(resolve, 1000));
            uploadRes = await api.post('/upload', form);
          }
          const data = uploadRes.data;
          if (!data.url) throw new Error('Upload response did not include an image URL.');
          urls.push(data.url);

          if (index === 0 && data.ai_label) {
            const cat = mapLabelToCategory(data.ai_label);
            setAiData({
              label: data.ai_label,
              confidence: (data.ai_confidence * 100).toFixed(0),
              suggested_category: cat,
            });
            setFormData((prev) => ({
              ...prev,
              title: prev.title || data.ai_label,
              category: prev.category === 'Other' ? cat : prev.category,
            }));
          }
        } catch (err) {
          failedUploads += 1;
          if (!firstUploadError) {
            firstUploadError = apiErrorMessage(err, 'Photo upload failed.');
          }
          console.error('Image upload failed:', err);
        }
      }
      setUploadedUrls(urls);
      if (failedUploads) {
        setUploadError(
          `${failedUploads} photo${failedUploads === 1 ? '' : 's'} could not be uploaded. ${firstUploadError} Select the photos again to retry.`,
        );
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
        address: loc.address || prev.address || 'Patiala, Punjab',
      }));
      setLocationNotice(
        `📍 Located: ${loc.address} (${loc.method === 'gps' ? 'High-accuracy GPS' : loc.method === 'ip' ? 'Network/IP Geolocation' : 'Default Location (Patiala, Punjab)'})`,
      );
    } catch (err) {
      console.error('Failed to get location:', err);
      setLocationNotice('Location set to Patiala, Punjab (Default).');
      setFormData((prev) => ({
        ...prev,
        lat: 30.3362,
        lon: 76.3922,
        address: prev.address || 'Patiala, Punjab',
      }));
    } finally {
      setIsLocating(false);
    }
  };

  const handleSubmit = async (publish = true) => {
    if (submissionLockRef.current) return;
    setSubmitError('');

    if (!formData.title.trim()) {
      setSubmitError('Enter an item name before saving your listing.');
      return;
    }
    const dailyPrice = Number(formData.price_per_day);
    if (!formData.price_per_day || !Number.isFinite(dailyPrice) || dailyPrice <= 0) {
      setSubmitError('Enter a valid price per day greater than zero.');
      return;
    }
    const deposit = Number(formData.security_deposit || 0);
    if (!Number.isFinite(deposit) || deposit < 0) {
      setSubmitError('Enter a valid non-negative security deposit.');
      return;
    }
    if (!files.length || uploadedUrls.length !== files.length || uploadError) {
      setSubmitError('Upload all listing photos before saving.');
      return;
    }

    submissionLockRef.current = true;
    setIsLoading(true);
    try {
      const payload = {
        name: formData.title.trim(),
        category: formData.category,
        description: formData.description,
        years_owned: formData.years_owned ? Number(formData.years_owned) : 0,
        price_bought: formData.price_bought ? Number(formData.price_bought) : 0,
        price_per_day: dailyPrice,
        security_deposit: deposit,
        lending_radius_km: Number(formData.lending_radius),
        latitude: formData.lat ? Number(formData.lat) : null,
        longitude: formData.lon ? Number(formData.lon) : null,
        address_text: formData.address,
        ai_label: aiData?.label || null,
        ai_confidence: aiData ? Number(aiData.confidence) / 100.0 : null,
        photo_urls: uploadedUrls,
        publish,
      };

      const { data } = await api.post('/listings', payload);
      const published = publish && data?.status === 'published';
      navigate('/my-listings', {
        state: {
          listingNotice: {
            type: published || !publish ? 'success' : 'error',
            text: published
              ? 'Listing published.'
              : publish
                ? 'Listing was saved, but the server did not publish it. Check its status and try again.'
                : 'Draft saved.',
          },
        },
      });
    } catch (err) {
      console.error(err);
      setSubmitError(apiErrorMessage(err, 'Could not save the listing. Please try again.'));
    } finally {
      submissionLockRef.current = false;
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
              <input type="file" ref={cameraFallbackRef} onChange={handleFileSelect} hidden accept="image/*" capture="environment" />

              {previews.length ? (
                <div className="preview-container">
                  <div className="preview-grid">
                    {previews.map((previewUrl, index) => (
                      <div className="listing-photo-tile" key={previewUrl}>
                        <img src={previewUrl} alt={`Photo ${index + 1}`} className="image-preview" />
                        <button type="button" className="photo-remove" aria-label={`Remove photo ${index + 1}`} disabled={isLoading} onClick={(e) => { e.stopPropagation(); removePhoto(index); }}><Trash2 size={16} /></button>
                      </div>
                    ))}
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={isLoading}
                    onClick={(e) => {
                      e.stopPropagation();
                      fileInputRef.current?.click();
                    }}
                  >
                    Add photos from device
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

            <div className="photo-actions">
              <Button type="button" variant="secondary" disabled={isLoading} onClick={openCamera}><Camera size={18} /> Take a photo</Button>
              <Button type="button" variant="secondary" disabled={isLoading} onClick={() => fileInputRef.current?.click()}><UploadCloud size={18} /> Choose from device</Button>
            </div>
            {cameraError && <p className="camera-message" role="status">{cameraError}</p>}
            {cameraOpen && <div className="camera-dialog" role="dialog" aria-modal="true" aria-label="Take listing photo">
              <div className="camera-panel">
                <div className="camera-dialog-head"><h3 className="t-card">Take a listing photo</h3><button type="button" className="camera-close" onClick={stopCamera} aria-label="Close camera"><X /></button></div>
                <video ref={videoRef} autoPlay playsInline muted className="camera-video" />
                <div className="camera-controls"><Button type="button" variant="primary" onClick={capturePhoto}><Camera size={18} /> Capture photo</Button><Button type="button" variant="secondary" onClick={() => { stopCamera(); cameraFallbackRef.current?.click(); }}>Use device camera</Button></div>
              </div>
            </div>}

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

              <div className="form-group full-width lending-radius-group">
                <div className="slider-label-row">
                  <label className="t-label" htmlFor="lending_radius">
                    Lending radius: <strong>{formData.lending_radius} km</strong>
                  </label>
                  <span className="slider-badge">Borrowers within {formData.lending_radius} km can see this item</span>
                </div>
                <input
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
              <Button variant="secondary" onClick={() => handleSubmit(false)} disabled={isLoading}>
                {isLoading ? <Loader2 size={16} className="animate-spin" /> : 'Save as draft'}
              </Button>
              <Button variant="primary" onClick={() => handleSubmit(true)} disabled={isLoading} className="publish-btn">
                {isLoading ? <Loader2 size={16} className="animate-spin" /> : 'Publish listing'}
              </Button>
            </div>
            {submitError && <p className="calc-error" role="alert">{submitError}</p>}
          </Card>
        )}
      </div>
    </div>
  );
};

export default CreateListing;
