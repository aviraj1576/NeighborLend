import './Damage.css';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import Button from '../ui/Button';
import { cropToBlob, decodeFile, describeCameraError } from './imageUtils';

/**
 * Camera with an optional ghost overlay of an earlier photo (ported from the damage_check
 * module's CaptureCamera).
 *
 * Props
 *  ghostSrc        blob/data URL of the lender's photo (optional)
 *  aspect          width / height of the saved photo; lender and borrower must use the SAME value
 *  maxSide         longest side of the saved photo in px
 *  label           what is being shot, e.g. "Front (1 of 6)"
 *  frameGuide      show a box to fit the item in (lender, no ghost)
 *  onCapture       ({ blob, width, height }) => void, called on "Use photo"
 *  onCancel        optional, shows a Cancel button
 */
export default function CaptureCamera({
  ghostSrc,
  aspect = 4 / 3,
  maxSide = 1024,
  label,
  initialOpacity = 0.35,
  frameGuide = false,
  onCapture,
  onCancel,
}) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const fileRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [opacity, setOpacity] = useState(initialOpacity);
  const [ghostOn, setGhostOn] = useState(true);
  const [shot, setShot] = useState(null);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    setReady(false);
  }, []);

  const startCamera = useCallback(async () => {
    stopCamera();
    setError('');
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setError(describeCameraError(null));
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      });
      streamRef.current = stream;
      const video = videoRef.current;
      if (!video) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      video.srcObject = stream;
      await video.play();
      setReady(true);
    } catch (err) {
      setError(describeCameraError(err));
    }
  }, [stopCamera]);

  useEffect(() => {
    startCamera();
    return stopCamera;
  }, [startCamera, stopCamera]);

  useEffect(() => () => { if (shot) URL.revokeObjectURL(shot.url); }, [shot]);

  async function takePhoto() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    try {
      const out = await cropToBlob(video, video.videoWidth, video.videoHeight, aspect, maxSide);
      setShot({ ...out, url: URL.createObjectURL(out.blob) });
    } catch (err) {
      setError(err.message);
    }
  }

  async function onFilePicked(e) {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    try {
      const img = await decodeFile(file);
      // With a guide photo the shape must match it so the two line up.
      const useAspect = ghostSrc ? aspect : img.width / img.height;
      const out = await cropToBlob(img.source, img.width, img.height, useAspect, maxSide);
      setShot({ ...out, url: URL.createObjectURL(out.blob) });
    } catch {
      setError('That file could not be read as a photo.');
    }
  }

  const reviewing = Boolean(shot);

  return (
    <section className="cc" aria-label={label ? `Capture ${label}` : 'Capture photo'}>
      {label && <h3 className="cc-title">{label}</h3>}

      <div className="cc-frame" style={{ aspectRatio: String(aspect) }}>
        <video
          ref={videoRef}
          className="cc-media"
          playsInline
          muted
          autoPlay
          style={{ visibility: reviewing ? 'hidden' : 'visible' }}
        />
        {!reviewing && ghostSrc && ghostOn && (
          <img className="cc-media cc-ghost" src={ghostSrc} alt="" style={{ opacity }} />
        )}
        {!reviewing && frameGuide && !ghostSrc && <div className="cc-guide" aria-hidden="true" />}
        {reviewing && <img className="cc-media cc-contain" src={shot.url} alt="Photo you just took" />}
        {!ready && !reviewing && !error && <p className="cc-status">Starting camera…</p>}
      </div>

      {error && <p className="cc-error" role="alert">{error}</p>}

      {!reviewing && (
        <>
          {ghostSrc && (
            <div className="cc-ghost-controls">
              <label className="cc-toggle">
                <input type="checkbox" checked={ghostOn} onChange={(e) => setGhostOn(e.target.checked)} />
                Show guide
              </label>
              <label className="cc-slider">
                <span>Guide strength</span>
                <input
                  type="range" min="0.1" max="0.8" step="0.05" value={opacity}
                  disabled={!ghostOn} onChange={(e) => setOpacity(Number(e.target.value))}
                />
              </label>
            </div>
          )}
          {frameGuide && !ghostSrc && (
            <p className="cc-hint">Fit the whole item inside the box. Use the same spot and light on return.</p>
          )}
          {ghostSrc && (
            <p className="cc-hint">Move until the item lines up with the faded photo, then take the shot.</p>
          )}

          <div className="cc-actions">
            {onCancel && <Button variant="secondary" size="sm" onClick={onCancel}>Cancel</Button>}
            <button
              type="button" className="cc-shutter" onClick={takePhoto}
              disabled={!ready} aria-label="Take photo"
            />
            <Button variant="secondary" size="sm" onClick={() => fileRef.current && fileRef.current.click()}>
              Choose a file
            </Button>
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={onFilePicked} data-testid="cc-file" />
          </div>
          <p className="cc-hint">
            {ghostSrc ? 'A photo from a file is cropped to match the lender’s photo.' : 'A photo from a file keeps its own shape.'}
          </p>
          {error && (
            <div className="cc-actions">
              <Button variant="secondary" size="sm" onClick={startCamera}>Try the camera again</Button>
            </div>
          )}
        </>
      )}

      {reviewing && (
        <div className="cc-actions">
          <Button variant="secondary" size="sm" onClick={() => setShot(null)}>Retake</Button>
          <Button
            variant="primary" size="sm"
            onClick={() => onCapture && onCapture({ blob: shot.blob, width: shot.width, height: shot.height })}
          >
            Use photo
          </Button>
        </div>
      )}
    </section>
  );
}
