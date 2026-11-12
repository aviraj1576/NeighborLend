import React, { createContext, useState, useEffect, useContext, useCallback, useRef } from 'react';
import api from '../api/client';
import { watchSessionChanges } from './sessionSync.js';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const authVersion = useRef(0);

  useEffect(() => {
    const invalidated = () => {
      authVersion.current += 1;
      setUser(null);
      setLoading(false);
    };
    window.addEventListener('auth:invalidated', invalidated);
    return () => window.removeEventListener('auth:invalidated', invalidated);
  }, []);

  useEffect(
    () =>
      watchSessionChanges(window, () => {
        authVersion.current += 1;
        setUser(null);
        setLoading(true);
        window.location.reload();
      }),
    [],
  );

  useEffect(() => {
    let cancelled = false;
    const version = authVersion.current;
    const checkAuth = async () => {
      const token = localStorage.getItem('nl_token');
      if (token) {
        try {
          const res = await api.get('/auth/me');
          if (
            cancelled ||
            version !== authVersion.current ||
            token !== localStorage.getItem('nl_token')
          )
            return;
          setUser(res.data);
        } catch {
          if (
            cancelled ||
            version !== authVersion.current ||
            token !== localStorage.getItem('nl_token')
          )
            return;
          setUser(null);
        }
      }
      if (!cancelled && version === authVersion.current) setLoading(false);
    };
    checkAuth();
    return () => {
      cancelled = true;
    };
  }, []);

  const authenticate = useCallback(async (path, payload) => {
    const version = ++authVersion.current;
    const res = await api.post(path, payload);
    if (version !== authVersion.current)
      throw new Error('Sign-in was superseded. Please sign in again.');
    localStorage.setItem('nl_token', res.data.access_token);
    setUser(res.data.user);
    setLoading(false);
    return res.data;
  }, []);

  const login = useCallback(
    (usernameOrEmail, password) =>
      authenticate('/auth/login', {
        username_or_email: usernameOrEmail, // Changed from 'username'
        password,
      }),
    [authenticate],
  );

  const register = useCallback(async (data) => {
    const res = await api.post('/auth/register', data);
    return res.data;
  }, []);

  const verifyEmail = useCallback(
    (email, code) => authenticate('/auth/verify-email', { email, code }),
    [authenticate],
  );

  const googleLogin = useCallback(
    (credential) => authenticate('/auth/google', { credential }),
    [authenticate],
  );

  const logout = () => {
    authVersion.current += 1;
    localStorage.removeItem('nl_token');
    setUser(null);
    setLoading(false);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        register,
        verifyEmail,
        googleLogin,
        logout,
        isAuthenticated: !!user,
      }}
    >
      <React.Fragment key={user?.id || 'anonymous'}>{children}</React.Fragment>
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
