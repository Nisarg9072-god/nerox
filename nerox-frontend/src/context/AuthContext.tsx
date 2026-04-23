/**
 * src/context/AuthContext.tsx
 * ============================
 * Production auth context — Phase 2 Enterprise Upgrade.
 *
 * Flow:
 *   login()    → POST /auth/login → store JWT → GET /auth/profile → store user
 *   register() → POST /auth/register → POST /auth/login (auto) → same as above
 *   logout()   → clear localStorage
 *   refreshUser() → GET /auth/profile → update stored profile (for settings)
 *
 * Session persistence: JWT and user profile survive page refresh via localStorage.
 * Token expiry: the Axios 401 interceptor (api.ts) auto-clears and redirects.
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from 'react';
import { authService, type UserProfile } from '../services/authService';
import { toast } from 'sonner';

// ── Types ────────────────────────────────────────────────────────────────────

/** Frontend user shape (camelCase for React conventions) */
export interface AuthUser {
  id: string;
  name: string;
  companyName: string;
  email: string;
  company_name: string;   // keep snake_case alias for backward compat
  created_at: string | null;
}

type AuthContextType = {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (companyName: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
};

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Map backend UserProfile (snake_case) to AuthUser (camelCase). */
function profileToUser(profile: UserProfile): AuthUser {
  return {
    id: profile.id,
    name: profile.name || profile.company_name || '',
    companyName: profile.company_name || '',
    company_name: profile.company_name || '',
    email: profile.email,
    created_at: profile.created_at,
  };
}

// ── Context ──────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// ── Provider ─────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    try {
      const stored = localStorage.getItem('nerox_user');
      return stored ? (JSON.parse(stored) as AuthUser) : null;
    } catch {
      return null;
    }
  });

  const [isLoading, setIsLoading] = useState(false);

  /** Persist tokens + user; update state. */
  const _storeSession = useCallback((token: string, refreshToken: string, authUser: AuthUser) => {
    localStorage.setItem('nerox_token', token);
    localStorage.setItem('nerox_refresh_token', refreshToken);
    localStorage.setItem('nerox_user', JSON.stringify(authUser));
    setUser(authUser);
  }, []);

  // ── login ─────────────────────────────────────────────────────────────────

  const login = useCallback(async (email: string, password: string) => {
    setIsLoading(true);
    try {
      // 1. Authenticate → get JWT pair
      const tokenResp = await authService.login({ email, password });

      // 2. Store access token so the next call carries Authorization header
      localStorage.setItem('nerox_token', tokenResp.access_token);
      localStorage.setItem('nerox_refresh_token', tokenResp.refresh_token);

      // 3. Fetch full profile (Phase 2: use /auth/profile instead of /auth/me)
      let profile: UserProfile;
      try {
        profile = await authService.getProfile();
      } catch {
        // Fallback to legacy /auth/me
        profile = await authService.getMe();
      }

      // 4. Finalize session
      const authUser = profileToUser(profile);
      _storeSession(tokenResp.access_token, tokenResp.refresh_token, authUser);
      toast.success(`Welcome back, ${authUser.companyName || authUser.email}!`);
    } catch (err: any) {
      const msg =
        err?.response?.data?.error ||
        err?.response?.data?.detail ||
        'Invalid email or password.';
      toast.error(msg);
      throw new Error(msg);
    } finally {
      setIsLoading(false);
    }
  }, [_storeSession]);

  // ── register ──────────────────────────────────────────────────────────────

  const register = useCallback(
    async (companyName: string, email: string, password: string) => {
      setIsLoading(true);
      try {
        // 1. Create account
        await authService.register({ company_name: companyName, email, password });

        // 2. Auto-login
        const tokenResp = await authService.login({ email, password });
        localStorage.setItem('nerox_token', tokenResp.access_token);
        localStorage.setItem('nerox_refresh_token', tokenResp.refresh_token);

        // 3. Fetch profile
        let profile: UserProfile;
        try {
          profile = await authService.getProfile();
        } catch {
          profile = await authService.getMe();
        }
        const authUser = profileToUser(profile);
        _storeSession(tokenResp.access_token, tokenResp.refresh_token, authUser);

        toast.success('Account created — welcome to Nerox!');
      } catch (err: any) {
        const msg =
          err?.response?.data?.error ||
          err?.response?.data?.detail ||
          'Registration failed. Please try again.';
        toast.error(msg);
        throw new Error(msg);
      } finally {
        setIsLoading(false);
      }
    },
    [_storeSession],
  );

  // ── logout ────────────────────────────────────────────────────────────────

  const logout = useCallback(() => {
    localStorage.removeItem('nerox_token');
    localStorage.removeItem('nerox_refresh_token');
    localStorage.removeItem('nerox_user');
    setUser(null);
    toast.info('You have been signed out.');
  }, []);

  // ── refreshUser (Phase 2) — re-fetches profile from API ────────────────────

  const refreshUser = useCallback(async () => {
    try {
      const profile = await authService.getProfile();
      const authUser = profileToUser(profile);
      localStorage.setItem('nerox_user', JSON.stringify(authUser));
      setUser(authUser);
    } catch {
      // Silent fail — user may still have a valid session
    }
  }, []);

  // ── Provider value ────────────────────────────────────────────────────────

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>');
  return ctx;
}
