import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import './Login.css';
import './VerifyEmail.css';

const VerifyEmail = () => {
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState(searchParams.get('email') || '');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const { verifyEmail } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (resendCooldown <= 0) return undefined;
    const timerId = window.setTimeout(
      () => setResendCooldown((remaining) => remaining - 1),
      1000,
    );
    return () => window.clearTimeout(timerId);
  }, [resendCooldown]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      await verifyEmail(email, code);
      navigate('/browse');
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to verify this email address.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleResend = async () => {
    setError('');
    setMessage('');
    try {
      const response = await api.post('/auth/resend-verification', { email });
      setMessage(response.data.message);
      setResendCooldown(60);
    } catch (err) {
      const retryAfter = Number(err.response?.headers?.['retry-after']);
      if (retryAfter > 0) setResendCooldown(retryAfter);
      setError(err.response?.data?.detail || 'Unable to resend the verification code.');
    }
  };

  return (
    <div className="login-page">
      <div className="login-container glass fade-in-up">
        <div className="login-header">
          <h1 className="gradient-text">Verify your email</h1>
          <p>Enter the 6-digit code we sent to activate your account.</p>
        </div>
        {error && <div className="error-banner">{error}</div>}
        {message && <div className="verification-message">{message}</div>}
        <form className="login-form" onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="verification-email">Email address</label>
            <input
              id="verification-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="verification-code">Verification code</label>
            <input
              id="verification-code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]{6}"
              maxLength={6}
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
              required
            />
          </div>
          <button type="submit" className="btn-primary login-submit-btn" disabled={isLoading}>
            {isLoading ? <span className="spinner" /> : 'Verify and continue'}
          </button>
        </form>
        <button
          type="button"
          className="resend-code-button"
          onClick={handleResend}
          disabled={!email || resendCooldown > 0}
        >
          {resendCooldown > 0 ? `Resend code in ${resendCooldown}s` : 'Resend code'}
        </button>
        <div className="login-footer">
          <p>Already verified? <Link to="/login" className="auth-link">Log in</Link></p>
        </div>
      </div>
    </div>
  );
};

export default VerifyEmail;
