import { createBrowserRouter, Navigate } from 'react-router';
import { useAuth } from '../context/AuthContext';
import Landing from './pages/Landing';
import Features from './pages/Features';
import Demo from './pages/Demo';
import Pricing from './pages/Pricing';
import About from './pages/About';
import Contact from './pages/Contact';
import Login from './pages/Login';
import Register from './pages/Register';
import { DashboardLayout } from './components/DashboardLayout';
import DashboardHome from './pages/dashboard/DashboardHome';
import Upload from './pages/dashboard/Upload';
import Assets from './pages/dashboard/Assets';
import Detections from './pages/dashboard/Detections';
import Analytics from './pages/dashboard/Analytics';
import Alerts from './pages/dashboard/Alerts';
import Verification from './pages/dashboard/Verification';
import Settings from './pages/dashboard/Settings';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

export const router = createBrowserRouter([
  {
    path: '/',
    Component: Landing,
  },
  {
    path: '/features',
    Component: Features,
  },
  {
    path: '/demo',
    Component: Demo,
  },
  {
    path: '/pricing',
    Component: Pricing,
  },
  {
    path: '/about',
    Component: About,
  },
  {
    path: '/contact',
    Component: Contact,
  },
  {
    path: '/login',
    Component: Login,
  },
  {
    path: '/register',
    Component: Register,
  },
  {
    path: '/dashboard',
    element: (
      <ProtectedRoute>
        <DashboardLayout>
          <DashboardHome />
        </DashboardLayout>
      </ProtectedRoute>
    ),
  },
  {
    path: '/dashboard/upload',
    element: (
      <ProtectedRoute>
        <DashboardLayout>
          <Upload />
        </DashboardLayout>
      </ProtectedRoute>
    ),
  },
  {
    path: '/dashboard/assets',
    element: (
      <ProtectedRoute>
        <DashboardLayout>
          <Assets />
        </DashboardLayout>
      </ProtectedRoute>
    ),
  },
  {
    path: '/dashboard/detections',
    element: (
      <ProtectedRoute>
        <DashboardLayout>
          <Detections />
        </DashboardLayout>
      </ProtectedRoute>
    ),
  },
  {
    path: '/dashboard/analytics',
    element: (
      <ProtectedRoute>
        <DashboardLayout>
          <Analytics />
        </DashboardLayout>
      </ProtectedRoute>
    ),
  },
  {
    path: '/dashboard/alerts',
    element: (
      <ProtectedRoute>
        <DashboardLayout>
          <Alerts />
        </DashboardLayout>
      </ProtectedRoute>
    ),
  },
  {
    path: '/dashboard/verification',
    element: (
      <ProtectedRoute>
        <DashboardLayout>
          <Verification />
        </DashboardLayout>
      </ProtectedRoute>
    ),
  },
  {
    path: '/dashboard/settings',
    element: (
      <ProtectedRoute>
        <DashboardLayout>
          <Settings />
        </DashboardLayout>
      </ProtectedRoute>
    ),
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);
