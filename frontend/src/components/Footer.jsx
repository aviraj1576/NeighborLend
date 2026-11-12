import React from 'react';
import { Link } from 'react-router-dom';
import './Footer.css';

/**
 * Footer — closing band (skill footer-statement).
 *
 * Inverse ground (ink #2B061E), cream text, one action, district-only address,
 * .example contact, and a single footer credit line.
 *
 * Props: none (keeps the same shape so any page can drop it in).
 */
export default function Footer() {
  return (
    <footer className="footer closing ground-inverse">
      <div className="wrap">
        <div className="footer-grid">
          <div className="footer-brand">
            <div className="footer-logo">NeighborLend</div>
            <p className="footer-lead">
              Borrow and lend from neighbors nearby. Warm, human-led lending with
              fair rates and no fees.
            </p>
          </div>

          <div className="footer-links">
            <div className="footer-link-group">
              <h3 className="footer-group-title">Explore</h3>
              <ul>
                <li><Link to="/browse">Browse items</Link></li>
                <li><Link to="/create-listing">List an item</Link></li>
                <li><Link to="/create-request">Request an item</Link></li>
              </ul>
            </div>
            <div className="footer-link-group">
              <h3 className="footer-group-title">Account</h3>
              <ul>
                <li><Link to="/my-listings">My listings</Link></li>
                <li><Link to="/my-borrow-requests">My borrow requests</Link></li>
                <li><Link to="/messages">Messages</Link></li>
              </ul>
            </div>
            <div className="footer-link-group">
              <h3 className="footer-group-title">Help</h3>
              <ul>
                <li><Link to="/">How it works</Link></li>
                <li><Link to="/">Safety centre</Link></li>
                <li><Link to="/">Terms of service</Link></li>
                <li><Link to="/">Privacy policy</Link></li>
              </ul>
            </div>
          </div>

          <div className="footer-contact">
            <h3 className="footer-group-title">NeighborHood HQ</h3>
            <p className="footer-address">
              Connaught Place district, Delhi • India
            </p>
            <p className="footer-contact-line">
              contact@example • support@example
            </p>
            <div className="footer-actions" style={{ marginTop: 'auto' }}>
              <Link to="/register">
                <button className="btn btn--primary btn--sm">Get started</button>
              </Link>
            </div>
          </div>
        </div>

        <hr className="footer-rule" />

        <p className="footer-credit">
          Photographs and art supplied by the client; stand-in frames are listed in the
          design report. &copy; 2026 NeighborLend — illustrative demo.
        </p>
      </div>
    </footer>
  );
}
