export const normalizeTrustScore = (value) => {
  const score = Number(value);
  return Number.isFinite(score) ? Math.max(0, Math.min(5, score)) : 0;
};

export const formatTrustScore = (value) => normalizeTrustScore(value).toFixed(1);

export const trustStarFill = (value, starIndex) => {
  const score = normalizeTrustScore(value);
  return `${Math.max(0, Math.min(1, score - starIndex)) * 100}%`;
};
