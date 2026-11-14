import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Menu, X, User, ChevronDown } from 'lucide-react';
import api from '../api/client';
import Button from './ui/Button';
import './Navbar.css';

const Navbar = () => {
  const { isAuthenticated, user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  const isActive = (path) => location.pathname === path ? 'active' : '';

  useEffect(() => {
    if (!isAuthenticated) {
      setUnreadCount(0);
      return undefined;
    }

    const refreshUnreadCount = async () => {
      try {
        const response = await api.get('/notifications/unread-count');
        setUnreadCount(response.data.unread_count);
      } catch (error) {
        console.error('Failed to load unread notification count:', error);
      }
    };
    const handleNotificationUpdate = () => refreshUnreadCount();
    refreshUnreadCount();
    const intervalId = window.setInterval(refreshUnreadCount, 30000);
    window.addEventListener('notifications:updated', handleNotificationUpdate);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('notifications:updated', handleNotificationUpdate);
    };
  }, [isAuthenticated]);

  const handleLogout = () => {
    logout();
    navigate('/');
    setUserMenuOpen(false);
  };

  const authedDropdown = (
    <>
      <Link
        to="/create-listing"
        className="dropdown-link"
        onClick={() => setUserMenuOpen(false)}
      >
        Lend an item
      </Link>
      <Link
        to="/create-request"
        className="dropdown-link"
        onClick={() => setUserMenuOpen(false)}
      >
        Request an item
      </Link>
      <Link
        to="/my-listings"
        className="dropdown-link"
        onClick={() => setUserMenuOpen(false)}
      >
        My listings
      </Link>
      <Link
        to="/my-borrow-requests"
        className="dropdown-link"
        onClick={() => setUserMenuOpen(false)}
      >
        My borrow requests
      </Link>
      <Link
        to="/messages"
        className="dropdown-link"
        onClick={() => setUserMenuOpen(false)}
      >
        Messages
      </Link>
      <Link
        to="/inbox"
        className={`dropdown-link ${unreadCount > 0 ? 'unread' : ''}`}
        onClick={() => setUserMenuOpen(false)}
      >
        Inbox
        {unreadCount > 0 && (
          <span className="dropdown-badge">{unreadCount > 99 ? '99+' : unreadCount}</span>
        )}
      </Link>
      {user?.is_admin && (
        <Link
          to="/admin/disputes"
          className="dropdown-link"
          onClick={() => setUserMenuOpen(false)}
        >
          Admin
        </Link>
      )}
      <div className="dropdown-divider" />
      <button
        className="dropdown-link dropdown-logout"
        onClick={handleLogout}
      >
        Sign out
      </button>
    </>
  );

  const toggleUserMenu = () => setUserMenuOpen(!userMenuOpen);

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      const nav = document.querySelector('.navbar');
      if (nav && !nav.contains(e.target)) {
        setUserMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Close the account dropdown and the mobile menu with Escape
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        setUserMenuOpen(false);
        setMobileMenuOpen(false);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <nav className="navbar">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <div className="wrap nav-wrap">
        <Link to="/" className="nav-logo">
          NeighborLend
        </Link>

        <div className="nav-core">
          <div className="nav-links desktop-only">
            <Link
              to="/browse"
              className={`nav-link ${isActive('/browse')}`}
              aria-label="Browse items"
              aria-current={location.pathname === '/browse' ? 'page' : undefined}
            >
              Browse
            </Link>
          </div>

          {isAuthenticated ? (
            <div className="user-area desktop-only">
              <Button
                variant="primary"
                size="sm"
                className="cta-btn"
                asChild
                onClick={() => setUserMenuOpen(false)}
              >
                <Link to="/create-listing">List something</Link>
              </Button>
              <button
                className="user-trigger"
                onClick={toggleUserMenu}
                aria-expanded={userMenuOpen}
                aria-label="Account menu"
              >
                <div className="user-avatar">
                  <User size={16} />
                </div>
                <ChevronDown size={14} className="trigger-arrow" />
              </button>
              {userMenuOpen && (
                <div className="user-dropdown">
                  {authedDropdown}
                </div>
              )}
            </div>
          ) : (
            <div className="auth-actions desktop-only">
              <Button variant="secondary" size="sm" asChild>
                <Link to="/login">Log in</Link>
              </Button>
              <Button variant="primary" size="sm" asChild>
                <Link to="/register">Sign up</Link>
              </Button>
            </div>
          )}

          <button
            className="mobile-menu-btn mobile-only"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-expanded={mobileMenuOpen}
            aria-label="Toggle menu"
          >
            {mobileMenuOpen ? <X /> : <Menu />}
          </button>
        </div>
      </div>

      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div className="mobile-menu">
          <Link
            to="/browse"
            className={`mobile-link ${isActive('/browse')}`}
            onClick={() => setMobileMenuOpen(false)}
          >
            Browse
          </Link>
          {isAuthenticated ? (
            <>
              <Link
                to="/create-listing"
                className="mobile-link"
                onClick={() => setMobileMenuOpen(false)}
              >
                List something
              </Link>
              <Link
                to="/create-request"
                className="mobile-link"
                onClick={() => setMobileMenuOpen(false)}
              >
                Request something
              </Link>
              <Link
                to="/my-listings"
                className="mobile-link"
                onClick={() => setMobileMenuOpen(false)}
              >
                My listings
              </Link>
              <Link
                to="/my-borrow-requests"
                className="mobile-link"
                onClick={() => setMobileMenuOpen(false)}
              >
                My borrow requests
              </Link>
              <Link
                to="/messages"
                className="mobile-link"
                onClick={() => setMobileMenuOpen(false)}
              >
                Messages
              </Link>
              <Link
                to="/inbox"
                className={`mobile-link ${unreadCount > 0 ? 'unread' : ''}`}
                onClick={() => setMobileMenuOpen(false)}
              >
                Inbox
                {unreadCount > 0 && (
                  <span className="mobile-badge">{unreadCount > 99 ? '99+' : unreadCount}</span>
                )}
              </Link>
              {user?.is_admin && (
                <Link
                  to="/admin/disputes"
                  className="mobile-link"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Admin
                </Link>
              )}
              <button
                className="mobile-link mobile-logout"
                onClick={() => { handleLogout(); setMobileMenuOpen(false); }}
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link
                to="/login"
                className="mobile-link"
                onClick={() => setMobileMenuOpen(false)}
              >
                Log in
              </Link>
              <Link
                to="/register"
                className="mobile-link mobile-primary"
                onClick={() => setMobileMenuOpen(false)}
              >
                Sign up
              </Link>
            </>
          )}
        </div>
      )}
    </nav>
  );
};

export default Navbar;
