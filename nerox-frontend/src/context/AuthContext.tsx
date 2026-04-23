/**
 * src/context/AuthContext.tsx
 * ============================
 * Production auth context — connected to the real Nerox FastAPI backend.
 *
 * Flow:
 *   login()    → POST /auth/login → store JWT → GET /auth/me → store user
 *   register() → POST /auth/register → POST /auth/login (auto) → same as above
 *   logout()   → clear localStorage
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

type AuthContextType = {
  user: UserProfile | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (companyName: string, email: string, password: string) => Promise<void>;
  logout: () => void;
};

// ── Context ──────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// ── Provider ─────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(() => {
    try {
      const stored = localStorage.getItem('nerox_user');
      return stored ? (JSON.parse(stored) as UserProfile) : null;
    } catch {
      return null;
    }
  });

  const [isLoading, setIsLoading] = useState(false);

  /** Persist tokens + user; update state. */
  const _storeSession = useCallback((token: string, refreshToken: string, profile: UserProfile) => {
    localStorage.setItem('nerox_token', token);
    localStorage.setItem('nerox_refresh_token', refreshToken);
    localStorage.setItem('nerox_user', JSON.stringify(profile));
    setUser(profile);
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

      // 3. Fetch full profile
      const profile = await authService.getMe();

      // 4. Finalize session
      _storeSession(tokenResp.access_token, tokenResp.refresh_token, profile);
      toast.success(`Welcome back, ${profile.company_name}!`);
    } catch (err: any) {
      // Re-throw so the Login page can display the message
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
        const profile = await authService.getMe();
        _storeSession(tokenResp.access_token, tokenResp.refresh_token, profile);

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
