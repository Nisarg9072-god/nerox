/**
 * src/services/authService.ts
 * ===========================
 * Auth API wrapper — Phase 2 Enterprise Upgrade
 *
 * Endpoints:
 *   POST /auth/register       → RegisterRequest / RegisterResponse
 *   POST /auth/login          → LoginRequest   / TokenResponse
 *   POST /auth/refresh        → RefreshRequest / TokenResponse
 *   GET  /auth/me             → UserProfile (legacy)
 *   GET  /auth/profile        → ProfileResponse
 *   PUT  /auth/profile        → ProfileUpdatePayload / ProfileResponse
 *   PATCH /auth/password      → PasswordChangePayload / { message: string }
 *   POST /auth/forgot-password → ForgotPasswordPayload / { message: string }
 *   POST /auth/reset-password  → ResetPasswordPayload / { message: string }
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

export interface ProfileUpdatePayload {
  name?: string;
  company_name?: string;
}

export interface PasswordChangePayload {
  current_password: string;
  new_password: string;
}

export interface ForgotPasswordPayload {
  email: string;
}

export interface ResetPasswordPayload {
  token: string;
  new_password: string;
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
  name: string;
  company_name: string;
  email: string;
  created_at: string | null;
  organization_id?: string | null;
  role?: 'owner' | 'admin' | 'member';
  organization_plan?: 'free' | 'pro' | 'enterprise';
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

  /** Fetch the currently authenticated user's profile (legacy). */
  async getMe(): Promise<UserProfile> {
    const { data } = await api.get<UserProfile>('/auth/me');
    return data;
  },

  // ── Phase 2: Profile Management ──────────────────────────────────────────

  /** Fetch the current user's full profile. */
  async getProfile(): Promise<UserProfile> {
    const { data } = await api.get<UserProfile>('/auth/profile');
    return data;
  },

  /** Update the current user's profile (name, company_name). */
  async updateProfile(payload: ProfileUpdatePayload): Promise<UserProfile> {
    const { data } = await api.put<UserProfile>('/auth/profile', payload);
    return data;
  },

  // ── Phase 2: Password Management ─────────────────────────────────────────

  /** Change the current user's password. */
  async changePassword(payload: PasswordChangePayload): Promise<{ message: string }> {
    const { data } = await api.patch<{ message: string }>('/auth/password', payload);
    return data;
  },

  /** Request a password reset email (simulated in dev). */
  async forgotPassword(payload: ForgotPasswordPayload): Promise<{ message: string }> {
    const { data } = await api.post<{ message: string }>('/auth/forgot-password', payload);
    return data;
  },

  /** Reset password using a token. */
  async resetPassword(payload: ResetPasswordPayload): Promise<{ message: string }> {
    const { data } = await api.post<{ message: string }>('/auth/reset-password', payload);
    return data;
  },
};
