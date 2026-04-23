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
import { lazy, Suspense, type ComponentType } from 'react';
import { useAuth } from '../context/AuthContext';
import { DashboardLayout } from './components/DashboardLayout';

const Landing = lazy(() => import('./pages/Landing'));
const Features = lazy(() => import('./pages/Features'));
const Demo = lazy(() => import('./pages/Demo'));
const Pricing = lazy(() => import('./pages/Pricing'));
const About = lazy(() => import('./pages/About'));
const Contact = lazy(() => import('./pages/Contact'));
const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'));
const ResetPassword = lazy(() => import('./pages/ResetPassword'));
const DashboardHome = lazy(() => import('./pages/dashboard/DashboardHome'));
const Upload = lazy(() => import('./pages/dashboard/Upload'));
const Assets = lazy(() => import('./pages/dashboard/Assets'));
const Detections = lazy(() => import('./pages/dashboard/Detections'));
const Analytics = lazy(() => import('./pages/dashboard/Analytics'));
const Alerts = lazy(() => import('./pages/dashboard/Alerts'));
const Verification = lazy(() => import('./pages/dashboard/Verification'));
const Settings = lazy(() => import('./pages/dashboard/Settings'));
const AutoDetection = lazy(() => import('./pages/dashboard/AutoDetection'));

function withSuspense(Component: ComponentType) {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-muted-foreground">Loading…</div>}>
      <Component />
    </Suspense>
  );
}

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
  { path: '/',               element: withSuspense(Landing) },
  { path: '/features',       element: withSuspense(Features) },
  { path: '/demo',           element: withSuspense(Demo) },
  { path: '/pricing',        element: withSuspense(Pricing) },
  { path: '/about',          element: withSuspense(About) },
  { path: '/contact',        element: withSuspense(Contact) },
  { path: '/login',          element: withSuspense(Login) },
  { path: '/register',       element: withSuspense(Register) },
  { path: '/forgot-password', element: withSuspense(ForgotPassword) },
  { path: '/reset-password',  element: withSuspense(ResetPassword) },

  // ── Protected dashboard routes (nested layout) ────────────────────────────
  {
    element: <ProtectedRoute />,
    children: [
      {
        path: '/dashboard',
        element: <ProtectedDashboard />,
        children: [
          { index: true,           element: withSuspense(DashboardHome) },
          { path: 'upload',        element: withSuspense(Upload) },
          { path: 'assets',        element: withSuspense(Assets) },
          { path: 'detections',    element: withSuspense(Detections) },
          { path: 'auto-detect',   element: withSuspense(AutoDetection) },
          { path: 'analytics',     element: withSuspense(Analytics) },
          { path: 'alerts',        element: withSuspense(Alerts) },
          { path: 'verification',  element: withSuspense(Verification) },
          { path: 'settings',      element: withSuspense(Settings) },
        ],
      },
    ],
  },

  // ── Catch-all ──────────────────────────────────────────────────────────────
  { path: '*', element: <Navigate to="/" replace /> },
]);
