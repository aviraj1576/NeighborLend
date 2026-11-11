import React from 'react';

/**
 * Badge — small status / category label.
 *
 * Soft pill on a layered surface with hairline border. Variants map to the brand palette:
 * default (muted on surface), accent (gold fill, action-ink text), success, outline.
 *
 * Props: children, variant, className.
 */
export default function Badge({ children, variant = 'default', className = '' }) {
  const cls = [
    'badge',
    `badge--${variant}`,
    className,
  ].filter(Boolean).join(' ');
  return <span className={cls}>{children}</span>;
}

Badge.displayName = 'Badge';
