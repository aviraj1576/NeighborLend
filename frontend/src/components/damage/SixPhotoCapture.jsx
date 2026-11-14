import './Damage.css';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import Button from '../ui/Button';
import AuthImage from './AuthImage';
import GuidedCapture from './GuidedCapture';
import { LABELS, VIEWS, apiError, getCheck, userPhotoPath } from './damageApi';

const INTRO = {
  before: 'Take all 6 photos (front, back, left, right, top, bottom) in the same spot and light you will use on return. Fit the whole item inside the dashed box.',
  after: 'Take the same 6 photos again. The lender’s photo is shown faded so you can line the item up with it.',
};

/**
 * Collects the 6 photos for one phase through the damage_check module's guided flow.
 * Resumes automatically: only the views still missing on the server are captured.
 * Tap a finished thumbnail to retake that single view (allowed until analysis starts).
 * Props: checkId, phase ('before' | 'after'), onComplete(check) when all 6 are uploaded.
 */
export default function SixPhotoCapture({ checkId, phase, onComplete }) {
  const [check, setCheck] = useState(null);
  const [captureViews, setCaptureViews] = useState(null);
  const [version, setVersion] = useState(0);
  const [error, setError] = useState('');
  const announced = useRef(false);

  const have = check ? (phase === 'before' ? check.before_views : check.after_views) : [];
  const missing = check ? (phase === 'before' ? check.missing_before : check.missing_after) : VIEWS;
  const locked = check ? check.status !== 'collecting' : false;

  const refresh = useCallback(async () => {
    try {
      setCheck(await getCheck(checkId));
      setError('');
    } catch (err) {
      setError(apiError(err, 'Could not load the photo check.'));
    }
  }, [checkId]);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    if (check && missing.length === 0 && !captureViews && !announced.current) {
      announced.current = true;
      onComplete?.(check);
    }
    if (missing.length > 0) announced.current = false;
  }, [check, missing.length, captureViews, onComplete]);

  const finishCapture = async () => {
    setCaptureViews(null);
    setVersion((v) => v + 1);
    await refresh();
  };

  if (error && !check) return <p className="dmg-error" role="alert">{error}</p>;
  if (!check) return <p className="dmg-note" role="status">Loading photo check…</p>;

  if (captureViews) {
    return (
      <GuidedCapture
        checkId={checkId}
        phase={phase}
        views={captureViews}
        onDone={finishCapture}
        onCancel={finishCapture}
      />
    );
  }

  return (
    <div className="dmg-six">
      <p className="dmg-note">{INTRO[phase]}</p>
      <p className="dmg-count" aria-live="polite">{have.length} of 6 photos uploaded</p>
      <ul className="dmg-slots">
        {VIEWS.map((view) => {
          const done = have.includes(view);
          return (
            <li key={view} className={done ? 'dmg-slot dmg-slot--done' : 'dmg-slot'}>
              {done ? (
                <button
                  type="button" className="dmg-slot-btn" disabled={locked}
                  onClick={() => setCaptureViews([view])}
                  aria-label={`Retake ${LABELS[view]} photo`}
                >
                  <AuthImage key={`${view}-${version}`} path={userPhotoPath(checkId, phase, view)} alt={`${LABELS[view]} photo`} className="dmg-thumb" />
                </button>
              ) : (
                <div className="dmg-thumb dmg-thumb--empty" aria-label={`${LABELS[view]} photo missing`}>—</div>
              )}
              <span className="dmg-slot-label">{LABELS[view]}</span>
            </li>
          );
        })}
      </ul>
      {!locked && missing.length > 0 && (
        <Button variant="primary" onClick={() => setCaptureViews(VIEWS.filter((v) => missing.includes(v)))}>
          {have.length === 0 ? 'Start photo check' : `Continue (${missing.length} left)`}
        </Button>
      )}
      {missing.length === 0 && <p className="dmg-ok">All 6 photos are uploaded.</p>}
      {locked && <p className="dmg-note">This check is already being analysed, so photos can no longer be changed.</p>}
    </div>
  );
}
