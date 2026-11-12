import React from 'react';

/**
 * Button — shared action primitive.
 *
 * Built on the taste-skill motion layer: .btn + .btn--primary / .btn--secondary give the
 * stepped hover, press-on-click and colour move; data-buttons="tonal" (set on <html>) makes
 * the secondary a tinted flat button (Linear / Vercel feel).
 *
 * Rendering:
 * - `href`  → renders an <a href> (keeps onClick/children interface)
 * - `asChild` → clones the single child element (e.g. react-router <Link>) and merges the
 *   button classes/behaviour onto it
 * - otherwise → renders a <button type="button">
 *
 * Props: children, onClick, type, disabled, variant ('primary'|'secondary'),
 * size ('md'|'sm'), href, asChild, className, loading.
 */
export default function Button({
  children,
  onClick,
  type = 'button',
  disabled = false,
  variant = 'primary',
  size = 'md',
  href,
  asChild = false,
  className = '',
  loading = false,
}) {
  const btnCls = [
    'btn',
    variant === 'primary' ? 'btn--primary' : 'btn--secondary',
    size === 'sm' ? 'btn--sm' : '',
    disabled ? 'btn--disabled' : '',
    className,
  ].filter(Boolean).join(' ');

  const style = loading ? { opacity: 0.7, pointerEvents: 'none' } : undefined;
  const common = {
    className: btnCls,
    style,
    'aria-busy': loading || undefined,
    onClick: disabled ? undefined : onClick,
  };

  if (href) {
    return <a href={href} {...common}>{children}</a>;
  }

  if (asChild && React.isValidElement(children)) {
    return React.cloneElement(children, {
      ...common,
      // the child (e.g. <Link>) owns its own onClick; compose both
      onClick: (e) => {
        if (children.props.onClick) children.props.onClick(e);
        if (onClick) onClick(e);
      },
      className: [children.props.className, btnCls].filter(Boolean).join(' '),
      style: { ...children.props.style, ...style },
    });
  }

  return <button type={type} disabled={disabled} {...common}>{children}</button>;
}

Button.displayName = 'Button';
