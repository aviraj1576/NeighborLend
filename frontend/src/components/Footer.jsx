import React from 'react';
import { Link } from 'react-router-dom';
import './Footer.css';

/**
 * Footer — closing band (skill footer-statement).
 *
 * Inverse ground (ink var(--p-ink)), cream text, one action, district-only address,
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
          </div>

          <div className="footer-contact">
            <h3 className="footer-group-title">Where we are</h3>
            <p className="footer-address">
              Connaught Place district, Delhi • India
            </p>
            <div className="footer-actions" style={{ marginTop: 'auto' }}>
              <Link to="/register" className="btn btn--primary btn--sm">Get started</Link>
            </div>
          </div>
        </div>

        <hr className="footer-rule" />

        <p className="footer-credit">
          &copy; 2026 NeighborLend. Borrow and lend with neighbors nearby.
        </p>
      </div>
    </footer>
  );
}
