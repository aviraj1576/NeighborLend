import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Card from '../components/ui/Card';
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
    <div className="login-page app-page">
      <div className="wrap grid grid--top">
        <div className="login-copy span-6">
          <div className="login-header">
            <h1 className="t-h1">Welcome back.</h1>
            <p className="t-lead measure">
              Sign in to continue borrowing and lending with your neighbors.
            </p>
          </div>
        </div>

        <div className="login-form-wrap span-5 start-7">
          <Card variant="default" className="login-card">
            <div className="form-body">
              {error && (
                <div className="error-banner" role="alert">
                  {error}
                </div>
              )}

              <form onSubmit={handleSubmit} className="login-form">
                <Input
                  id="identifier"
                  name="identifier"
                  label="Username or email"
                  type="text"
                  placeholder="Enter your username or email"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  required
                />
                <div className="password-group">
                  <Input
                    id="password"
                    name="password"
                    label="Password"
                    type={showPassword ? 'text' : 'password'}
                    placeholder="Enter your password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                  <button
                    type="button"
                    className="toggle-password"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? 'Hide' : 'Show'}
                  </button>
                </div>

                <Button
                  variant="primary"
                  type="submit"
                  disabled={isLoading}
                  className="login-submit-btn"
                >
                  {isLoading ? 'Signing in…' : 'Sign in'}
                </Button>
              </form>

              <div className="login-divider">
                <span>Or continue with</span>
              </div>

              {googleClientId ? (
                <div className="google-signin" ref={googleButtonRef} />
              ) : (
                <div className="google-signin-unconfigured">
                  <Button
                    variant="secondary"
                    type="button"
                    onClick={handleGoogleSetupNotice}
                    className="google-signin-button"
                  >
                    Continue with Google
                  </Button>
                  <p className="t-small muted">
                    Google Sign-In requires an OAuth client ID to be configured.
                  </p>
                </div>
              )}

              <div className="login-footer">
                <p className="t-body">
                  Don&rsquo;t have an account?{' '}
                  <Link to="/register" className="auth-link">
                    Create an account
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

export default Login;
