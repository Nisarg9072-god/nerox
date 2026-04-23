import { motion } from 'motion/react';
import { Building2, Bell, Shield, Key } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Input } from '../../components/ui/input';
import { Button } from '../../components/ui/button';
import { Switch } from '../../components/ui/switch';
import { useAuth } from '../../../context/AuthContext';
import { useState } from 'react';

export default function Settings() {
  const { user } = useAuth();
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [criticalAlerts, setCriticalAlerts] = useState(true);
  const [weeklyReports, setWeeklyReports] = useState(true);
  const [autoTakedown, setAutoTakedown] = useState(false);

  return (
    <div className="p-6 md:p-8 space-y-8">
      <div>
        <h1 className="text-3xl font-bold mb-2">Settings</h1>
        <p className="text-muted-foreground">Manage your account and preferences</p>
      </div>

      <div className="grid gap-6 max-w-4xl">
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
                <label className="block text-sm mb-2">Company Name</label>
                <Input defaultValue={user?.company_name} />
              </div>
              <div>
                <label className="block text-sm mb-2">Business Email</label>
                <Input type="email" defaultValue={user?.email} />
              </div>
              <div>
                <label className="block text-sm mb-2">Company Website</label>
                <Input placeholder="https://yourcompany.com" />
              </div>
              <div>
                <label className="block text-sm mb-2">Industry</label>
                <Input placeholder="Sports Media" />
              </div>
              <Button>Save Changes</Button>
            </CardContent>
          </Card>
        </motion.div>

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
                <Input type="password" placeholder="Enter current password" />
              </div>
              <div>
                <label className="block text-sm mb-2">New Password</label>
                <Input type="password" placeholder="Enter new password" />
              </div>
              <div>
                <label className="block text-sm mb-2">Confirm New Password</label>
                <Input type="password" placeholder="Confirm new password" />
              </div>
              <Button>Update Password</Button>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
