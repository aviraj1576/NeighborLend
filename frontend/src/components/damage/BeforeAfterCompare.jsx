import './Damage.css';
import React, { useMemo, useState } from 'react';
import { LABELS, VIEWS, usePhotoUrls } from './damageApi';

// "top-left" -> [row, col] on the 3x3 grid the model reports locations in.
function cell(loc) {
  if (loc === 'center') return [1, 1];
  const [r, c] = String(loc).split('-');
  const row = { top: 0, middle: 1, bottom: 2 }[r];
  const col = { left: 0, center: 1, right: 2 }[c];
  return row === undefined || col === undefined ? null : [row, col];
}

/**
 * Drag-to-reveal before/after slider with one tab per view (ported from the damage_check
 * module's BeforeAfterSlider). `pathFor(phase, view)` returns the API path of one photo, so the
 * same component works for participants (/damage-checks/...) and admins (/admin/disputes/...).
 * Props: pathFor, views (defaults to all 6), report (optional, draws the AI's approximate area).
 */
export default function BeforeAfterCompare({ pathFor, views = VIEWS, report }) {
  const [active, setActive] = useState(views[0]);
  const [pos, setPos] = useState(50);
  const [showArea, setShowArea] = useState(true);

  const beforePath = useMemo(() => (v) => pathFor('before', v), [pathFor]);
  const afterPath = useMemo(() => (v) => pathFor('after', v), [pathFor]);
  const { urls: before } = usePhotoUrls(beforePath, [active]);
  const { urls: after } = usePhotoUrls(afterPath, [active]);

  const result = report?.views?.find((v) => v.view === active);
  const cells = (result?.findings || []).map((f) => cell(f.location)).filter(Boolean);

  return (
    <div className="dmg-compare">
      <div className="dmg-tabs" role="tablist" aria-label="Choose a view">
        {views.map((v) => {
          const flagged = report?.views?.find((r) => r.view === v)?.damage_detected;
          return (
            <button
              key={v} type="button" role="tab" aria-selected={active === v}
              className={active === v ? 'dmg-tab dmg-tab--on' : 'dmg-tab'}
              onClick={() => setActive(v)}
            >
              {LABELS[v]}{flagged ? ' •' : ''}
            </button>
          );
        })}
      </div>
      {!before[active] || !after[active] ? (
        <p className="dmg-note" role="status">Loading photos…</p>
      ) : (
        <>
          <div className="dmg-ba-frame">
            <img src={after[active]} alt={`${LABELS[active]}, after`} />
            <img
              className="dmg-ba-top" src={before[active]} alt={`${LABELS[active]}, before`}
              style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}
            />
            <span className="dmg-ba-tag dmg-ba-tag--left">Before</span>
            <span className="dmg-ba-tag dmg-ba-tag--right">After</span>
            <div className="dmg-ba-divider" style={{ left: `${pos}%` }} aria-hidden="true" />
            {showArea && cells.map(([r, c], k) => (
              <div key={k} className="dmg-ba-area" style={{ left: `${(c * 100) / 3}%`, top: `${(r * 100) / 3}%` }} aria-hidden="true" />
            ))}
          </div>
          <input
            type="range" min="0" max="100" value={pos}
            aria-label="Compare before and after" onChange={(e) => setPos(Number(e.target.value))}
          />
          {cells.length > 0 && (
            <label className="dmg-check">
              <input type="checkbox" checked={showArea} onChange={(e) => setShowArea(e.target.checked)} />
              Show the approximate area the AI flagged
            </label>
          )}
        </>
      )}
    </div>
  );
}
