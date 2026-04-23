/**
 * src/services/authService.ts
 * ===========================
 * Auth API wrapper — maps exactly to:
 *   POST /auth/register  → RegisterRequest / RegisterResponse
 *   POST /auth/login     → LoginRequest   / TokenResponse
 *   GET  /auth/me        → UserProfile
 */

import api from './api';

// ── Request types ────────────────────────────────────────────────────────────

export interface RegisterPayload {
  company_name: string;
  email: string;
  password: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

// ── Response types (mirror backend Pydantic schemas) ─────────────────────────

export interface RegisterResponse {
  message: string;
  user_id: string;
  email: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserProfile {
  id: string;
  company_name: string;
  email: string;
}

// ── Service ──────────────────────────────────────────────────────────────────

export const authService = {
  /** Create a new company account. */
  async register(payload: RegisterPayload): Promise<RegisterResponse> {
    const { data } = await api.post<RegisterResponse>('/auth/register', payload);
    return data;
  },

  /** Authenticate and retrieve JWT access + refresh tokens. */
  async login(payload: LoginPayload): Promise<TokenResponse> {
    const { data } = await api.post<TokenResponse>('/auth/login', payload);
    return data;
  },

  /** Exchange a refresh token for a new access + refresh token pair. */
  async refreshToken(refreshToken: string): Promise<TokenResponse> {
    const { data } = await api.post<TokenResponse>('/auth/refresh', {
      refresh_token: refreshToken,
    });
    return data;
  },

  /** Fetch the currently authenticated user's profile. */
  async getMe(): Promise<UserProfile> {
    const { data } = await api.get<UserProfile>('/auth/me');
    return data;
  },
};
