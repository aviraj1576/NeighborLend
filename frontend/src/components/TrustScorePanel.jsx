import React, { useEffect, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import api from '../api/client';
import { formatTrustScore, normalizeTrustScore } from '../utils/trustScore.js';
import './TrustScorePanel.css';

export default function TrustScorePanel({ userId, compact = false, showIdentity = false, initialTrust = null }) {
  const [trust, setTrust] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    setTrust(null);
    setError('');
    if (!userId) return undefined;
    if (initialTrust) {
      setTrust({
        ...initialTrust,
        user_id: initialTrust.id || userId,
        score: initialTrust.score ?? initialTrust.trust_score,
        rating_score: initialTrust.rating_score ?? initialTrust.trust_rating_component,
        reliability_score: initialTrust.reliability_score ?? initialTrust.trust_reliability_component,
        experience_score: initialTrust.experience_score ?? initialTrust.trust_experience_component,
        verification_score: initialTrust.verification_score ?? initialTrust.trust_verification_component,
        average_rating: initialTrust.average_rating ?? initialTrust.rating,
        rating_count: initialTrust.rating_count ?? 0,
        completed_transactions: initialTrust.completed_transactions ?? initialTrust.completed_rentals_count ?? 0,
        last_updated: initialTrust.last_updated ?? initialTrust.trust_score_updated_at,
      });
      setError('');
      return undefined;
    }
    let active = true;
    api.get(userId === 'me' ? '/trust/me' : `/trust/${encodeURIComponent(userId)}`)
      .then(({ data }) => { if (active) setTrust(data); })
      .catch((err) => { if (active) setError(err.response?.data?.detail || 'Trust score is unavailable.'); });
    return () => { active = false; };
  }, [userId, initialTrust]);

  if (error) return <p className="trust-score-error" role="status">{error}</p>;
  if (!trust) return <div className="trust-score-loading" aria-label="Loading trust score" />;
  const score = formatTrustScore(trust.score);
  const normalizedScore = normalizeTrustScore(trust.score);
  return <section className={`trust-score-panel ${compact ? 'trust-score-compact' : ''}`} aria-label="Trust score">
    {showIdentity && <div className="trust-profile-identity">
      {trust.avatar_url ? <img src={trust.avatar_url} alt="" /> : <div className="trust-avatar-fallback">{(trust.username || 'N')[0].toUpperCase()}</div>}
      <div><h2>{trust.name}</h2><p>@{trust.username} · Neighbor since {trust.member_since ? new Date(trust.member_since).getFullYear() : '—'}</p></div>
    </div>}
    <div className="trust-score-topline">
      <div><span className="trust-score-label"><ShieldCheck size={16} /> NeighborLend Trust Score</span><div className="trust-score-number">{score}<span>/5</span></div></div>
      <div className="trust-stars" role="img" aria-label={`${score} out of 5 stars`}>
        {Array.from({ length: 5 }, (_, index) => {
          const fill = Math.max(0, Math.min(1, normalizedScore - index)) * 100;
          return <span key={index} className="trust-star" style={{ '--trust-fill': `${fill}%` }}>★</span>;
        })}
      </div>
    </div>
  </section>;
}
