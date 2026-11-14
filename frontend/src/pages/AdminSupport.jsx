import React, { useCallback, useEffect, useState } from 'react';
import api from '../api/client';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Badge from '../components/ui/Badge';
import { apiError } from '../components/damage/damageApi';
import { AdminNav } from './AdminDisputes';
import './Admin.css';

const parseMeta = (raw) => {
  try { return raw ? JSON.parse(raw) : null; } catch { return null; }
};

export default function AdminSupport() {
  const [status, setStatus] = useState('escalated');
  const [rows, setRows] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [ticket, setTicket] = useState(null);
  const [reply, setReply] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const loadList = useCallback(async () => {
    try {
      setRows((await api.get('/admin/support/escalations', { params: { status } })).data);
      setError('');
    } catch (err) {
      setError(apiError(err, 'Could not load support chats.'));
    }
  }, [status]);

  const loadTicket = useCallback(async (id) => {
    try {
      setTicket((await api.get(`/admin/support/escalations/${id}`)).data);
    } catch (err) {
      setError(apiError(err, 'Could not load this chat.'));
    }
  }, []);

  useEffect(() => { setRows(null); loadList(); }, [loadList]);
  useEffect(() => { if (selectedId) loadTicket(selectedId); else setTicket(null); }, [selectedId, loadTicket]);

  const send = async () => {
    if (!reply.trim()) return;
    setBusy(true);
    setError('');
    try {
      await api.post(`/admin/support/escalations/${selectedId}/reply`, { content: reply.trim() });
      setReply('');
      await loadTicket(selectedId);
    } catch (err) {
      setError(apiError(err, 'Could not send the reply.'));
    } finally {
      setBusy(false);
    }
  };

  const closeChat = async () => {
    if (!window.confirm('Close this chat? The user can still start a new one.')) return;
    setBusy(true);
    setError('');
    try {
      await api.post(`/admin/support/escalations/${selectedId}/close`);
      setSelectedId(null);
      await loadList();
    } catch (err) {
      setError(apiError(err, 'Could not close the chat.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="admin-page app-page">
      <div className="wrap">
        <section className="admin-card card">
          <h1 className="t-h1">Admin</h1>
          <AdminNav active="support" />
          <div className="admin-filter" role="group" aria-label="Filter chats">
            {[['escalated', 'Needs a human'], ['closed', 'Closed']].map(([value, label]) => (
              <button
                key={value} type="button" aria-pressed={status === value}
                className={status === value ? 'admin-chip admin-chip--on' : 'admin-chip'}
                onClick={() => { setStatus(value); setSelectedId(null); }}
              >
                {label}
              </button>
            ))}
          </div>

          {error && <div className="error-banner" role="alert">{error}</div>}
          {!rows && !error && <p className="t-body">Loading chats…</p>}
          {rows && rows.length === 0 && <p className="t-body">No {status} chats.</p>}

          <div className="support-admin">
            {rows && rows.length > 0 && (
              <ul className="support-list">
                {rows.map((t) => (
                  <li key={t.id}>
                    <button
                      type="button"
                      className={selectedId === t.id ? 'support-item support-item--on' : 'support-item'}
                      onClick={() => setSelectedId(t.id)}
                    >
                      <strong>{t.user.name}</strong>
                      <span className="admin-mono">{t.context_step}</span>
                      <span>{t.last_user_message || '—'}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {ticket && (
              <div className="support-thread">
                <div className="admin-head">
                  <h2 className="t-h2">{ticket.user.name}</h2>
                  <Badge variant="outline">{ticket.context_step}</Badge>
                  {ticket.entity_id && <span className="admin-mono">{ticket.entity_type} {ticket.entity_id}</span>}
                </div>
                <ul className="support-messages" aria-label="Conversation">
                  {ticket.messages.map((m) => {
                    const meta = parseMeta(m.meta);
                    const fromUser = m.sender_id === ticket.user.id;
                    return (
                      <li key={m.id} className={m.is_system ? 'support-msg support-msg--system' : fromUser ? 'support-msg support-msg--user' : 'support-msg'}>
                        <span className="support-msg-who">
                          {m.is_system ? 'System' : fromUser ? ticket.user.name : meta?.admin ? 'Staff' : 'Bot'}
                        </span>
                        {m.content}
                      </li>
                    );
                  })}
                </ul>
                {ticket.status === 'escalated' ? (
                  <div className="support-reply">
                    <Input
                      id="support-reply" label="Reply as NeighborLend Support" type="textarea" rows="3"
                      maxLength={2000} value={reply} onChange={(e) => setReply(e.target.value)}
                    />
                    <div className="dmg-row">
                      <Button variant="primary" disabled={busy || !reply.trim()} onClick={send}>
                        {busy ? 'Sending…' : 'Send reply'}
                      </Button>
                      <Button variant="secondary" disabled={busy} onClick={closeChat}>Close chat</Button>
                    </div>
                  </div>
                ) : (
                  <p className="t-small muted">This chat is {ticket.status}.</p>
                )}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
