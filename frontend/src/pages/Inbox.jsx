import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Check, MailOpen } from 'lucide-react';
import api from '../api/client';
import './Inbox.css';

const Inbox = () => {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchNotifications = useCallback(async () => {
    setError('');
    try {
      const response = await api.get('/notifications');
      setNotifications(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not load your inbox.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  const markRead = async (notification) => {
    if (notification.is_read) return;
    try {
      const response = await api.patch(`/notifications/${notification.id}/read`);
      setNotifications((items) => items.map((item) => (
        item.id === notification.id ? response.data : item
      )));
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not mark this notification as read.');
    }
  };

  const markAllRead = async () => {
    try {
      await api.patch('/notifications/read-all');
      setNotifications((items) => items.map((item) => ({ ...item, is_read: true })));
      window.dispatchEvent(new Event('notifications:updated'));
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not mark notifications as read.');
    }
  };

  const unreadCount = notifications.filter((notification) => !notification.is_read).length;

  return (
    <section className="inbox-page container fade-in-up">
      <header className="inbox-header">
        <div>
          <h1 className="gradient-text">Inbox</h1>
          <p>{unreadCount ? `${unreadCount} unread notification${unreadCount === 1 ? '' : 's'}` : 'You are all caught up.'}</p>
        </div>
        {unreadCount > 0 && (
          <button type="button" className="btn-outline inbox-read-all" onClick={markAllRead}>
            <Check size={16} /> Mark all as read
          </button>
        )}
      </header>

      {error && <div className="error-banner">{error}</div>}
      {loading ? (
        <p className="inbox-empty">Loading inbox…</p>
      ) : notifications.length === 0 ? (
        <div className="inbox-empty glass">
          <MailOpen size={32} />
          <p>No notifications yet. Updates about borrowing requests and rentals will appear here.</p>
        </div>
      ) : (
        <div className="inbox-list">
          {notifications.map((notification) => (
            <article
              key={notification.id}
              className={`inbox-item glass ${notification.is_read ? 'is-read' : 'is-unread'}`}
            >
              <span className="inbox-status" aria-label={notification.is_read ? 'Read' : 'Unread'} />
              <div className="inbox-item-content">
                <h2>{notification.title}</h2>
                <p>{notification.message}</p>
                <time dateTime={notification.created_at}>
                  {new Date(notification.created_at).toLocaleString()}
                </time>
              </div>
              <div className="inbox-item-actions">
                <Link
                  to={notification.link_url}
                  className="btn-primary inbox-open-link"
                  onClick={() => markRead(notification)}
                >
                  View
                </Link>
                {!notification.is_read && (
                  <button type="button" className="inbox-mark-read" onClick={() => markRead(notification)}>
                    Mark read
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
};

export default Inbox;
