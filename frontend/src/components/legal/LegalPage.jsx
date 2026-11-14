import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import SupportChatButton from '../SupportChatButton';
import './Legal.css';

// Set VITE_CONTACT_EMAIL in the Vercel project (and .env) to show a public contact address.
export const CONTACT_EMAIL = (import.meta.env?.VITE_CONTACT_EMAIL || '').trim();

/**
 * Shared layout for the Privacy Policy and Terms of Service.
 * Props: eyebrow, title, lead, updated, sections [{ id, title, body }], other { to, label }.
 * `body` is JSX (paragraphs, lists, <Note>). Sections are numbered by CSS.
 */
export default function LegalPage({ eyebrow = 'Legal', title, lead, updated, sections, other }) {
  const { isAuthenticated } = useAuth();
  const [active, setActive] = useState(sections[0]?.id);

  useEffect(() => {
    const previous = document.title;
    document.title = `${title} · NeighborLend`;
    return () => { document.title = previous; };
  }, [title]);

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return undefined;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: '-20% 0px -65% 0px' },
    );
    sections.forEach((s) => {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [sections]);

  const toc = (
    <ol className="legal-toc-list">
      {sections.map((s) => (
        <li key={s.id}>
          <a href={`#${s.id}`} className={active === s.id ? 'is-active' : ''} aria-current={active === s.id ? 'location' : undefined}>
            {s.title}
          </a>
        </li>
      ))}
    </ol>
  );

  return (
    <div className="legal-page app-page">
      <div className="wrap">
        <header className="legal-head">
          <p className="legal-eyebrow">{eyebrow}</p>
          <h1 className="t-h1">{title}</h1>
          <p className="t-lead measure">{lead}</p>
          <p className="legal-updated">Last updated {updated}</p>
        </header>

        <div className="legal-body">
          <nav className="legal-toc" aria-label="On this page">
            <p className="legal-toc-title">On this page</p>
            {toc}
          </nav>

          <details className="legal-toc-mobile">
            <summary>On this page</summary>
            {toc}
          </details>

          <article className="legal-content">
            {sections.map((s) => (
              <section key={s.id} id={s.id} className="legal-section">
                <h2 className="legal-h2">{s.title}</h2>
                {s.body}
              </section>
            ))}

            <aside className="legal-contact" aria-labelledby="legal-contact-title">
              <h2 id="legal-contact-title" className="legal-h2 legal-h2--plain">Questions about this page</h2>
              <p>
                {CONTACT_EMAIL ? (
                  <>Write to <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.</>
                ) : (
                  <>Use the chat option in the app and say what you need.</>
                )}{' '}
                If you have an account you can also chat with us from any page that shows a &ldquo;Chat with us&rdquo; button.
              </p>
              <div className="legal-contact-actions">
                {isAuthenticated && <SupportChatButton step="legal" label="Chat with us" />}
                <Link className="legal-other" to={other.to}>{other.label}</Link>
              </div>
            </aside>
          </article>
        </div>
      </div>
    </div>
  );
}

/** A highlighted aside inside a section. */
export const Note = ({ children }) => <p className="legal-note">{children}</p>;
