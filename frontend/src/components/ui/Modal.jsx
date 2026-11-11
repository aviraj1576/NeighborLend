import React, { useEffect } from 'react';

/**
 * Modal — shared overlay dialog.
 *
 * Renders a backdrop + a surface panel using the skill's tokens (hairline border, soft
 * radius, inverse surface). Focus management is minimal: escape closes; focus-visible ring
 * comes from system.css. Keeps isOpen, onClose, children and title.
 *
 * Props: isOpen, onClose, children, title, className.
 */
export default function Modal({ isOpen, onClose, children, title, className = '' }) {
  if (!isOpen) return null;

  useEffect(() => {
    const onEsc = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onEsc);
    return () => document.removeEventListener('keydown', onEsc);
  }, [onClose]);

  const stop = (e) => e.stopPropagation();

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className={['modal', className].filter(Boolean).join(' ')}
        onClick={stop}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? 'modal-title' : undefined}
      >
        {title && (
          <h2 id="modal-title" className="modal-title">
            {title}
          </h2>
        )}
        <button className="btn btn--secondary btn--sm" onClick={onClose} aria-label="Close">
          Close
        </button>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

Modal.displayName = 'Modal';
