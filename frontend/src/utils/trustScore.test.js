import assert from 'node:assert/strict';
import test from 'node:test';
import { formatTrustScore, normalizeTrustScore, trustStarFill } from './trustScore.js';

test('formats trust scores to one decimal star rating', () => {
  assert.equal(formatTrustScore(4.34), '4.3');
  assert.equal(formatTrustScore(4.36), '4.4');
});

test('clamps malformed and out-of-range trust values to zero through five', () => {
  assert.equal(normalizeTrustScore(-1), 0);
  assert.equal(normalizeTrustScore(8), 5);
  assert.equal(normalizeTrustScore('not-a-score'), 0);
  assert.equal(trustStarFill(2.5, 0), '100%');
  assert.equal(trustStarFill(2.5, 2), '50%');
  assert.equal(trustStarFill(2.5, 3), '0%');
});
