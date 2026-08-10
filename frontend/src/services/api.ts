import axios from 'axios';
import { getAccessToken, refreshAccessToken, setAccessToken } from './authSession';

const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const request = error.config as (typeof error.config & { _retried?: boolean });
    if (error.response?.status === 401 && request && !request._retried) {
      request._retried = true;
      const token = await refreshAccessToken();
      if (token) {
        request.headers.Authorization = `Bearer ${token}`;
        return api(request);
      }
      setAccessToken(null);
      if (!window.location.pathname.startsWith('/login')) window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
