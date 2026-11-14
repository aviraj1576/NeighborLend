import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LifeBuoy } from 'lucide-react';
import api from '../api/client';
import './SupportChatButton.css';

/**
 * "Chat with us" action for error-prone steps. Opens a NeighborLend support thread in the
 * existing messages inbox, passing the step name and the lend/listing it came from.
 * Props: step (e.g. 'handover_photos'), entityType ('borrow_request' | 'listing' | null),
 * entityId, label.
 */
export default function SupportChatButton({ step, entityType = null, entityId = null, label = 'Chat with us' }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const open = async () => {
    if (!localStorage.getItem('nl_token')) {
      navigate('/login');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const res = await api.post('/support/chat', {
        context_step: step,
        entity_type: entityType,
        entity_id: entityId,
      });
      navigate(`/messages/${res.data.conversation_id}`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not open the chat. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <span className="support-chat">
      <button type="button" className="support-chat__btn" onClick={open} disabled={busy} data-support-step={step}>
        <LifeBuoy size={16} aria-hidden="true" /> {busy ? 'Opening…' : label}
      </button>
      {error && <span className="support-chat__error" role="alert">{error}</span>}
    </span>
  );
}
