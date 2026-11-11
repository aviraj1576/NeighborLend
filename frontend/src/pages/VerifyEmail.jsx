import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Card from '../components/ui/Card';
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
    <div className="verify-page section" style={{ '--h': '1' }}>
      <div className="wrap grid grid--top">
        <div className="verify-copy span-6">
          <div className="verify-header">
            <h1 className="t-h1">Verify your email</h1>
            <p className="t-lead measure">
              Enter the 6-digit code we sent to activate your account.
            </p>
          </div>
        </div>

        <div className="verify-form-wrap span-5 start-7">
          <Card variant="default" className="verify-card">
            <div className="form-body">
              {error && (
                <div className="error-banner" role="alert">
                  {error}
                </div>
              )}
              {message && (
                <div className="verification-message" role="status">
                  {message}
                </div>
              )}

              <form className="verify-form" onSubmit={handleSubmit}>
                <Input
                  id="verification-email"
                  name="email"
                  label="Email address"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
                <Input
                  id="verification-code"
                  name="code"
                  label="Verification code"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  value={code}
                  onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
                  required
                />
                <Button
                  variant="primary"
                  type="submit"
                  disabled={isLoading}
                  className="verify-submit-btn"
                >
                  {isLoading ? 'Verifying…' : 'Verify and continue'}
                </Button>
              </form>

              <Button
                variant="secondary"
                type="button"
                onClick={handleResend}
                disabled={!email || resendCooldown > 0}
                className="resend-code-button"
              >
                {resendCooldown > 0 ? `Resend code in ${resendCooldown}s` : 'Resend code'}
              </Button>

              <div className="verify-footer">
                <p className="t-body">
                  Already verified?{' '}
                  <Link to="/login" className="auth-link">
                    Log in
                  </Link>
                </p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default VerifyEmail;
