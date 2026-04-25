import { ReactNode, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { Shield, Home, Upload, FolderOpen, AlertTriangle, BarChart3, Bell, FileCheck, Settings, LogOut, Menu, X, Radar } from 'lucide-react';
import { Button } from './ui/button';
import { ThemeToggle } from './ThemeToggle';
import { useAuth } from '../../context/AuthContext';
import { motion, AnimatePresence } from 'motion/react';

const navigation = [
  { name: 'Dashboard', href: '/dashboard', icon: Home },
  { name: 'Upload', href: '/dashboard/upload', icon: Upload },
  { name: 'Assets', href: '/dashboard/assets', icon: FolderOpen },
  { name: 'Detections', href: '/dashboard/detections', icon: AlertTriangle },
  { name: 'Auto Detect', href: '/dashboard/auto-detect', icon: Radar },
  { name: 'Analytics', href: '/dashboard/analytics', icon: BarChart3 },
  { name: 'Alerts', href: '/dashboard/alerts', icon: Bell },
  { name: 'Verification', href: '/dashboard/verification', icon: FileCheck },
  { name: 'Settings', href: '/dashboard/settings', icon: Settings },
];

export function DashboardLayout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const NavLink = ({ item, onClick }: { item: typeof navigation[0]; onClick?: () => void }) => {
    const Icon = item.icon;
    const isActive = location.pathname === item.href;
    return (
      <Link
        to={item.href}
        onClick={onClick}
        className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all text-sm font-medium ${
          isActive
            ? 'bg-primary text-primary-foreground'
            : 'hover:bg-accent text-muted-foreground hover:text-foreground'
        }`}
      >
        <Icon className="h-5 w-5 shrink-0" />
        <span className="truncate">{item.name}</span>
      </Link>
    );
  };

  const UserFooter = ({ onLogout }: { onLogout: () => void }) => (
    <div className="p-4 border-t border-border shrink-0">
      <div className="px-3 py-2 mb-2">
        <div className="text-sm font-medium truncate">{user?.companyName}</div>
        <div className="text-xs text-muted-foreground truncate">{user?.email}</div>
      </div>
      <Button
        variant="ghost"
        className="w-full justify-start gap-3 text-sm"
        onClick={onLogout}
      >
        <LogOut className="h-5 w-5 shrink-0" />
        Logout
      </Button>
    </div>
  );

  return (
    <div className="min-h-screen flex overflow-hidden">
      {/* Desktop Sidebar — fixed, hidden on mobile */}
      <aside className="hidden md:flex md:flex-col w-64 shrink-0 border-r border-border bg-card">
        <div className="h-16 flex items-center px-6 border-b border-border shrink-0">
          <Link to="/dashboard" className="flex items-center gap-2 min-w-0">
            <Shield className="h-6 w-6 shrink-0" />
            <span className="text-xl font-semibold truncate">Nerox</span>
          </Link>
        </div>

        <nav className="flex-1 px-4 py-4 space-y-0.5 overflow-y-auto">
          {navigation.map((item) => (
            <NavLink key={item.name} item={item} />
          ))}
        </nav>

        <UserFooter onLogout={handleLogout} />
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Header */}
        <header className="h-16 border-b border-border bg-card flex items-center justify-between px-4 sm:px-6 shrink-0 z-30 relative">
          <div className="flex items-center gap-3">
            {/* Hamburger — mobile only */}
            <Button
              variant="ghost"
              size="sm"
              className="md:hidden p-2 h-auto"
              onClick={() => setMobileMenuOpen(true)}
              aria-label="Open navigation menu"
            >
              <Menu className="h-5 w-5" />
            </Button>
            <Link to="/dashboard" className="md:hidden flex items-center gap-2">
              <Shield className="h-5 w-5" />
              <span className="text-lg font-semibold">Nerox</span>
            </Link>
          </div>
          <div className="flex items-center gap-3 ml-auto">
            <ThemeToggle />
          </div>
        </header>

        <main className="flex-1 overflow-auto bg-background">
          {children}
        </main>
      </div>

      {/* Mobile Slide-in Drawer */}
      <AnimatePresence>
        {mobileMenuOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="fixed inset-0 bg-background/80 backdrop-blur-sm z-40 md:hidden"
              onClick={() => setMobileMenuOpen(false)}
              aria-hidden="true"
            />
            {/* Drawer */}
            <motion.div
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ type: 'spring', damping: 30, stiffness: 300 }}
              className="fixed inset-y-0 left-0 w-72 max-w-[85vw] bg-card border-r border-border z-50 md:hidden flex flex-col shadow-2xl"
            >
              <div className="h-16 flex items-center justify-between px-6 border-b border-border shrink-0">
                <Link
                  to="/dashboard"
                  className="flex items-center gap-2"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  <Shield className="h-6 w-6 shrink-0" />
                  <span className="text-xl font-semibold">Nerox</span>
                </Link>
                <Button
                  variant="ghost"
                  size="sm"
                  className="p-2 h-auto"
                  onClick={() => setMobileMenuOpen(false)}
                  aria-label="Close navigation menu"
                >
                  <X className="h-5 w-5" />
                </Button>
              </div>

              <nav className="flex-1 px-4 py-4 space-y-0.5 overflow-y-auto">
                {navigation.map((item) => (
                  <NavLink
                    key={item.name}
                    item={item}
                    onClick={() => setMobileMenuOpen(false)}
                  />
                ))}
              </nav>

              <UserFooter onLogout={handleLogout} />
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
