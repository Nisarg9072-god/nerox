import { motion } from 'motion/react';
import { Building2, Bell, Shield, Key, Loader2, CheckCircle2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Input } from '../../components/ui/input';
import { Button } from '../../components/ui/button';
import { Switch } from '../../components/ui/switch';
import { useAuth } from '../../../context/AuthContext';
import { useState, useEffect } from 'react';
import { authService } from '../../../services/authService';
import { toast } from 'sonner';

export default function Settings() {
  const { user, refreshUser } = useAuth();

  // ── Profile state ──────────────────────────────────────────────────────────
  const [profileName, setProfileName] = useState('');
  const [profileCompany, setProfileCompany] = useState('');
  const [profileEmail, setProfileEmail] = useState('');
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileSaved, setProfileSaved] = useState(false);

  // ── Password state ─────────────────────────────────────────────────────────
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);

  // ── Notification preferences (UI-only for now) ─────────────────────────────
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [criticalAlerts, setCriticalAlerts] = useState(true);
  const [weeklyReports, setWeeklyReports] = useState(true);
  const [autoTakedown, setAutoTakedown] = useState(false);

  // Load profile data on mount
  useEffect(() => {
    async function loadProfile() {
      try {
        const profile = await authService.getProfile();
        setProfileName(profile.name || '');
        setProfileCompany(profile.company_name || '');
        setProfileEmail(profile.email || '');
      } catch {
        // Fallback to context data
        setProfileName(user?.name || user?.companyName || '');
        setProfileCompany(user?.companyName || '');
        setProfileEmail(user?.email || '');
      }
    }
    loadProfile();
  }, [user]);

  // ── Save profile handler ──────────────────────────────────────────────────
  const handleProfileSave = async () => {
    setProfileLoading(true);
    setProfileSaved(false);
    try {
      await authService.updateProfile({
        name: profileName.trim() || undefined,
        company_name: profileCompany.trim() || undefined,
      });
      setProfileSaved(true);
      toast.success('Profile updated successfully');
      // Refresh user context
      if (refreshUser) await refreshUser();
      setTimeout(() => setProfileSaved(false), 3000);
    } catch (err: any) {
      const msg = err?.response?.data?.error || err?.response?.data?.detail || 'Failed to update profile';
      toast.error(msg);
    } finally {
      setProfileLoading(false);
    }
  };

  // ── Change password handler ───────────────────────────────────────────────
  const handlePasswordChange = async () => {
    if (!currentPassword || !newPassword || !confirmPassword) {
      toast.error('Please fill in all password fields');
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error('New passwords do not match');
      return;
    }
    if (newPassword.length < 8) {
      toast.error('New password must be at least 8 characters');
      return;
    }

    setPasswordLoading(true);
    try {
      await authService.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      toast.success('Password changed successfully');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: any) {
      const msg = err?.response?.data?.error || err?.response?.data?.detail || 'Failed to change password';
      toast.error(msg);
    } finally {
      setPasswordLoading(false);
    }
  };

  return (
    <div className="p-6 md:p-8 space-y-8">
      <div>
        <h1 className="text-3xl font-bold mb-2">Settings</h1>
        <p className="text-muted-foreground">Manage your account and preferences</p>
      </div>

      <div className="grid gap-6 max-w-4xl">
        {/* ── Company Profile ───────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <Card>
            <CardHeader>
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-primary/10">
                  <Building2 className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <CardTitle>Company Profile</CardTitle>
                  <CardDescription>Update your company information</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="block text-sm mb-2">Display Name</label>
                <Input
                  id="settings-profile-name"
                  value={profileName}
                  onChange={(e) => setProfileName(e.target.value)}
                  placeholder="Your name"
                />
              </div>
              <div>
                <label className="block text-sm mb-2">Company Name</label>
                <Input
                  id="settings-company-name"
                  value={profileCompany}
                  onChange={(e) => setProfileCompany(e.target.value)}
                  placeholder="Company name"
                />
              </div>
              <div>
                <label className="block text-sm mb-2">Business Email</label>
                <Input
                  id="settings-email"
                  type="email"
                  value={profileEmail}
                  disabled
                  className="opacity-60"
                />
                <p className="text-xs text-muted-foreground mt-1">Email cannot be changed</p>
              </div>
              <Button
                id="settings-save-profile"
                onClick={handleProfileSave}
                disabled={profileLoading}
              >
                {profileLoading ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Saving...</>
                ) : profileSaved ? (
                  <><CheckCircle2 className="h-4 w-4 mr-2" /> Saved!</>
                ) : (
                  'Save Changes'
                )}
              </Button>
            </CardContent>
          </Card>
        </motion.div>

        {/* ── Notification Preferences ──────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <Card>
            <CardHeader>
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-primary/10">
                  <Bell className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <CardTitle>Notification Preferences</CardTitle>
                  <CardDescription>Choose how you want to be notified</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Email Notifications</div>
                  <div className="text-sm text-muted-foreground">Receive updates via email</div>
                </div>
                <Switch checked={emailNotifications} onCheckedChange={setEmailNotifications} />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Critical Alerts</div>
                  <div className="text-sm text-muted-foreground">Immediate notifications for high-risk detections</div>
                </div>
                <Switch checked={criticalAlerts} onCheckedChange={setCriticalAlerts} />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Weekly Reports</div>
                  <div className="text-sm text-muted-foreground">Summary of protection activity</div>
                </div>
                <Switch checked={weeklyReports} onCheckedChange={setWeeklyReports} />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Detection Updates</div>
                  <div className="text-sm text-muted-foreground">Get notified of new detections</div>
                </div>
                <Switch defaultChecked />
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* ── Protection Settings ───────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <Card>
            <CardHeader>
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-primary/10">
                  <Shield className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <CardTitle>Protection Settings</CardTitle>
                  <CardDescription>Configure automated protection actions</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Auto Watermarking</div>
                  <div className="text-sm text-muted-foreground">Automatically watermark uploads</div>
                </div>
                <Switch defaultChecked />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">AI Fingerprinting</div>
                  <div className="text-sm text-muted-foreground">Create digital signatures for all assets</div>
                </div>
                <Switch defaultChecked />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Automated Takedown</div>
                  <div className="text-sm text-muted-foreground">Auto-request removal of detected content</div>
                </div>
                <Switch checked={autoTakedown} onCheckedChange={setAutoTakedown} />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Continuous Monitoring</div>
                  <div className="text-sm text-muted-foreground">24/7 platform scanning</div>
                </div>
                <Switch defaultChecked />
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* ── Security / Password ───────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <Card>
            <CardHeader>
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-primary/10">
                  <Key className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <CardTitle>Security</CardTitle>
                  <CardDescription>Update your password and security settings</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="block text-sm mb-2">Current Password</label>
                <Input
                  id="settings-current-password"
                  type="password"
                  placeholder="Enter current password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-sm mb-2">New Password</label>
                <Input
                  id="settings-new-password"
                  type="password"
                  placeholder="Enter new password (min 8 chars, 1 uppercase, 1 digit, 1 special)"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-sm mb-2">Confirm New Password</label>
                <Input
                  id="settings-confirm-password"
                  type="password"
                  placeholder="Confirm new password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </div>
              {newPassword && confirmPassword && newPassword !== confirmPassword && (
                <p className="text-sm text-destructive">Passwords do not match</p>
              )}
              <Button
                id="settings-update-password"
                onClick={handlePasswordChange}
                disabled={passwordLoading || !currentPassword || !newPassword || !confirmPassword || newPassword !== confirmPassword}
              >
                {passwordLoading ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Updating...</>
                ) : (
                  'Update Password'
                )}
              </Button>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
