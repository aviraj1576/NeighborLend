import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  MessageSquare, Send, ArrowLeft, Check, X, RefreshCw,
  Calendar, Shield, Tag, ChevronDown, ChevronUp, AlertCircle,
  ExternalLink, Search, Clock, Sparkles
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import Input from '../components/ui/Input';
import './Chat.css';

const formatTimestamp = (dateStr) => {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  if (isToday) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
};

const formatDate = (dateStr) => {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
};

const Chat = () => {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [conversations, setConversations] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loadingConversations, setLoadingConversations] = useState(true);

  const [activeConv, setActiveConv] = useState(null);
  const [messages, setMessages] = useState([]);
  const [offers, setOffers] = useState([]);
  const [loadingActive, setLoadingActive] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const [newMessage, setNewMessage] = useState('');
  const [sendingMessage, setSendingMessage] = useState(false);

  const [showNegotiation, setShowNegotiation] = useState(true);
  const [showHistory, setShowHistory] = useState(false);
  const [negotiationMode, setNegotiationMode] = useState(null);
  const [counterTargetOffer, setCounterTargetOffer] = useState(null);

  const [formDailyPrice, setFormDailyPrice] = useState('');
  const [formStartDate, setFormStartDate] = useState('');
  const [formEndDate, setFormEndDate] = useState('');
  const [formNote, setFormNote] = useState('');
  const [offerSubmitting, setOfferSubmitting] = useState(false);
  const [offerError, setOfferError] = useState('');
  const [lenderListings, setLenderListings] = useState([]);
  const [formListingId, setFormListingId] = useState('');

  const messagesEndRef = useRef(null);
  const conversationsRequestRef = useRef(null);
  const activeConversationRequestRef = useRef(null);
  const loadedConversationIdRef = useRef(null);
  const currentConversationIdRef = useRef(conversationId);
  currentConversationIdRef.current = conversationId;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const fetchConversations = (silent = false) => {
    if (conversationsRequestRef.current) return conversationsRequestRef.current;
    if (!silent) setLoadingConversations(true);
    const request = api.get('/conversations')
      .then((res) => setConversations((previous) => (
        JSON.stringify(previous) === JSON.stringify(res.data) ? previous : res.data
      )))
      .catch((err) => console.error('Failed to load conversations:', err))
      .finally(() => {
        if (conversationsRequestRef.current === request) conversationsRequestRef.current = null;
        if (!silent) setLoadingConversations(false);
      });
    conversationsRequestRef.current = request;
    return request;
  };

  useEffect(() => {
    fetchConversations();
  }, []);

  useEffect(() => {
    if (!activeConv?.lender?.id) return;
    api.get('/listings/search?radius_km=500')
      .then((res) => setLenderListings(res.data.filter((item) => item.owner_id === activeConv.lender.id)))
      .catch((err) => console.error('Failed to load lender listings:', err));
  }, [activeConv?.lender?.id]);

  const fetchActiveConversation = (convId, silent = false) => {
    if (!convId) return Promise.resolve();
    if (activeConversationRequestRef.current?.id === convId) {
      return activeConversationRequestRef.current.promise;
    }
    const showInitialSpinner = !silent && loadedConversationIdRef.current !== convId;
    if (showInitialSpinner) setLoadingActive(true);
    setErrorMsg('');

    const request = api.get(`/conversations/${convId}`)
      .then((res) => {
        if (currentConversationIdRef.current !== convId) return;
        loadedConversationIdRef.current = convId;
        setActiveConv((previous) => (
          JSON.stringify(previous) === JSON.stringify(res.data) ? previous : res.data
        ));
        setMessages((previous) => {
          const next = res.data.messages || [];
          return JSON.stringify(previous) === JSON.stringify(next) ? previous : next;
        });
        setOffers((previous) => {
          const next = res.data.offers || [];
          return JSON.stringify(previous) === JSON.stringify(next) ? previous : next;
        });
      })
      .catch((err) => {
        console.error('Failed to fetch conversation details:', err);
        if (currentConversationIdRef.current === convId) {
          setErrorMsg('Could not load conversation. It may not exist or you lack access.');
        }
      })
      .finally(() => {
        if (activeConversationRequestRef.current?.promise === request) {
          activeConversationRequestRef.current = null;
        }
        if (showInitialSpinner && currentConversationIdRef.current === convId) {
          setLoadingActive(false);
        }
      });
    activeConversationRequestRef.current = { id: convId, promise: request };
    return request;
  };

  useEffect(() => {
    if (conversationId) fetchActiveConversation(conversationId);
  }, [conversationId]);

  useEffect(() => {
    if (!conversationId && conversations.length > 0) {
      navigate(`/messages/${conversations[0].id}`, { replace: true });
    }
  }, [conversationId, conversations, navigate]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (!conversationId) return;
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') fetchActiveConversation(conversationId, true);
    };
    const interval = window.setInterval(refreshWhenVisible, 5000);
    window.addEventListener('focus', refreshWhenVisible);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener('focus', refreshWhenVisible);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [conversationId]);

  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    if (!newMessage.trim() || sendingMessage || !activeConv) return;

    const content = newMessage.trim();
    setNewMessage('');
    setSendingMessage(true);

    const tempId = 'temp-' + Date.now();
    const optimisticMsg = {
      id: tempId,
      conversation_id: activeConv.id,
      sender_id: user?.id,
      sender_name: user?.name,
      sender_username: user?.username,
      content,
      is_system: false,
      created_at: new Date().toISOString()
    };
    setMessages((prev) => [...prev, optimisticMsg]);

    try {
      const res = await api.post(`/conversations/${activeConv.id}/messages`, { content });
      setMessages((prev) => prev.map((m) => (m.id === tempId ? res.data : m)));
      fetchConversations(true);
    } catch (err) {
      console.error('Failed to send message:', err);
      setMessages((prev) => prev.filter((m) => m.id !== tempId));
    } finally {
      setSendingMessage(false);
    }
  };

  const getOfferCalculations = () => {
    const price = parseFloat(formDailyPrice);
    if (isNaN(price) || price <= 0 || !formStartDate || !formEndDate) {
      return { days: 0, total: 0, isValid: false };
    }
    const s = new Date(formStartDate);
    const e = new Date(formEndDate);
    if (e < s) return { days: 0, total: 0, isValid: false, error: 'End date cannot be earlier than start date' };

    const diffTime = e.getTime() - s.getTime();
    let days = Math.round(diffTime / (1000 * 3600 * 24));
    if (days === 0) days = 1;
    const total = Math.round(days * price * 100) / 100;
    return { days, total, isValid: true };
  };

  const startMakeOffer = () => {
    setNegotiationMode('make');
    setCounterTargetOffer(null);
    setOfferError('');
    const today = new Date().toISOString().split('T')[0];
    const defaultEnd = new Date(Date.now() + 86400000 * 2).toISOString().split('T')[0];
    setFormStartDate(today);
    setFormEndDate(defaultEnd);
    setFormListingId(lenderListings[0]?.id || '');
    setFormDailyPrice(lenderListings[0]?.price_per_day || '');
    setFormNote('');
  };

  const startCounterOffer = (targetOffer) => {
    setNegotiationMode('counter');
    setCounterTargetOffer(targetOffer);
    setOfferError('');
    setFormListingId(targetOffer.listing_id || '');
    setFormDailyPrice(targetOffer.daily_price || '');
    setFormStartDate(targetOffer.start_date.split('T')[0]);
    setFormEndDate(targetOffer.end_date.split('T')[0]);
    setFormNote('');
  };

  const handleSubmitOffer = async (e) => {
    e.preventDefault();
    setOfferError('');
    const calcs = getOfferCalculations();
    if (!calcs.isValid) {
      setOfferError(calcs.error || 'Please fill in a valid daily price and date range.');
      return;
    }

    const price = parseFloat(formDailyPrice);
    const selectedListing = lenderListings.find((item) => item.id === formListingId);
    if (!formListingId) {
      setOfferError('The lender has no available listings for an offer.');
      return;
    }
    if (selectedListing?.min_price_per_day && price < selectedListing.min_price_per_day) {
      setOfferError(`Minimum price per day is ₹${selectedListing.min_price_per_day}`);
      return;
    }

    setOfferSubmitting(true);
    try {
      const payload = {
        listing_id: formListingId,
        daily_price: price,
        start_date: new Date(formStartDate).toISOString(),
        end_date: new Date(formEndDate).toISOString(),
        message: formNote.trim() || undefined
      };

      if (negotiationMode === 'counter' && counterTargetOffer) {
        await api.post(`/offers/${counterTargetOffer.id}/counter`, payload);
      } else {
        await api.post(`/conversations/${activeConv.id}/offers`, payload);
      }

      setNegotiationMode(null);
      setCounterTargetOffer(null);
      await fetchActiveConversation(activeConv.id, true);
      fetchConversations(true);
    } catch (err) {
      console.error('Failed to submit offer:', err);
      const detail = err.response?.data?.detail;
      setOfferError(typeof detail === 'string' ? detail : 'Failed to submit offer. Please try again.');
    } finally {
      setOfferSubmitting(false);
    }
  };

  const handleAcceptOffer = async (offerId) => {
    if (!window.confirm('Accept this rental offer? This will initiate the borrow booking request.')) return;
    try {
      const response = await api.post(`/offers/${offerId}/accept`);
      const borrowRequestId = response.data?.borrow_request_id;
      await fetchActiveConversation(activeConv.id, true);
      fetchConversations(true);
      if (borrowRequestId) {
        navigate(`/borrow-requests/${borrowRequestId}`);
      }
    } catch (err) {
      console.error('Failed to accept offer:', err);
      alert(err.response?.data?.detail || 'Failed to accept offer.');
    }
  };

  const handleRejectOffer = async (offerId) => {
    if (!window.confirm('Are you sure you want to decline this offer?')) return;
    try {
      await api.post(`/offers/${offerId}/reject`);
      await fetchActiveConversation(activeConv.id, true);
      fetchConversations(true);
    } catch (err) {
      console.error('Failed to reject offer:', err);
      alert(err.response?.data?.detail || 'Failed to reject offer.');
    }
  };

  const filteredConversations = conversations.filter((c) => {
    const term = searchQuery.toLowerCase();
    const oName = (c.other_participant?.name || '').toLowerCase();
    const uName = (c.other_participant?.username || '').toLowerCase();
    return oName.includes(term) || uName.includes(term);
  });

  const latestOffer = activeConv?.active_offer || (offers.length > 0 ? offers[offers.length - 1] : null);
  const isOfferRecipient = latestOffer && user && latestOffer.sender_id !== user.id;

  return (
    <div className="chat-page app-page">
      <div className="wrap">
        <aside className={`conversations-sidebar ${conversationId ? 'hidden-mobile' : ''}`}>
          <div className="conversations-header">
            <div className="conversations-title-row">
              <h2 className="conversations-title">
                <MessageSquare size={22} className="text-accent" />
                Messages
              </h2>
              <span className="conversations-count-badge">{conversations.length}</span>
            </div>
            <div className="conversations-search">
              <Search size={16} className="search-icon" />
              <Input
                id="conv-search"
                label="Search conversations"
                type="text"
                placeholder="Search conversations…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          </div>

          <div className="conversations-list">
            {loadingConversations ? (
              <div className="sidebar-loading-state">
                <RefreshCw className="animate-spin text-accent" size={24} />
                <p>Loading messages…</p>
              </div>
            ) : filteredConversations.length === 0 ? (
              <div className="sidebar-empty-state">
                <MessageSquare size={36} className="text-muted" />
                <p>No conversations found.</p>
                <Link to="/browse">
                  <Button variant="secondary" size="sm">Browse items</Button>
                </Link>
              </div>
            ) : (
              filteredConversations.map((conv) => {
                const isActive = conv.id === conversationId;
                const other = conv.other_participant;
                const actOffer = conv.active_offer;

                return (
                  <div
                    key={conv.id}
                    className={`conversation-item ${isActive ? 'active' : ''}`}
                    onClick={() => navigate(`/messages/${conv.id}`)}
                  >
                    <div className="item-thumb-wrapper">
                      <div className="item-thumbnail-placeholder"><MessageSquare size={20} /></div>
                      <div className="avatar-badge-small" title={other.name}>
                        {(other.name || 'U')[0].toUpperCase()}
                      </div>
                    </div>

                    <div className="conversation-content">
                      <div className="conversation-top-row">
                        <span className="listing-name" title={other.name}>
                          {other.name}
                        </span>
                        <span className="timestamp-text">
                          {formatTimestamp(conv.last_message?.created_at || conv.updated_at)}
                        </span>
                      </div>

                      <div className="participant-sub">
                        <span>{other.name}</span>
                        {other.trust_score && (
                          <span className="trust-badge-mini" title={`Trust Score: ${other.trust_score}`}>
                            <Shield size={12} /> {Math.round(other.trust_score)}
                          </span>
                        )}
                      </div>

                      <div className="conversation-bottom-row">
                        <span className="last-message-preview">
                          {conv.last_message ? (
                            conv.last_message.is_system ? (
                              <em>{conv.last_message.content}</em>
                            ) : (
                              conv.last_message.content
                            )
                          ) : (
                            'No messages yet'
                          )}
                        </span>

                        {actOffer && actOffer.status === 'pending' && (
                          <span className="offer-pill-badge offer-pill-pending">
                            Offer ₹{actOffer.daily_price}
                          </span>
                        )}
                        {actOffer && actOffer.status === 'accepted' && (
                          <span className="offer-pill-badge offer-pill-accepted">
                            Accepted
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </aside>

        {conversationId ? (
          <section className={`chat-window ${!conversationId ? 'hidden-mobile' : ''}`}>
            <header className="chat-header">
              <div className="chat-header-left">
                <button
                  className="mobile-back-btn"
                  onClick={() => navigate('/messages')}
                  title="Back to conversations"
                >
                  <ArrowLeft size={20} />
                </button>

                {activeConv && (
                  <div className="chat-listing-info">
                    <div className="chat-listing-thumb item-thumbnail-placeholder"><MessageSquare size={18} /></div>
                    <div className="chat-listing-meta">
                      <h3 className="chat-listing-title">
                        {activeConv.is_borrower ? activeConv.lender.name : activeConv.borrower.name}
                      </h3>
                      <div className="chat-listing-pricing">
                        <span>Conversation</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="chat-header-right">
                <button
                  className={`toggle-negotiation-btn ${showNegotiation ? 'active' : ''}`}
                  onClick={() => setShowNegotiation(!showNegotiation)}
                >
                  <Tag size={16} />
                  <span>Negotiation</span>
                </button>
              </div>
            </header>

            <div className="messages-container">
              {loadingActive ? (
                <div className="messages-empty-state">
                  <RefreshCw className="animate-spin text-accent" size={28} />
                  <p>Loading messages…</p>
                </div>
              ) : errorMsg ? (
                <div className="messages-empty-state text-danger">
                  <AlertCircle size={32} />
                  <p>{errorMsg}</p>
                </div>
              ) : messages.length === 0 ? (
                <div className="messages-empty-state">
                  <Sparkles size={36} className="text-accent" />
                  <h4 className="t-card">Start the conversation</h4>
                  <p>Ask about item condition, delivery pickup, or make a rental price offer.</p>
                </div>
              ) : (
                messages.map((msg) => {
                  const isMe = user && msg.sender_id === user.id;

                  if (msg.is_system) {
                    return (
                      <div key={msg.id} className="message-bubble-wrapper system">
                        <div className="system-bubble">
                          <span>{msg.content}</span>
                        </div>
                      </div>
                    );
                  }

                  return (
                    <div
                      key={msg.id}
                      className={`message-bubble-wrapper ${isMe ? 'outgoing' : 'incoming'}`}
                    >
                      {!isMe && (
                        <span className="message-sender-name">
                          {msg.sender_name || msg.sender_username}
                        </span>
                      )}
                      <div className="message-bubble">
                        <p>{msg.content}</p>
                        <span className="message-timestamp">
                          {formatTimestamp(msg.created_at)}
                        </span>
                      </div>
                    </div>
                  );
                })
              )}
              <div ref={messagesEndRef} />
            </div>

            <form className="chat-input-bar" onSubmit={handleSendMessage}>
              <div className="chat-input-wrapper">
                <Input
                  id="chat-input"
                  label="Message"
                  type="textarea"
                  rows="1"
                  placeholder="Type a message… (Press Enter to send)"
                  value={newMessage}
                  onChange={(e) => setNewMessage(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSendMessage();
                    }
                  }}
                />
              </div>
              <button
                type="submit"
                className="chat-send-btn"
                disabled={!newMessage.trim() || sendingMessage}
                title="Send Message"
              >
                <Send size={18} />
              </button>
            </form>
          </section>
        ) : (
          <section className="chat-window no-conversation-selected hidden-mobile">
            <MessageSquare size={60} className="text-muted" />
            <h3 className="t-card">Select a conversation</h3>
            <p>Choose a chat from the sidebar or browse items to start negotiating.</p>
            <Link to="/browse">
              <Button variant="primary">Browse marketplace</Button>
            </Link>
          </section>
        )}

        {conversationId && activeConv && showNegotiation && (
          <aside className="negotiation-panel">
            <div className="negotiation-header">
              <h3 className="negotiation-title">
                <Tag size={20} className="text-accent" />
                Rental negotiation
              </h3>
              <button
                className="negotiation-close-btn"
                onClick={() => setShowNegotiation(false)}
              >
                <X size={18} />
              </button>
            </div>

            <div className="negotiation-body">
              {latestOffer ? (
                <div className="active-offer-card">
                  <div className="offer-card-top">
                    <span className="offer-label">Current offer</span>
                    <span className={`offer-status-tag status-${latestOffer.status}`}>
                      {latestOffer.status}
                    </span>
                  </div>

                  <div className="offer-price-highlight">
                    <span className="offer-rate-large">₹{latestOffer.daily_price}</span>
                    <span className="offer-unit">/ day</span>
                  </div>

                  <div className="offer-details-grid">
                    <div className="offer-detail-item">
                      <span className="detail-label">Rental period</span>
                      <span className="detail-val">
                        {formatDate(latestOffer.start_date)} - {formatDate(latestOffer.end_date)}
                      </span>
                    </div>
                    <div className="offer-detail-item">
                      <span className="detail-label">Total cost</span>
                      <span className="detail-val text-accent">₹{latestOffer.total_cost}</span>
                    </div>
                    <div className="offer-detail-item">
                      <span className="detail-label">Proposed by</span>
                      <span className="detail-val">
                        {user && latestOffer.sender_id === user.id ? 'You' : latestOffer.sender_name}
                      </span>
                    </div>
                    <div className="offer-detail-item">
                      <span className="detail-label">Last updated</span>
                      <span className="detail-val">{formatTimestamp(latestOffer.updated_at)}</span>
                    </div>
                  </div>

                  {latestOffer.message && (
                    <div className="offer-note-box">
                      "{latestOffer.message}"
                    </div>
                  )}

                  {latestOffer.status === 'pending' && (
                    isOfferRecipient ? (
                      <div className="offer-actions-group">
                        <Button variant="primary" onClick={() => handleAcceptOffer(latestOffer.id)}>
                          <Check size={18} />
                          <span style={{ marginLeft: 'var(--s-2)' }}>Accept offer (₹{latestOffer.total_cost})</span>
                        </Button>
                        <Button variant="secondary" onClick={() => startCounterOffer(latestOffer)}>
                          <RefreshCw size={16} />
                          <span style={{ marginLeft: 'var(--s-2)' }}>Counter offer</span>
                        </Button>
                        <Button variant="secondary" onClick={() => handleRejectOffer(latestOffer.id)}>
                          <X size={16} />
                          <span style={{ marginLeft: 'var(--s-2)' }}>Decline</span>
                        </Button>
                      </div>
                    ) : (
                      <div className="waiting-indicator">
                        <Clock size={16} className="animate-pulse" />
                        <span>Waiting for recipient to respond</span>
                      </div>
                    )
                  )}

                  {latestOffer.status === 'accepted' && (
                    <div className="accepted-banner">
                      <Check size={20} />
                      <div>
                        <strong>Agreement confirmed!</strong>
                        <div style={{ fontSize: '0.8rem', opacity: 0.9 }}>
                          Borrow request generated for handover and final approval.
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="active-offer-card">
                  <div className="offer-card-top">
                    <span className="offer-label">Item listed rate</span>
                    <span className="offer-status-tag status-pending">Base rate</span>
                  </div>
                  <div className="offer-price-highlight">
                    <span className="offer-rate-large">—</span>
                  </div>
                  <p style={{ fontSize: '0.85rem', color: 'var(--p-muted)' }}>
                    No negotiation offer has been made yet. You can submit an offer for specific dates.
                  </p>
                  <Button variant="primary" onClick={startMakeOffer}>
                    Make an offer
                  </Button>
                </div>
              )}

              {negotiationMode && (
                <form className="offer-form-card" onSubmit={handleSubmitOffer}>
                  <div className="offer-form-title">
                    <Sparkles size={18} className="text-accent" />
                    {negotiationMode === 'counter' ? 'Counter offer' : 'New offer'}
                  </div>

                  <div className="form-field">
                    <label className="t-label">Listing</label>
                    <Input
                      id="offer-listing"
                      label="Listing"
                      type="select"
                      value={formListingId}
                      disabled={negotiationMode === 'counter'}
                      onChange={(e) => {
                        const selected = lenderListings.find((item) => item.id === e.target.value);
                        setFormListingId(e.target.value);
                        if (selected) setFormDailyPrice(selected.price_per_day);
                      }}
                    >
                      <option value="">Select a listing</option>
                      {lenderListings.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                    </Input>
                    {lenderListings.length === 0 && <span className="t-small muted">No available listings from this lender.</span>}
                  </div>

                  <div className="form-field">
                    <label className="t-label">Daily price (₹/day)</label>
                    <Input
                      id="offer-daily-price"
                      label="Daily price"
                      type="number"
                      min="1"
                      step="any"
                      placeholder="Enter daily price"
                      value={formDailyPrice}
                      onChange={(e) => setFormDailyPrice(e.target.value)}
                    />
                    {lenderListings.find((item) => item.id === formListingId)?.min_price_per_day && (
                      <span style={{ fontSize: '0.75rem', color: 'var(--p-muted)' }}>
                        Minimum accepted price: ₹{lenderListings.find((item) => item.id === formListingId).min_price_per_day}/day
                      </span>
                    )}
                  </div>

                  <div className="dates-row">
                    <div className="form-field">
                      <label className="t-label">Start date</label>
                      <Input
                        id="offer-start-date"
                        label="Start date"
                        type="date"
                        min={new Date().toISOString().split('T')[0]}
                        value={formStartDate}
                        onChange={(e) => setFormStartDate(e.target.value)}
                      />
                    </div>
                    <div className="form-field">
                      <label className="t-label">End date</label>
                      <Input
                        id="offer-end-date"
                        label="End date"
                        type="date"
                        min={formStartDate || new Date().toISOString().split('T')[0]}
                        value={formEndDate}
                        onChange={(e) => setFormEndDate(e.target.value)}
                      />
                    </div>
                  </div>

                  {(() => {
                    const calcs = getOfferCalculations();
                    if (!calcs.isValid) return null;
                    return (
                      <div className="calculation-preview-box">
                        <div className="calc-label">
                          <span>Duration: <strong>{calcs.days} day{calcs.days > 1 ? 's' : ''}</strong></span>
                          <div style={{ fontSize: '0.75rem', color: 'var(--p-muted)' }}>
                            ₹{formDailyPrice} × {calcs.days}
                          </div>
                        </div>
                        <div className="calc-total">₹{calcs.total}</div>
                      </div>
                    );
                  })()}

                  <div className="form-field">
                    <label className="t-label">Optional note</label>
                    <Input
                      id="offer-note"
                      label="Optional note"
                      type="textarea"
                      rows="2"
                      placeholder="e.g. Can I pickup Saturday morning?"
                      value={formNote}
                      onChange={(e) => setFormNote(e.target.value)}
                    />
                  </div>

                  {offerError && (
                    <div className="form-error-banner">
                      <AlertCircle size={16} />
                      <span>{offerError}</span>
                    </div>
                  )}

                  <div className="form-buttons-row">
                    <Button variant="secondary" type="button" onClick={() => setNegotiationMode(null)}>
                      Cancel
                    </Button>
                    <Button variant="primary" type="submit" disabled={offerSubmitting}>
                      {offerSubmitting ? 'Sending…' : negotiationMode === 'counter' ? 'Send counter' : 'Send offer'}
                    </Button>
                  </div>
                </form>
              )}

              {!negotiationMode && latestOffer?.status !== 'pending' && latestOffer?.status !== 'accepted' && (
                <Button variant="primary" onClick={startMakeOffer}>
                  Make new offer
                </Button>
              )}

              {offers.length > 0 && (
                <div className="negotiation-history-section">
                  <button
                    className="history-toggle-btn"
                    onClick={() => setShowHistory(!showHistory)}
                  >
                    <span>Negotiation history ({offers.length})</span>
                    {showHistory ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>

                  {showHistory && (
                    <div className="history-items-list">
                      {offers.map((off, idx) => (
                        <div key={off.id} className="history-item">
                          <div className="history-top">
                            <strong>Round {idx + 1}: ₹{off.daily_price}/day</strong>
                            <span className={`offer-status-tag status-${off.status}`}>
                              {off.status}
                            </span>
                          </div>
                          <div style={{ color: 'var(--p-muted)', fontSize: '0.75rem' }}>
                            Total: ₹{off.total_cost} ({formatDate(off.start_date)} - {formatDate(off.end_date)})
                          </div>
                          <div style={{ color: 'var(--p-muted)', fontSize: '0.75rem' }}>
                            By {user && off.sender_id === user.id ? 'You' : off.sender_name} on {formatTimestamp(off.created_at)}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </aside>
        )}
      </div>
    </div>
  );
};

export default Chat;
