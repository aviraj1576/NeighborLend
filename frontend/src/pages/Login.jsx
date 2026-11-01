import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import './Login.css';

const Login = () => {
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { login, googleLogin } = useAuth();
  const navigate = useNavigate();
  const googleButtonRef = useRef(null);

  useEffect(() => {
    if (!googleClientId) return undefined;

    const mountGoogleButton = () => {
      if (!window.google?.accounts?.id || !googleButtonRef.current) return false;
      window.google.accounts.id.initialize({
        client_id: googleClientId,
        callback: async ({ credential }) => {
          setError('');
          setIsLoading(true);
          try {
            await googleLogin(credential);
            navigate('/browse');
          } catch (err) {
            setError(err.response?.data?.detail || 'Google Sign-In failed. Please try again.');
          } finally {
            setIsLoading(false);
          }
        },
      });
      window.google.accounts.id.renderButton(googleButtonRef.current, {
        theme: 'outline',
        size: 'large',
        shape: 'rectangular',
        text: 'signin_with',
        width: 320,
      });
      return true;
    };

    if (mountGoogleButton()) return undefined;
    const intervalId = window.setInterval(() => {
      if (mountGoogleButton()) window.clearInterval(intervalId);
    }, 250);
    return () => window.clearInterval(intervalId);
  }, [googleClientId, googleLogin, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await login(identifier, password);
      navigate('/browse');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to login. Please check your credentials.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleSetupNotice = () => {
    setError('Google Sign-In needs a Google OAuth Web client ID. Set VITE_GOOGLE_CLIENT_ID and GOOGLE_CLIENT_ID in the project .env, then restart Vite and the backend.');
  };

  return (
    <div className="login-page">
      <div className="login-container glass fade-in-up">
        <div className="login-header">
          <h1 className="gradient-text">Welcome Back</h1>
          <p>Login to continue sharing with your neighborhood.</p>
        </div>

        {error && <div className="error-banner">{error}</div>}

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label htmlFor="identifier">Username or Email</label>
            <input
              id="identifier"
              type="text"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              placeholder="Enter your username or email"
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <div className="password-input-wrapper">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                required
              />
              <button 
                type="button" 
                className="toggle-password"
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>

          <button type="submit" className="btn-primary login-submit-btn" disabled={isLoading}>
            {isLoading ? <span className="spinner"></span> : 'Login'}
          </button>
        </form>

        <div className="login-divider"><span>or continue with</span></div>
        {googleClientId ? (
            <div className="google-signin" ref={googleButtonRef} />
        ) : (
          <div className="google-signin-unconfigured">
            <button type="button" className="google-signin-button" onClick={handleGoogleSetupNotice}>
              <span className="google-signin-mark" aria-hidden="true">G</span>
              Continue with Google
            </button>
            <p>Google Sign-In requires an OAuth client ID to be configured.</p>
          </div>
        )}

        <div className="login-footer">
          <p>Don't have an account? <Link to="/register" className="auth-link">Register</Link></p>
        </div>
      </div>
    </div>
  );
};

export default Login;
