import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Card from '../components/ui/Card';
import './Register.css';

const Register = () => {
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    full_name: '',
    password: '',
    confirm_password: '',
    captcha_answer: '',
  });

  const [captcha, setCaptcha] = useState({ captcha_id: '', question: '' });
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { register } = useAuth();
  const navigate = useNavigate();

  const getRegistrationError = (err) => {
    const detail = err.response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => (typeof item === 'string' ? item : item?.msg || item?.message))
        .filter(Boolean);
      if (messages.length) return messages.join('. ');
    }
    if (detail && typeof detail === 'object') {
      if (typeof detail.message === 'string') return detail.message;
      if (typeof detail.msg === 'string') return detail.msg;
    }
    if (err.response?.status === 503) {
      return 'The verification email could not be sent. Check your Brevo SMTP settings and try again.';
    }
    return 'Failed to register. Please check your details and try again.';
  };

  const fetchCaptcha = async () => {
    try {
      const res = await api.get('/auth/captcha');
      setCaptcha(res.data);
      setFormData((prev) => ({ ...prev, captcha_answer: '' }));
    } catch (err) {
      console.error('Failed to fetch captcha', err);
      setError('Failed to load security check.');
    }
  };

  useEffect(() => {
    fetchCaptcha();
  }, []);

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (formData.password !== formData.confirm_password) {
      return setError('Passwords do not match');
    }

    if (formData.password.length < 6) {
      return setError('Password must be at least 6 characters');
    }

    if (!captcha.captcha_id || !formData.captcha_answer) {
      return setError('Please complete the security check');
    }

    setIsLoading(true);

    try {
      const registerData = {
        name: formData.full_name,
        username: formData.username,
        email: formData.email,
        password: formData.password,
        captcha_id: captcha.captcha_id,
        captcha_answer: formData.captcha_answer,
      };

      await register(registerData);
      navigate(`/verify-email?email=${encodeURIComponent(formData.email)}`);
    } catch (err) {
      setError(getRegistrationError(err));
      await fetchCaptcha();
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="register-page app-page">
      <div className="wrap grid grid--top">
        <div className="register-copy span-6">
          <div className="register-header">
            <h1 className="t-h1">Create an account.</h1>
            <p className="t-lead measure">
              Join the neighborhood and start borrowing and lending with the people around you.
            </p>
          </div>
        </div>

        <div className="register-form-wrap span-5 start-7">
          <Card variant="default" className="register-card">
            <div className="form-body">
              {error && (
                <div className="error-banner" role="alert">
                  {error}
                </div>
              )}

              <form onSubmit={handleSubmit} className="register-form">
                <div className="form-row">
                  <Input
                    id="full_name"
                    name="full_name"
                    label="Full name"
                    type="text"
                    placeholder="John Doe"
                    value={formData.full_name}
                    onChange={handleChange}
                    required
                  />
                  <Input
                    id="username"
                    name="username"
                    label="Username"
                    type="text"
                    placeholder="johndoe"
                    value={formData.username}
                    onChange={handleChange}
                    required
                  />
                </div>

                <Input
                  id="email"
                  name="email"
                  label="Email address"
                  type="email"
                  placeholder="john@example.com"
                  value={formData.email}
                  onChange={handleChange}
                  required
                />

                <div className="form-row">
                  <Input
                    id="password"
                    name="password"
                    label="Password"
                    type="password"
                    placeholder="••••••••"
                    value={formData.password}
                    onChange={handleChange}
                    required
                  />
                  <Input
                    id="confirm_password"
                    name="confirm_password"
                    label="Confirm password"
                    type="password"
                    placeholder="••••••••"
                    value={formData.confirm_password}
                    onChange={handleChange}
                    required
                  />
                </div>

                <div className="captcha-section">
                  <div className="captcha-question">
                    <span>Security check</span>
                    <strong>{captcha.question}</strong>
                    <button
                      type="button"
                      onClick={fetchCaptcha}
                      className="refresh-captcha"
                      aria-label="Refresh security question"
                    >
                      Refresh
                    </button>
                  </div>
                  <Input
                    id="captcha_answer"
                    name="captcha_answer"
                    label="Your answer"
                    type="text"
                    placeholder="Answer"
                    value={formData.captcha_answer}
                    onChange={handleChange}
                    required
                  />
                </div>

                <Button
                  variant="primary"
                  type="submit"
                  disabled={isLoading}
                  className="register-submit-btn"
                >
                  {isLoading ? 'Creating account…' : 'Create account'}
                </Button>
              </form>

              <div className="register-footer">
                <p className="t-body">
                  Already have an account?{' '}
                  <Link to="/login" className="auth-link">
                    Sign in
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

export default Register;
