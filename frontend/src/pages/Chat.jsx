import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { 
  MessageSquare, Send, ArrowLeft, Check, X, RefreshCw, 
  Calendar, Shield, Tag, ChevronDown, ChevronUp, AlertCircle, 
  ExternalLink, Search, Clock, Sparkles
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import { resolvePhotoUrl } from '../utils/photoUrl';
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

  // Conversations List State
  const [conversations, setConversations] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loadingConversations, setLoadingConversations] = useState(true);

  // Active Conversation State
  const [activeConv, setActiveConv] = useState(null);
  const [messages, setMessages] = useState([]);
  const [offers, setOffers] = useState([]);
  const [loadingActive, setLoadingActive] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  // Message Input State
  const [newMessage, setNewMessage] = useState('');
  const [sendingMessage, setSendingMessage] = useState(false);

  // Negotiation Panel State
  const [showNegotiation, setShowNegotiation] = useState(true);
  const [showHistory, setShowHistory] = useState(false);
  const [negotiationMode, setNegotiationMode] = useState(null); // 'make' | 'counter' | null
  const [counterTargetOffer, setCounterTargetOffer] = useState(null);

  // Offer Form Inputs
  const [formDailyPrice, setFormDailyPrice] = useState('');
  const [formStartDate, setFormStartDate] = useState('');
  const [formEndDate, setFormEndDate] = useState('');
  const [formNote, setFormNote] = useState('');
  const [offerSubmitting, setOfferSubmitting] = useState(false);
  const [offerError, setOfferError] = useState('');

  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // 1. Fetch Conversations List
  const fetchConversations = async (silent = false) => {
    if (!silent) setLoadingConversations(true);
    try {
      const res = await api.get('/conversations');
      setConversations(res.data);
    } catch (err) {
      console.error('Failed to load conversations:', err);
    } finally {
      if (!silent) setLoadingConversations(false);
    }
  };

  useEffect(() => {
    fetchConversations();
  }, []);

  // 2. Fetch Active Conversation Detail
  const fetchActiveConversation = async (convId, silent = false) => {
    if (!convId) return;
    if (!silent) setLoadingActive(true);
    setErrorMsg('');
    try {
      const res = await api.get(`/conversations/${convId}`);
      setActiveConv(res.data);
      setMessages(res.data.messages || []);
      setOffers(res.data.offers || []);
    } catch (err) {
      console.error('Failed to fetch conversation details:', err);
      setErrorMsg('Could not load conversation. It may not exist or you lack access.');
    } finally {
      if (!silent) setLoadingActive(false);
    }
  };

  useEffect(() => {
    if (conversationId) {
      fetchActiveConversation(conversationId);
    } else if (conversations.length > 0 && !activeConv) {
      // Navigate to first conversation on desktop
      navigate(`/messages/${conversations[0].id}`, { replace: true });
    }
  }, [conversationId, conversations]);

  // Scroll to bottom when messages update
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 3. Real-Time Auto Refresh (Poll every 3 seconds for active conversation)
  useEffect(() => {
    if (!conversationId) return;
    const interval = setInterval(() => {
      fetchActiveConversation(conversationId, true);
      fetchConversations(true);
    }, 3000);

    return () => clearInterval(interval);
  }, [conversationId]);

  // 4. Send Message Handler
  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    if (!newMessage.trim() || sendingMessage || !activeConv) return;

    const content = newMessage.trim();
    setNewMessage('');
    setSendingMessage(true);

    // Optimistic message
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
      // Remove optimistic message if error
      setMessages((prev) => prev.filter((m) => m.id !== tempId));
    } finally {
      setSendingMessage(false);
    }
  };

  // Helper: Live calculation of duration and total cost for offer form
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
    if (days === 0) days = 1; // Same day rental
    const total = Math.round(days * price * 100) / 100;
    return { days, total, isValid: true };
  };

  // 5. Open Make Offer / Counter Offer
  const startMakeOffer = () => {
    setNegotiationMode('make');
    setCounterTargetOffer(null);
    setOfferError('');
    const today = new Date().toISOString().split('T')[0];
    const defaultEnd = new Date(Date.now() + 86400000 * 2).toISOString().split('T')[0];
    setFormStartDate(today);
    setFormEndDate(defaultEnd);
    setFormDailyPrice(activeConv?.listing?.price_per_day || '');
    setFormNote('');
  };

  const startCounterOffer = (targetOffer) => {
    setNegotiationMode('counter');
    setCounterTargetOffer(targetOffer);
    setOfferError('');
    setFormDailyPrice(targetOffer.daily_price || activeConv?.listing?.price_per_day || '');
    setFormStartDate(targetOffer.start_date.split('T')[0]);
    setFormEndDate(targetOffer.end_date.split('T')[0]);
    setFormNote('');
  };

  // 6. Submit Offer or Counter Offer
  const handleSubmitOffer = async (e) => {
    e.preventDefault();
    setOfferError('');
    const calcs = getOfferCalculations();
    if (!calcs.isValid) {
      setOfferError(calcs.error || 'Please fill in a valid daily price and date range.');
      return;
    }

    const price = parseFloat(formDailyPrice);
    if (activeConv?.listing?.min_price_per_day && price < activeConv.listing.min_price_per_day) {
      setOfferError(`Minimum price per day is ₹${activeConv.listing.min_price_per_day}`);
      return;
    }

    setOfferSubmitting(true);
    try {
      const payload = {
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

  // 7. Accept Offer Handler
  const handleAcceptOffer = async (offerId) => {
    if (!window.confirm('Accept this rental offer? This will initiate the borrow booking request.')) return;
    try {
      await api.post(`/offers/${offerId}/accept`);
      await fetchActiveConversation(activeConv.id, true);
      fetchConversations(true);
    } catch (err) {
      console.error('Failed to accept offer:', err);
      alert(err.response?.data?.detail || 'Failed to accept offer.');
    }
  };

  // 8. Reject Offer Handler
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

  // Filter conversations
  const filteredConversations = conversations.filter((c) => {
    const term = searchQuery.toLowerCase();
    const lName = (c.listing?.name || '').toLowerCase();
    const oName = (c.other_participant?.name || '').toLowerCase();
    const uName = (c.other_participant?.username || '').toLowerCase();
    return lName.includes(term) || oName.includes(term) || uName.includes(term);
  });

  const latestOffer = activeConv?.active_offer || (offers.length > 0 ? offers[offers.length - 1] : null);
  const isOfferRecipient = latestOffer && user && latestOffer.sender_id !== user.id;

  return (
    <div className="chat-page">
      {/* 1. Conversations Sidebar */}
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
            <input 
              type="text" 
              placeholder="Search conversations..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        <div className="conversations-list">
          {loadingConversations ? (
            <div className="sidebar-loading-state">
              <RefreshCw className="animate-spin text-accent" size={24} />
              <p>Loading messages...</p>
            </div>
          ) : filteredConversations.length === 0 ? (
            <div className="sidebar-empty-state">
              <MessageSquare size={36} className="text-muted" />
              <p>No conversations found.</p>
              <Link to="/browse" className="btn-outline btn-sm">Browse Items</Link>
            </div>
          ) : (
            filteredConversations.map((conv) => {
              const isActive = conv.id === conversationId;
              const other = conv.other_participant;
              const photoUrl = resolvePhotoUrl(conv.listing?.photo_url);
              const actOffer = conv.active_offer;

              return (
                <div 
                  key={conv.id} 
                  className={`conversation-item ${isActive ? 'active' : ''}`}
                  onClick={() => navigate(`/messages/${conv.id}`)}
                >
                  <div className="item-thumb-wrapper">
                    {photoUrl ? (
                      <img src={photoUrl} alt={conv.listing.name} className="item-thumbnail" />
                    ) : (
                      <div className="item-thumbnail-placeholder">
                        <Tag size={20} />
                      </div>
                    )}
                    <div className="avatar-badge-small" title={other.name}>
                      {(other.name || 'U')[0].toUpperCase()}
                    </div>
                  </div>

                  <div className="conversation-content">
                    <div className="conversation-top-row">
                      <span className="listing-name" title={conv.listing?.name}>
                        {conv.listing?.name}
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

      {/* 2. Main Chat Window */}
      {conversationId ? (
        <section className={`chat-window ${!conversationId ? 'hidden-mobile' : ''}`}>
          {/* Header */}
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
                  {activeConv.listing?.photo_url ? (
                    <img 
                      src={resolvePhotoUrl(activeConv.listing.photo_url)}
                      alt={activeConv.listing.name} 
                      className="chat-listing-thumb" 
                    />
                  ) : (
                    <div className="chat-listing-thumb item-thumbnail-placeholder">
                      <Tag size={18} />
                    </div>
                  )}
                  <div className="chat-listing-meta">
                    <h3 className="chat-listing-title">
                      <Link to={`/listing/${activeConv.listing_id}`} className="hover-underline">
                        {activeConv.listing?.name}
                      </Link>
                    </h3>
                    <div className="chat-listing-pricing">
                      <span>₹{activeConv.listing?.price_per_day}/day</span>
                      <span>•</span>
                      <span>
                        with {activeConv.is_borrower ? activeConv.lender.name : activeConv.borrower.name}
                      </span>
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

          {/* Messages Feed */}
          <div className="messages-container">
            {loadingActive ? (
              <div className="messages-empty-state">
                <RefreshCw className="animate-spin text-accent" size={28} />
                <p>Loading messages...</p>
              </div>
            ) : errorMsg ? (
              <div className="messages-empty-state text-danger">
                <AlertCircle size={32} />
                <p>{errorMsg}</p>
              </div>
            ) : messages.length === 0 ? (
              <div className="messages-empty-state">
                <Sparkles size={36} className="text-accent" />
                <h4>Start the conversation</h4>
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

          {/* Message Input */}
          <form className="chat-input-bar" onSubmit={handleSendMessage}>
            <div className="chat-input-wrapper">
              <textarea 
                className="chat-textarea"
                rows="1"
                placeholder="Type a message... (Press Enter to send)"
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
          <h3>Select a conversation</h3>
          <p>Choose a chat from the sidebar or browse items to start negotiating.</p>
          <Link to="/browse" className="btn-primary">Browse Marketplace</Link>
        </section>
      )}

      {/* 3. Negotiation Panel */}
      {conversationId && activeConv && showNegotiation && (
        <aside className="negotiation-panel">
          <div className="negotiation-header">
            <h3 className="negotiation-title">
              <Tag size={20} className="text-accent" />
              Rental Negotiation
            </h3>
            <button 
              className="negotiation-close-btn" 
              onClick={() => setShowNegotiation(false)}
            >
              <X size={18} />
            </button>
          </div>

          <div className="negotiation-body">
            {/* Active Offer Card */}
            {latestOffer ? (
              <div className="active-offer-card">
                <div className="offer-card-top">
                  <span className="offer-label">Current Offer</span>
                  <span className={`offer-status-tag status-${latestOffer.status}`}>
                    {latestOffer.status}
                  </span>
                </div>

                <div className="offer-price-highlight">
                  <span className="offer-rate-large gradient-text">₹{latestOffer.daily_price}</span>
                  <span className="offer-unit">/ day</span>
                </div>

                <div className="offer-details-grid">
                  <div className="offer-detail-item">
                    <span className="detail-label">Rental Period</span>
                    <span className="detail-val">
                      {formatDate(latestOffer.start_date)} - {formatDate(latestOffer.end_date)}
                    </span>
                  </div>
                  <div className="offer-detail-item">
                    <span className="detail-label">Total Cost</span>
                    <span className="detail-val text-accent">₹{latestOffer.total_cost}</span>
                  </div>
                  <div className="offer-detail-item">
                    <span className="detail-label">Proposed By</span>
                    <span className="detail-val">
                      {user && latestOffer.sender_id === user.id ? 'You' : latestOffer.sender_name}
                    </span>
                  </div>
                  <div className="offer-detail-item">
                    <span className="detail-label">Last Updated</span>
                    <span className="detail-val">{formatTimestamp(latestOffer.updated_at)}</span>
                  </div>
                </div>

                {latestOffer.message && (
                  <div className="offer-note-box">
                    "{latestOffer.message}"
                  </div>
                )}

                {/* Offer Action Buttons */}
                {latestOffer.status === 'pending' && (
                  isOfferRecipient ? (
                    <div className="offer-actions-group">
                      <button 
                        className="btn-accept" 
                        onClick={() => handleAcceptOffer(latestOffer.id)}
                      >
                        <Check size={18} />
                        Accept Offer (₹{latestOffer.total_cost})
                      </button>
                      <button 
                        className="btn-counter" 
                        onClick={() => startCounterOffer(latestOffer)}
                      >
                        <RefreshCw size={16} />
                        Counter Offer
                      </button>
                      <button 
                        className="btn-reject" 
                        onClick={() => handleRejectOffer(latestOffer.id)}
                      >
                        <X size={16} />
                        Decline
                      </button>
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
                      <strong>Agreement Confirmed!</strong>
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
                  <span className="offer-label">Item Listed Rate</span>
                  <span className="offer-status-tag status-pending">Base Rate</span>
                </div>
                <div className="offer-price-highlight">
                  <span className="offer-rate-large gradient-text">₹{activeConv.listing?.price_per_day}</span>
                  <span className="offer-unit">/ day</span>
                </div>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  No negotiation offer has been made yet. You can submit an offer for specific dates.
                </p>
                <button className="btn-primary" onClick={startMakeOffer}>
                  Make an Offer
                </button>
              </div>
            )}

            {/* Make / Counter Offer Form */}
            {negotiationMode && (
              <form className="offer-form-card" onSubmit={handleSubmitOffer}>
                <div className="offer-form-title">
                  <Sparkles size={18} className="text-accent" />
                  {negotiationMode === 'counter' ? 'Counter Offer' : 'New Offer'}
                </div>

                <div className="form-field">
                  <label>Daily Price (₹/day)</label>
                  <input 
                    type="number" 
                    min="1" 
                    step="any"
                    required
                    placeholder="Enter daily price"
                    value={formDailyPrice}
                    onChange={(e) => setFormDailyPrice(e.target.value)}
                  />
                  {activeConv.listing?.min_price_per_day && (
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      Minimum accepted price: ₹{activeConv.listing.min_price_per_day}/day
                    </span>
                  )}
                </div>

                <div className="dates-row">
                  <div className="form-field">
                    <label>Start Date</label>
                    <input 
                      type="date" 
                      required
                      min={new Date().toISOString().split('T')[0]}
                      value={formStartDate}
                      onChange={(e) => setFormStartDate(e.target.value)}
                    />
                  </div>
                  <div className="form-field">
                    <label>End Date</label>
                    <input 
                      type="date" 
                      required
                      min={formStartDate || new Date().toISOString().split('T')[0]}
                      value={formEndDate}
                      onChange={(e) => setFormEndDate(e.target.value)}
                    />
                  </div>
                </div>

                {/* Live Cost Calculation */}
                {(() => {
                  const calcs = getOfferCalculations();
                  if (!calcs.isValid) return null;
                  return (
                    <div className="calculation-preview-box">
                      <div className="calc-label">
                        <span>Duration: <strong>{calcs.days} day{calcs.days > 1 ? 's' : ''}</strong></span>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          ₹{formDailyPrice} × {calcs.days}
                        </div>
                      </div>
                      <div className="calc-total">
                        ₹{calcs.total}
                      </div>
                    </div>
                  );
                })()}

                <div className="form-field">
                  <label>Optional Note</label>
                  <textarea 
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
                  <button 
                    type="button" 
                    className="btn-outline" 
                    onClick={() => setNegotiationMode(null)}
                  >
                    Cancel
                  </button>
                  <button 
                    type="submit" 
                    className="btn-primary" 
                    disabled={offerSubmitting}
                  >
                    {offerSubmitting ? 'Sending...' : negotiationMode === 'counter' ? 'Send Counter' : 'Send Offer'}
                  </button>
                </div>
              </form>
            )}

            {/* Offer Button if not in form mode and offer can be started/replaced */}
            {!negotiationMode && latestOffer?.status !== 'pending' && latestOffer?.status !== 'accepted' && (
              <button className="btn-primary" onClick={startMakeOffer}>
                Make New Offer
              </button>
            )}

            {/* Negotiation History */}
            {offers.length > 0 && (
              <div className="negotiation-history-section">
                <button 
                  className="history-toggle-btn"
                  onClick={() => setShowHistory(!showHistory)}
                >
                  <span>Negotiation History ({offers.length})</span>
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
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                          Total: ₹{off.total_cost} ({formatDate(off.start_date)} - {formatDate(off.end_date)})
                        </div>
                        <div style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
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
  );
};

export default Chat;
