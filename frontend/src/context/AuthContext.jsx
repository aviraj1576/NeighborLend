import React, { createContext, useState, useEffect, useContext, useCallback } from 'react';
import api from '../api/client';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem('nl_token');
      if (token) {
        try {
          const res = await api.get('/auth/me');
          setUser(res.data);
        } catch (err) {
          console.error('Auth check failed:', err);
          localStorage.removeItem('nl_token');
          setUser(null);
        }
      }
      setLoading(false);
    };
    checkAuth();
  }, []);

  const login = useCallback(async (usernameOrEmail, password) => {
    const res = await api.post('/auth/login', {
      username_or_email: usernameOrEmail, // Changed from 'username'
      password
    });
    localStorage.setItem('nl_token', res.data.access_token);
    setUser(res.data.user || res.data);
    return res.data;
  }, []);

  const register = useCallback(async (data) => {
    const res = await api.post('/auth/register', data);
    return res.data;
  }, []);

  const verifyEmail = useCallback(async (email, code) => {
    const res = await api.post('/auth/verify-email', { email, code });
    localStorage.setItem('nl_token', res.data.access_token);
    setUser(res.data.user);
    return res.data;
  }, []);

  const googleLogin = useCallback(async (credential) => {
    const res = await api.post('/auth/google', { credential });
    localStorage.setItem('nl_token', res.data.access_token);
    setUser(res.data.user);
    return res.data;
  }, []);

  const logout = () => {
    localStorage.removeItem('nl_token');
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{
      user,
      loading,
      login,
      register,
      verifyEmail,
      googleLogin,
      logout,
      isAuthenticated: !!user
    }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
