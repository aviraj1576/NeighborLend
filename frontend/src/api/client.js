import axios from 'axios';
import { invalidateSession } from '../context/sessionSync.js';

const api = axios.create({
  baseURL: import.meta.env?.VITE_API_BASE_URL || '/api',
});

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('nl_token');
    config.sessionToken = token;
    if (token) {
      if (config.headers && typeof config.headers.set === 'function') {
        config.headers.set('Authorization', `Bearer ${token}`);
      } else {
        config.headers = config.headers || {};
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  },
);

api.interceptors.response.use(
  (response) => {
    if (response.config.sessionToken !== localStorage.getItem('nl_token')) {
      return Promise.reject(new Error('Account changed. Reload this page before continuing.'));
    }
    return response;
  },
  (error) => {
    if (error.response && error.response.status === 401) {
      const requestUrl = error.config?.url || '';
      const isAuthEndpoint = [
        '/auth/login',
        '/auth/register',
        '/auth/verify-email',
        '/auth/google',
      ].some((path) => requestUrl.includes(path));
      if (!isAuthEndpoint && invalidateSession(window, error.config?.sessionToken)) {
        if (
          window.location.pathname !== '/login' &&
          window.location.pathname !== '/register' &&
          window.location.pathname !== '/'
        ) {
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  },
);

export const getAuthHeaders = () => {
  const token = localStorage.getItem('nl_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

export default api;
