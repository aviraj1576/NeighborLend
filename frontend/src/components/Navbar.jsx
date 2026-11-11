import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Menu, X, User } from 'lucide-react';
import api from '../api/client';
import Button from './ui/Button';
import './Navbar.css';

const Navbar = () => {
  const { isAuthenticated, user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
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
  };

  const authedLinks = (
    <>
      <Link to="/create-listing" className={`nav-link ${isActive('/create-listing')}`}>
        Lend Item
      </Link>
      <Link to="/create-request" className={`nav-link ${isActive('/create-request')}`}>
        Request Item
      </Link>
      <Link to="/my-listings" className={`nav-link ${isActive('/my-listings')}`}>
        My Listings
      </Link>
      <Link to="/my-borrow-requests" className={`nav-link ${isActive('/my-borrow-requests')}`}>
        My Borrow Requests
      </Link>
      <Link to="/messages" className={`nav-link ${isActive('/messages')}`}>
        Messages
      </Link>
      <Link to="/inbox" className={`nav-link ${isActive('/inbox')}`}>
        Inbox
        {unreadCount > 0 && <span className="unread-badge">{unreadCount > 99 ? '99+' : unreadCount}</span>}
      </Link>
    </>
  );

  return (
    <nav className="navbar">
      <a href="#" className="skip-link visually-hidden" tabIndex={0}>
        Skip to content
      </a>
      <div className="wrap nav-wrap">
        <Link to="/" className="nav-logo">
          NeighborLend
        </Link>

        <div className="nav-links desktop-only">
          <Link to="/browse" className={`nav-link ${isActive('/browse')}`}>
            Browse
          </Link>
          {isAuthenticated ? authedLinks : null}
        </div>

        <div className="nav-actions desktop-only">
          {isAuthenticated ? (
            <div className="user-menu">
              <div className="user-avatar">
                <User size={18} />
              </div>
              <span className="user-name">{user?.username || 'User'}</span>
              <Button variant="secondary" size="sm" onClick={handleLogout} className="logout-btn">
                Logout
              </Button>
            </div>
          ) : (
            <div className="auth-buttons">
              <Link to="/login">
                <Button variant="secondary" size="sm">
                  Log in
                </Button>
              </Link>
              <Link to="/register">
                <Button variant="primary" size="sm">
                  Sign up
                </Button>
              </Link>
            </div>
          )}
        </div>

        <button
          className="mobile-menu-btn mobile-only"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-expanded={mobileMenuOpen}
          aria-label="Toggle menu"
        >
          {mobileMenuOpen ? <X /> : <Menu />}
        </button>
      </div>

      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div className="mobile-menu">
          <Link to="/browse" className={`nav-link ${isActive('/browse')}`} onClick={() => setMobileMenuOpen(false)}>
            Browse
          </Link>
          {isAuthenticated ? (
            <>
              {authedLinks}
              <div className="mobile-user">
                <span>{user?.username}</span>
                <Button variant="secondary" size="sm" onClick={() => { handleLogout(); setMobileMenuOpen(false); }} className="logout-btn">
                  Logout
                </Button>
              </div>
            </>
          ) : (
            <div className="mobile-auth">
              <Link to="/login">
                <Button variant="secondary" size="sm" onClick={() => setMobileMenuOpen(false)}>
                  Log in
                </Button>
              </Link>
              <Link to="/register">
                <Button variant="primary" size="sm" onClick={() => setMobileMenuOpen(false)}>
                  Sign up
                </Button>
              </Link>
            </div>
          )}
        </div>
      )}
    </nav>
  );
};

export default Navbar;
