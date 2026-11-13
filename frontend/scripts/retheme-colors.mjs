// One-off migration: replace hard-coded legacy colours with palette tokens.
// Run from frontend/:  node scripts/retheme-colors.mjs
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

// Every legacy colour maps to the cream/gold token closest to it, so the look is preserved.
const MAP = {
  '#2b061e': 'var(--p-ink)', '#1f1320': 'var(--p-ink)', '#241820': 'var(--p-ink)', '#1a1218': 'var(--p-ink)',
  '#111': 'var(--p-accent-ink)', '#111111': 'var(--p-accent-ink)',
  '#4a3630': 'var(--p-ink-soft)',
  '#76575d': 'var(--p-muted)', '#8d575d': 'var(--p-muted)', '#6b4f22': 'var(--p-muted)',
  '#c9c2ba': 'var(--p-border)',
  '#8d5a28': 'var(--p-accent-text)',
  '#d2bf55': 'var(--p-accent)',
  '#f3e1cc': 'var(--p-surface)',
  '#ffeed6': 'var(--p-bg)',
  '#e8dcc8': 'var(--p-tint-soft)',
  '#fff8e7': 'var(--p-highlight)', '#fff5e6': 'var(--p-highlight)', '#fdf3ec': 'var(--p-highlight)',
  '#fdeef0': 'var(--p-highlight)', '#fbf7f0': 'var(--p-highlight)', '#f3e9d2': 'var(--p-highlight)',
  '#ffe9c4': 'var(--p-highlight)', '#ffe6d4': 'var(--p-highlight)', '#f0f7f0': 'var(--p-highlight)',
  '#fbbfca': 'var(--p-tint)',
  '#aa8e8a': 'var(--p-inv-muted)', '#381429': 'var(--p-inv-surface)',
  '#ef4444': 'var(--p-danger)', '#b3261e': 'var(--p-danger)', '#7f1d1d': 'var(--p-danger)',
  '#22c55e': 'var(--p-success)', '#15803d': 'var(--p-success)', '#14532d': 'var(--p-success)',
  '#166534': 'var(--p-success)',
};
const KEEP = new Set(['#fff', '#ffffff', '#000', '#000000']);

const list = (dir, exts) => readdirSync(dir).filter((f) => exts.some((e) => f.endsWith(e))).map((f) => join(dir, f));
const files = [
  ...list('src/components', ['.css', '.jsx']),
  ...list('src/pages', ['.css', '.jsx']),
  'src/design/global.css',
  'src/App.jsx',
];

let total = 0;
const leftovers = [];
for (const file of files) {
  const src = readFileSync(file, 'utf8');
  let n = 0;
  let out = src.replace(/var\((--[\w-]+),\s*#[0-9a-fA-F]{3,6}\)/g, (_m, name) => { n += 1; return `var(${name})`; });
  out = out.replace(/#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b/g, (m) => {
    const key = m.toLowerCase();
    if (MAP[key]) { n += 1; return MAP[key]; }
    if (!KEEP.has(key)) leftovers.push(`${file}: ${m}`);
    return m;
  });
  // gold is for fills only: a text or icon colour that is gold becomes the accessible brown
  out = out.replace(/(^|[^-\w])color:(\s*)var\(--(?:p-)?accent\)/g, (_m, pre, sp) => { n += 1; return `${pre}color:${sp}var(--p-accent-text)`; });
  if (out !== src) writeFileSync(file, out);
  total += n;
  console.log(`${String(n).padStart(4)}  ${file}`);
}
console.log(`TOTAL replacements: ${total}`);
console.log(leftovers.length ? `UNMAPPED: ${leftovers.join(', ')}` : 'UNMAPPED: none');
