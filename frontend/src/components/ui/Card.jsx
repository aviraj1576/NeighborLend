import React from 'react';

/**
 * Card — shared surface primitive.
 *
 * Built on the skill's one card style: .card (+ .card--open / .card--plan) with an optional
 * inset .panel for a photograph or UI fragment. Hairline border, layered surface, soft
 * radius, 2px lift on hover (motion layer). Keeps children, onClick, variant and className.
 *
 * Props: children, onClick, variant ('default'|'open'|'plan'), className, padded.
 */
export default function Card({
  children,
  onClick,
  variant = 'default',
  className = '',
  padded = true,
}) {
  const cls = [
    'card',
    variant === 'open' ? 'card--open' : variant === 'plan' ? 'card--plan' : '',
    !padded ? 'card--unpadded' : '',
    className,
  ].filter(Boolean).join(' ');

  const onClickHandler = onClick
    ? {
        onClick,
        onKeyDown: (e) => {
          if (e.target !== e.currentTarget) return;
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onClick(e);
          }
        },
        role: 'button',
        tabIndex: 0,
        style: { cursor: 'pointer' },
      }
    : {};

  return (
    <div className={cls} {...onClickHandler}>
      {children}
    </div>
  );
}

Card.displayName = 'Card';
