/**
 * src/app/routes.tsx
 * ===================
 * Phase 2: Refactored to nested route architecture.
 *
 * Before: Flat, redundant <ProtectedRoute><DashboardLayout><Page/></DashboardLayout></ProtectedRoute>
 * After:  Clean nested routes with shared layout — DRY + scalable.
 *
 * New routes:
 *   /forgot-password  → ForgotPassword page
 *   /reset-password   → ResetPassword page (token via query param)
 */

import { createBrowserRouter, Navigate, Outlet } from 'react-router';
import { useAuth } from '../context/AuthContext';
import Landing from './pages/Landing';
import Features from './pages/Features';
import Demo from './pages/Demo';
import Pricing from './pages/Pricing';
import About from './pages/About';
import Contact from './pages/Contact';
import Login from './pages/Login';
import Register from './pages/Register';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import { DashboardLayout } from './components/DashboardLayout';
import DashboardHome from './pages/dashboard/DashboardHome';
import Upload from './pages/dashboard/Upload';
import Assets from './pages/dashboard/Assets';
import Detections from './pages/dashboard/Detections';
import Analytics from './pages/dashboard/Analytics';
import Alerts from './pages/dashboard/Alerts';
import Verification from './pages/dashboard/Verification';
import Settings from './pages/dashboard/Settings';

/**
 * ProtectedRoute wrapper — redirects to /login if not authenticated.
 * Uses <Outlet /> for nested child routes.
 */
function ProtectedRoute() {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? <Outlet /> : <Navigate to="/login" replace />;
}

/**
 * ProtectedDashboard — wraps children in DashboardLayout.
 * Renders child routes via <Outlet /> inside the layout shell.
 */
function ProtectedDashboard() {
  return (
    <DashboardLayout>
      <Outlet />
    </DashboardLayout>
  );
}

export const router = createBrowserRouter([
  // ── Public routes ─────────────────────────────────────────────────────────
  { path: '/',               Component: Landing },
  { path: '/features',       Component: Features },
  { path: '/demo',           Component: Demo },
  { path: '/pricing',        Component: Pricing },
  { path: '/about',          Component: About },
  { path: '/contact',        Component: Contact },
  { path: '/login',          Component: Login },
  { path: '/register',       Component: Register },
  { path: '/forgot-password', Component: ForgotPassword },
  { path: '/reset-password',  Component: ResetPassword },

  // ── Protected dashboard routes (nested layout) ────────────────────────────
  {
    element: <ProtectedRoute />,
    children: [
      {
        path: '/dashboard',
        element: <ProtectedDashboard />,
        children: [
          { index: true,           Component: DashboardHome },
          { path: 'upload',        Component: Upload },
          { path: 'assets',        Component: Assets },
          { path: 'detections',    Component: Detections },
          { path: 'analytics',     Component: Analytics },
          { path: 'alerts',        Component: Alerts },
          { path: 'verification',  Component: Verification },
          { path: 'settings',      Component: Settings },
        ],
      },
    ],
  },

  // ── Catch-all ──────────────────────────────────────────────────────────────
  { path: '*', element: <Navigate to="/" replace /> },
]);
