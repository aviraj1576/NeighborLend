import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import './Register.css';

const Register = () => {
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    full_name: '',
    password: '',
    confirm_password: '',
    captcha_answer: ''
  });

  const [captcha, setCaptcha] = useState({ captcha_id: '', question: '' });
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { register } = useAuth();
  const navigate = useNavigate();

  const fetchCaptcha = async () => {
    try {
      const res = await api.get('/auth/captcha');
      setCaptcha(res.data);
      setFormData(prev => ({ ...prev, captcha_answer: '' }));
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
      [e.target.name]: e.target.value
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
        captcha_answer: formData.captcha_answer
      };

      await register(registerData);
      navigate(`/verify-email?email=${encodeURIComponent(formData.email)}`);
    } catch (err) {
      setError(
        err.response?.data?.detail ||
        'Failed to register. Please try again.'
      );
      fetchCaptcha();
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="register-page">
      <div className="register-container glass fade-in-up">

        <div className="register-header">
          <h1 className="gradient-text">Create Account</h1>
          <p>Join the community and start sharing.</p>
        </div>

        {error && <div className="error-banner">{error}</div>}

        <form onSubmit={handleSubmit} className="register-form">

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="full_name">Full Name</label>
              <input
                id="full_name"
                name="full_name"
                type="text"
                value={formData.full_name}
                onChange={handleChange}
                placeholder="John Doe"
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="username">Username</label>
              <input
                id="username"
                name="username"
                type="text"
                value={formData.username}
                onChange={handleChange}
                placeholder="johndoe"
                required
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="email">Email Address</label>
            <input
              id="email"
              name="email"
              type="email"
              value={formData.email}
              onChange={handleChange}
              placeholder="john@example.com"
              required
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                name="password"
                type="password"
                value={formData.password}
                onChange={handleChange}
                placeholder="••••••••"
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="confirm_password">Confirm Password</label>
              <input
                id="confirm_password"
                name="confirm_password"
                type="password"
                value={formData.confirm_password}
                onChange={handleChange}
                placeholder="••••••••"
                required
              />
            </div>
          </div>

          <div className="captcha-section">
            <div className="captcha-question">
              <span>Security Check:</span>
              <strong>{captcha.question}</strong>

              <button
                type="button"
                onClick={fetchCaptcha}
                className="refresh-captcha"
              >
                Refresh
              </button>
            </div>

            <input
              type="text"
              name="captcha_answer"
              value={formData.captcha_answer}
              onChange={handleChange}
              placeholder="Answer"
              required
            />
          </div>

          <button
            type="submit"
            className="btn-primary register-submit-btn"
            disabled={isLoading}
          >
            {isLoading ? (
              <span className="spinner"></span>
            ) : (
              'Create Account'
            )}
          </button>

        </form>

        <div className="register-footer">
          <p>
            Already have an account?{' '}
            <Link to="/login" className="auth-link">
              Log in
            </Link>
          </p>
        </div>

      </div>
    </div>
  );
};

export default Register;