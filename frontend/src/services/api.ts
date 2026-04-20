/**
 * API service configuration
 */

import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  timeout: 300000, // 5 minutes default timeout
  headers: {
    'Content-Type': 'application/json',
  },
});

// Token refresh lock to prevent concurrent refresh attempts
let isRefreshing = false;
let refreshSubscribers: Array<(token: string) => void> = [];

function subscribeTokenRefresh(cb: (token: string) => void) {
  refreshSubscribers.push(cb);
}

function onTokenRefreshed(token: string) {
  refreshSubscribers.forEach((cb) => cb(token));
  refreshSubscribers = [];
}

function onRefreshFailed() {
  refreshSubscribers = [];
}

// Check if a JWT token will expire within the given buffer (seconds)
function isTokenExpiringSoon(token: string, bufferSeconds: number = 60): boolean {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    const exp = payload.exp;
    if (!exp) return true;
    const nowSeconds = Math.floor(Date.now() / 1000);
    return exp - nowSeconds < bufferSeconds;
  } catch {
    return true;
  }
}

// Proactively refresh the access token (returns new token or null on failure)
async function proactiveRefresh(): Promise<string | null> {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) return null;

  // If another refresh is in progress, wait for it
  if (isRefreshing) {
    return new Promise((resolve) => {
      subscribeTokenRefresh((newToken: string) => {
        resolve(newToken);
      });
    });
  }

  isRefreshing = true;
  try {
    const response = await axios.post(`${API_URL}/api/v1/auth/refresh`, {
      refresh_token: refreshToken,
    });
    const { access_token, refresh_token } = response.data;
    localStorage.setItem('access_token', access_token);
    localStorage.setItem('refresh_token', refresh_token);
    onTokenRefreshed(access_token);
    return access_token;
  } catch {
    onRefreshFailed();
    return null;
  } finally {
    isRefreshing = false;
  }
}

// Request interceptor - attach token, proactively refresh if expiring soon
api.interceptors.request.use(
  async (config) => {
    let token = localStorage.getItem('access_token');

    // If token is about to expire (within 60s), refresh it before sending the request
    if (token && isTokenExpiringSoon(token, 60)) {
      const newToken = await proactiveRefresh();
      if (newToken) {
        token = newToken;
      }
    }

    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor - handle 401 as fallback (in case proactive refresh missed)
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Handle 401 errors - try to refresh token
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      const refreshToken = localStorage.getItem('refresh_token');
      if (!refreshToken) {
        // No refresh token - clear state and redirect to login
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/login';
        return Promise.reject(error);
      }

      // If already refreshing, queue this request to retry after refresh completes
      if (isRefreshing) {
        return new Promise((resolve) => {
          subscribeTokenRefresh((newToken: string) => {
            originalRequest.headers.Authorization = `Bearer ${newToken}`;
            resolve(api(originalRequest));
          });
        });
      }

      isRefreshing = true;

      try {
        const response = await axios.post(`${API_URL}/api/v1/auth/refresh`, {
          refresh_token: refreshToken,
        });
        const { access_token, refresh_token } = response.data;
        localStorage.setItem('access_token', access_token);
        localStorage.setItem('refresh_token', refresh_token);
        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        onTokenRefreshed(access_token);
        return api(originalRequest);
      } catch (refreshError) {
        onRefreshFailed();
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default api;
