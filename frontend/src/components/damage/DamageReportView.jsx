import './Damage.css';
import React from 'react';
import Badge from '../ui/Badge';
import { LABELS } from './damageApi';

const HEADLINE = {
  possible_damage: ['Possible damage found', 'At least one view shows a likely change. Check the photos side by side.'],
  needs_review: ['Needs a closer look', 'The comparison was not conclusive. Check the photos yourself.'],
  clear: ['No visible change found', 'Nothing external stood out. Internal faults cannot be seen in photos.'],
};
const TONE = { possible_damage: 'bad', needs_review: 'warn', clear: 'ok' };
const words = (s) => String(s || 'unknown').replace(/[-_]/g, ' ');

function viewStatus(r) {
  if (r.error) return 'Could not compare';
  if (!r.comparable) return 'Not comparable';
  if (r.damage_detected) return `Change seen (${r.confidence} confidence)`;
  return 'No change seen';
}

/** The AI-assisted log from the damage_check module. A warning, never a verdict. */
export default function DamageReportView({ report, status }) {
  if (status === 'processing' || status === 'collecting') {
    return <div className="dmg-panel" role="status"><h3>Comparing photos</h3><p>This can take up to a minute.</p></div>;
  }
  if (status === 'failed') {
    return <div className="dmg-panel"><h3>The AI comparison failed</h3><p className="dmg-note">Nothing was reported as clear. Compare the photos yourself.</p></div>;
  }
  if (!report) return null;
  const [title, sub] = HEADLINE[report.overall] || HEADLINE.needs_review;
  return (
    <div className="dmg-report" data-overall={report.overall}>
      <p className="dmg-disclaimer" role="note">{report.disclaimer}</p>
      <div className="dmg-report-head">
        <Badge variant={report.overall === 'clear' ? 'success' : 'outline'} className={`dmg-tone dmg-tone--${TONE[report.overall] || 'warn'}`}>
          {words(report.overall)}
        </Badge>
        <h3>{title}</h3>
      </div>
      <p className="dmg-note">{sub}</p>
      <ul className="dmg-views">
        {report.views.map((r) => (
          <li key={r.view} className={r.damage_detected ? 'dmg-view dmg-view--bad' : 'dmg-view'}>
            <div className="dmg-view-head">
              <strong>{LABELS[r.view] || r.view}</strong>
              <span>{viewStatus(r)}</span>
            </div>
            {r.findings.length > 0 && (
              <ul className="dmg-findings">
                {r.findings.map((f, k) => (
                  <li key={k}><strong>{words(f.type)}</strong>, {words(f.location)}: {f.description}</li>
                ))}
              </ul>
            )}
            {r.note && <p className="dmg-note">{r.note}</p>}
            {r.error && <p className="dmg-note">{r.error}</p>}
          </li>
        ))}
      </ul>
      <p className="dmg-note">Model: {report.model || 'unknown'}</p>
    </div>
  );
}
