/**
 * src/services/api.ts
 * ===================
 * Centralized Axios instance for all Nerox API calls.
 *
 * Features:
 *  - Base URL from VITE_API_BASE_URL env variable
 *  - Request interceptor: auto-attach JWT Bearer token
 *  - Response interceptor: 401 → attempt token refresh → retry original request
 *  - If refresh fails → clear session + redirect to /login
 *  - 60-second timeout for file upload operations
 *  - Queue mechanism prevents multiple simultaneous refresh calls
 */

import axios, { type AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios';

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 60_000,                     // 60s — generous for file uploads
  headers: { 'Accept': 'application/json' },
});

// ── Request interceptor: attach stored JWT ──────────────────────────────────
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('nerox_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// ── Response interceptor: auto-refresh on 401 ──────────────────────────────
//
// Flow:
//   1. A request returns 401 (access token expired)
//   2. We attempt POST /auth/refresh with the stored refresh_token
//   3. If refresh succeeds → store new tokens → retry the original request
//   4. If refresh fails → clear all tokens → redirect to /login
//
// A mutex (`_isRefreshing`) prevents multiple parallel refresh calls.
// While one refresh is in-flight, other failed requests queue up and
// are replayed once the new token arrives.

let _isRefreshing = false;
let _failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}> = [];

function _processQueue(error: unknown, token: string | null) {
  _failedQueue.forEach(({ resolve, reject }) => {
    if (token) {
      resolve(token);
    } else {
      reject(error);
    }
  });
  _failedQueue = [];
}

function _clearSessionAndRedirect() {
  localStorage.removeItem('nerox_token');
  localStorage.removeItem('nerox_refresh_token');
  localStorage.removeItem('nerox_user');
  window.location.href = '/login';
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean };

    // Only attempt refresh for 401 responses on non-auth endpoints
    if (
      error.response?.status !== 401 ||
      !originalRequest ||
      originalRequest._retry ||
      originalRequest.url?.includes('/auth/login') ||
      originalRequest.url?.includes('/auth/register') ||
      originalRequest.url?.includes('/auth/refresh')
    ) {
      // If 401 on auth endpoints, just clear and redirect
      if (
        error.response?.status === 401 &&
        localStorage.getItem('nerox_token') &&
        (originalRequest?.url?.includes('/auth/refresh') || originalRequest?._retry)
      ) {
        _clearSessionAndRedirect();
      }
      return Promise.reject(error);
    }

    // No refresh token stored → can't refresh → logout
    const refreshToken = localStorage.getItem('nerox_refresh_token');
    if (!refreshToken) {
      if (localStorage.getItem('nerox_token')) {
        _clearSessionAndRedirect();
      }
      return Promise.reject(error);
    }

    // If another refresh is already in progress, queue this request
    if (_isRefreshing) {
      return new Promise<string>((resolve, reject) => {
        _failedQueue.push({ resolve, reject });
      }).then((newToken) => {
        originalRequest.headers = { ...originalRequest.headers, Authorization: `Bearer ${newToken}` };
        return api(originalRequest);
      });
    }

    // Start the refresh
    originalRequest._retry = true;
    _isRefreshing = true;

    try {
      const { data } = await axios.post(`${BASE_URL}/auth/refresh`, {
        refresh_token: refreshToken,
      });

      const newAccessToken: string = data.access_token;
      const newRefreshToken: string = data.refresh_token;

      localStorage.setItem('nerox_token', newAccessToken);
      localStorage.setItem('nerox_refresh_token', newRefreshToken);

      _processQueue(null, newAccessToken);

      // Retry the original request with the new token
      originalRequest.headers = { ...originalRequest.headers, Authorization: `Bearer ${newAccessToken}` };
      return api(originalRequest);
    } catch (refreshError) {
      _processQueue(refreshError, null);
      _clearSessionAndRedirect();
      return Promise.reject(refreshError);
    } finally {
      _isRefreshing = false;
    }
  },
);

export default api;
