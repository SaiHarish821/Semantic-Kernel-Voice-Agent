/**
 * app/static/auth.js — Auth helper for JWT management.
 *
 * Provides: login, register, logout, refresh, getAuthHeader, getUser
 * Stores tokens in localStorage under 'access_token' / 'refresh_token'.
 */

'use strict';

const AUTH_BASE = '/api/v1/auth';

// ── Token storage ─────────────────────────────────────────────────────────────
function getAccessToken()  { return localStorage.getItem('access_token'); }
function getRefreshToken() { return localStorage.getItem('refresh_token'); }
function getStoredUser()   { try { return JSON.parse(localStorage.getItem('auth_user')); } catch { return null; } }

function storeTokens({ access_token, refresh_token, user }) {
  localStorage.setItem('access_token', access_token);
  localStorage.setItem('refresh_token', refresh_token);
  localStorage.setItem('auth_user', JSON.stringify(user));
}

function clearTokens() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('auth_user');
}

function isLoggedIn() {
  return !!getAccessToken();
}

function getAuthHeader() {
  const token = getAccessToken();
  return token ? { 'Authorization': `Bearer ${token}` } : {};
}

// ── API helpers ───────────────────────────────────────────────────────────────
async function authFetch(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeader(),
      ...(options.headers || {}),
    },
  });
  if (res.status === 401) {
    // Try to refresh
    const refreshed = await tryRefresh();
    if (refreshed) {
      return fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeader(),
          ...(options.headers || {}),
        },
      });
    } else {
      clearTokens();
      window.location.href = '/login';
      throw new Error('Session expired');
    }
  }
  return res;
}

async function tryRefresh() {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  try {
    const res = await fetch(`${AUTH_BASE}/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (res.ok) {
      const data = await res.json();
      storeTokens(data);
      return true;
    }
  } catch {}
  return false;
}

// ── Auth actions ──────────────────────────────────────────────────────────────
async function register(name, email, password) {
  const res = await fetch(`${AUTH_BASE}/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Registration failed');
  storeTokens(data);
  return data;
}

async function login(email, password) {
  const res = await fetch(`${AUTH_BASE}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Login failed');
  storeTokens(data);
  return data;
}

async function logout() {
  try {
    await authFetch(`${AUTH_BASE}/logout`, { method: 'POST' });
  } catch {}
  clearTokens();
  window.location.href = '/login';
}

async function getMe() {
  const res = await authFetch(`${AUTH_BASE}/me`);
  if (!res.ok) throw new Error('Not authenticated');
  return res.json();
}

// ── Guard helpers (call at top of protected pages) ────────────────────────────
function requireAuth(redirectTo = '/login') {
  if (!isLoggedIn()) {
    window.location.href = redirectTo;
    return false;
  }
  return true;
}

function requireAdmin(redirectTo = '/') {
  const user = getStoredUser();
  if (!user || user.role !== 'admin') {
    window.location.href = redirectTo;
    return false;
  }
  return true;
}
