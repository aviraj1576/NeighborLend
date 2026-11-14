import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Button from '../ui/Button';
import CaptureCamera from './CaptureCamera';
import { checkQuality } from './quality';
import { LABELS, apiError, uploadPhoto, usePhotoUrls, userPhotoPath } from './damageApi';

/**
 * Walks through `views` one at a time and uploads each photo (ported from the damage_check
 * module's GuidedCapture).
 *  phase "before": lender, framing box, no guide
 *  phase "after":  borrower; the lender's photo is shown faded as a guide and its shape
 *                  (aspect ratio) is copied so the two line up
 */
export default function GuidedCapture({ checkId, phase, views, aspect = 3 / 4, onDone, onCancel }) {
  const [i, setI] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [pending, setPending] = useState(null); // { blob, issues, uploadFailed? }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [ghostAspect, setGhostAspect] = useState(null);
  const [skipGhost, setSkipGhost] = useState(false);

  const view = views[i];
  const isAfter = phase === 'after';
  const pendingUrl = useMemo(() => (pending ? URL.createObjectURL(pending.blob) : null), [pending]);
  useEffect(() => () => { if (pendingUrl) URL.revokeObjectURL(pendingUrl); }, [pendingUrl]);

  const beforePath = useCallback((v) => userPhotoPath(checkId, 'before', v), [checkId]);
  const { urls } = usePhotoUrls(beforePath, isAfter ? [view] : []);
  const ghost = isAfter && !skipGhost ? urls[view] : undefined;

  useEffect(() => {
    setGhostAspect(null);
    if (!ghost) return;
    const img = new Image();
    img.onload = () => setGhostAspect(img.naturalWidth / img.naturalHeight);
    img.src = ghost;
  }, [ghost]);

  async function upload(blob) {
    setBusy(true);
    setError('');
    try {
      await uploadPhoto(checkId, phase, view, blob);
      setPending(null);
      setAttempt((a) => a + 1);
      if (i + 1 < views.length) setI(i + 1);
      else onDone();
    } catch (e) {
      setPending({ blob, issues: [], uploadFailed: true });
      setError(apiError(e, 'Upload failed.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleCapture({ blob }) {
    setError('');
    let q = { ok: true, issues: [] };
    try { q = await checkQuality(blob); } catch { /* skip the check if it fails */ }
    if (q.ok) upload(blob);
    else setPending({ blob, issues: q.issues });
  }

  const title = `${LABELS[view]} (${i + 1} of ${views.length})`;
  const waitingForGhost = isAfter && !skipGhost && (!ghost || !ghostAspect);

  return (
    <div className="dmg-step">
      <progress className="dmg-bar" max={views.length} value={i} aria-label="Progress" />
      {pending ? (
        <div className="dmg-panel">
          <h3>{LABELS[view]}</h3>
          <img className="dmg-preview" src={pendingUrl} alt="Photo you just took" />
          {pending.issues.map((m) => (<p key={m} className="dmg-warn">{m}</p>))}
          {error && <p className="dmg-error" role="alert">{error}</p>}
          <div className="dmg-row">
            <Button
              variant="secondary" disabled={busy}
              onClick={() => { setPending(null); setError(''); setAttempt((a) => a + 1); }}
            >
              Retake
            </Button>
            <Button variant="primary" disabled={busy} onClick={() => upload(pending.blob)}>
              {busy ? 'Uploading…' : pending.uploadFailed ? 'Try upload again' : 'Use anyway'}
            </Button>
          </div>
        </div>
      ) : waitingForGhost ? (
        <div className="dmg-panel" role="status">
          <h3>{LABELS[view]}</h3>
          <p>Loading the lender’s photo…</p>
          <Button variant="secondary" onClick={() => setSkipGhost(true)}>Continue without the guide</Button>
        </div>
      ) : (
        <>
          <CaptureCamera
            key={`${view}-${attempt}`}
            label={title}
            aspect={isAfter && ghostAspect ? ghostAspect : aspect}
            ghostSrc={ghost}
            frameGuide={!isAfter}
            onCapture={handleCapture}
            onCancel={onCancel}
          />
          {busy && <p className="dmg-note" role="status">Uploading…</p>}
          {error && <p className="dmg-error" role="alert">{error}</p>}
        </>
      )}
    </div>
  );
}
