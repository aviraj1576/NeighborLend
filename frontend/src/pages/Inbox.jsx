import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Check, MailOpen } from 'lucide-react';
import api from '../api/client';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
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
      setNotifications((items) => items.map((item) =>
        item.id === notification.id ? response.data : item
      ));
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
    <div className="inbox-page section" style={{ '--h': '2' }}>
      <div className="wrap">
        <div className="inbox-header section-head--split">
          <div>
            <h2 className="t-h2">Inbox</h2>
            <p className="t-lead measure">
              {unreadCount
                ? `${unreadCount} unread notification${unreadCount === 1 ? '' : 's'}`
                : 'You are all caught up.'}
            </p>
          </div>
          {unreadCount > 0 && (
            <Button variant="secondary" onClick={markAllRead} className="inbox-read-all">
              <Check size={16} />
              <span style={{ marginLeft: 'var(--s-2)' }}>Mark all as read</span>
            </Button>
          )}
        </div>

        {error && (
          <div className="error-banner" role="alert">{error}</div>
        )}

        {loading ? (
          <div className="inbox-loading">Loading inbox…</div>
        ) : notifications.length === 0 ? (
          <Card variant="default" className="inbox-empty">
            <div className="empty-body">
              <MailOpen size={40} />
              <h3 className="t-card">No notifications yet</h3>
              <p className="t-body">Updates about borrowing requests and rentals will appear here.</p>
            </div>
          </Card>
        ) : (
          <div className="inbox-list">
            {notifications.map((notification) => (
              <article
                key={notification.id}
                className={['inbox-item', notification.is_read ? 'is-read' : 'is-unread'].join(' ')}
              >
                <span className="inbox-status" aria-label={notification.is_read ? 'Read' : 'Unread'} />
                <div className="inbox-item-content">
                  <h3 className="t-card">{notification.title}</h3>
                  <p className="t-body">{notification.message}</p>
                  <time dateTime={notification.created_at} className="t-small muted">
                    {new Date(notification.created_at).toLocaleString()}
                  </time>
                </div>
                <div className="inbox-item-actions">
                  <Button
                    variant="secondary"
                    size="sm"
                    asChild
                    onClick={() => markRead(notification)}
                  >
                    <Link to={notification.link_url}>View</Link>
                  </Button>
                  {!notification.is_read && (
                    <Button variant="secondary" size="sm" onClick={() => markRead(notification)}>
                      Mark read
                    </Button>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default Inbox;
