import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Plus, ArrowRight, Clock, Check, X } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import './MyBorrowRequests.css';

const STATUS_LABELS = {
  open: 'Open',
  fulfilled: 'Fulfilled',
  closed: 'Closed',
  cancelled: 'Cancelled',
};

const HANDOVER_LABELS = {
  not_applicable: 'No handover yet',
  pending: 'Handover pending',
  photos_uploaded: 'Photos uploaded',
  borrower_confirmed: 'Item received',
  lender_confirmed: 'Handover confirmed',
  issue_reported: 'Issue reported',
  return_photos_uploaded: 'Return photos uploaded',
  return_confirmed: 'Returned',
};

const MyBorrowRequests = () => {
  const { user } = useAuth();
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('all'); // 'all', 'as_borrower', 'as_lender'

  useEffect(() => {
    const fetchMyRequests = async () => {
      try {
        const res = await api.get('/borrow-requests/my');
        setRequests(res.data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchMyRequests();
  }, []);

  const filteredRequests = requests.filter((r) => {
    if (activeTab === 'all') return true;
    if (activeTab === 'as_borrower') return r.borrower_id === user?.id;
    if (activeTab === 'as_lender') return r.lender_id === user?.id;
    return true;
  });

  const tabs = [
    { key: 'all', label: 'All' },
    { key: 'as_borrower', label: 'As borrower' },
    { key: 'as_lender', label: 'As lender' },
  ];

  return (
    <div className="my-borrow-requests-page app-page">
      <div className="wrap">
        <div className="page-header section-head--split">
          <div>
            <h2 className="t-h2">My borrow requests</h2>
            <p className="t-lead measure">Track rentals you&rsquo;ve requested and offers made to you.</p>
          </div>
          <div className="tab-buttons">
            {tabs.map((t) => (
              <Button
                key={t.key}
                variant="secondary"
                size="sm"
                className={`tab-btn ${activeTab === t.key ? 'active' : ''}`}
                onClick={() => setActiveTab(t.key)}
              >
                {t.label}
              </Button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="dashboard-loading">Loading your borrow requests…</div>
        ) : filteredRequests.length > 0 ? (
          <div className="request-grid">
            {filteredRequests.map((request) => (
              <Card
                key={request.id}
                variant="default"
                className="request-card"
              >
                <Link to={`/borrow-requests/${request.id}`} className="request-link">
                  <div className="request-head">
                    <div className={`status-badge status-${request.status}`}>
                      {STATUS_LABELS[request.status] || request.status}
                    </div>
                    <Badge variant="outline" className="handover-badge">
                      {HANDOVER_LABELS[request.handover_status] || 'No handover yet'}
                    </Badge>
                  </div>
                  <div className="request-body">
                    <h3 className="t-card">{request.title}</h3>
                    <span className="request-category">{request.category}</span>
                    <div className="request-price">
                      ₹{request.max_price_per_day || request.price_per_day || 0} / day
                    </div>
                  </div>
                  <div className="request-foot">
                    <div className="request-parties">
                      <span className="party-label">Borrower</span>
                      <span className="party-val">{request.borrower_name || '—'}</span>
                    </div>
                    <div className="request-parties">
                      <span className="party-label">Status</span>
                      <span className="party-val">{request.lender_id ? 'Matched' : 'Waiting'}</span>
                    </div>
                  </div>
                  <div className="request-hint">
                    <ArrowRight size={14} />
                    <span>View details</span>
                  </div>
                </Link>
              </Card>
            ))}
          </div>
        ) : (
          <Card variant="default" className="empty-card">
            <div className="empty-body">
              <Plus size={44} className="empty-icon" />
              <h3 className="t-card">No borrow requests yet</h3>
              <p className="t-body">
                Start a conversation and make an offer to create a rental request.
              </p>
              <div className="empty-actions" style={{ marginTop: 'var(--s-5)' }}>
                <Link to="/browse">
                  <Button variant="primary">Browse items</Button>
                </Link>
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
};

export default MyBorrowRequests;
