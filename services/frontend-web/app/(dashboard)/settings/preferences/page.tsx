'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { organizationAPI, Organization, OrganizationStats } from '@/lib/api/organization';
import { preferencesAPI, Preferences } from '@/lib/api/preferences';
import { accountAPI } from '@/lib/api/account';
import { useTheme } from '@/contexts/ThemeContext';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { StatCard } from '@/components/StatCard';
import {
  Building2,
  Calendar,
  Users,
  MessageSquare,
  Crown,
  Edit3,
  Check,
  X,
  Settings as SettingsIcon,
  Palette,
  Monitor,
  Sun,
  Moon,
  Bell,
  AlertTriangle,
  Download,
  Trash2,
  Shield,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';

export default function PreferencesPage() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const [mounted, setMounted] = useState(false);
  const [org, setOrg] = useState<Organization | null>(null);
  const [stats, setStats] = useState<OrganizationStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [editedOrgName, setEditedOrgName] = useState('');
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [savingDigest, setSavingDigest] = useState(false);
  const [savingAlerts, setSavingAlerts] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  // Always call useTheme (Rules of Hooks) — values are safe to read after mount
  const { theme: currentTheme, setTheme } = useTheme();
  const theme = mounted ? currentTheme : 'system';

  // Helper to get role display name
  const getRoleDisplayName = (role: string) => {
    switch (role) {
      case 'owner': return 'Owner';
      case 'admin': return 'Administrator';
      case 'member': return 'Member';
      default: return role;
    }
  };

  // Helper to get role color
  const getRoleColor = (role: string) => {
    switch (role) {
      case 'owner': return 'var(--chart-5)'; // Purple
      case 'admin': return 'var(--chart-2)'; // Amber
      case 'member': return 'var(--muted-foreground)';
      default: return 'var(--muted-foreground)';
    }
  };

  // Only admin/owner can edit organization details
  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const token = localStorage.getItem('access_token');
        if (!token) {
          router.push('/login');
          return;
        }

        const [orgData, statsData, prefsData] = await Promise.all([
          organizationAPI.getMe(),
          organizationAPI.getStats(),
          preferencesAPI.get(),
        ]);

        setOrg(orgData);
        setStats(statsData);
        setPreferences(prefsData);
        setEditedOrgName(orgData.name);
      } catch (err) {
        console.error('Failed to load organization data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [router]);

  const handleToggleDigest = async (checked: boolean) => {
    setSavingDigest(true);
    try {
      const updated = await preferencesAPI.update({ weekly_digest_enabled: checked });
      setPreferences(updated);
    } catch (err) {
      console.error('Failed to update preferences:', err);
    } finally {
      setSavingDigest(false);
    }
  };

  const handleToggleAlertChannel = async (channel: 'dashboard' | 'email' | 'slack', checked: boolean) => {
    setSavingAlerts(true);
    try {
      const currentChannels = preferences?.alert_channels || { dashboard: true, email: false, slack: false };
      const updated = await preferencesAPI.update({
        alert_channels: { ...currentChannels, [channel]: checked },
      });
      setPreferences(updated);
    } catch (err) {
      console.error('Failed to update alert channels:', err);
    } finally {
      setSavingAlerts(false);
    }
  };

  const handleSaveOrgName = async () => {
    try {
      await organizationAPI.update({ name: editedOrgName });
      const updatedOrg = await organizationAPI.getMe();
      setOrg(updatedOrg);
      setIsEditing(false);
    } catch (err) {
      console.error('Failed to update organization:', err);
    }
  };

  const handleCancelEdit = () => {
    setEditedOrgName(org?.name || '');
    setIsEditing(false);
  };

  const handleExportData = async () => {
    setExportLoading(true);
    try {
      await accountAPI.exportData();
    } catch (err) {
      console.error('Failed to export data:', err);
    } finally {
      setExportLoading(false);
    }
  };

  const handleDeleteAccount = async () => {
    setDeleteLoading(true);
    try {
      await accountAPI.requestDeletion();
      setDeleteDialogOpen(false);
      logout();
      router.push('/login');
    } catch (err) {
      console.error('Failed to request deletion:', err);
      setDeleteLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 border-4 border-primary/20 rounded-full"></div>
            <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
          </div>
          <p className="text-muted-foreground font-medium">Loading preferences...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Page Header */}
        <div className="animate-fade-in">
          <div className="flex items-center space-x-3 mb-6">
            <div className="p-3 bg-secondary rounded-xl">
              <SettingsIcon className="w-8 h-8 text-primary" />
            </div>
            <div>
              <h1 className="text-4xl font-bold text-foreground">Settings</h1>
              <p className="text-muted-foreground text-lg">Manage your organization and preferences</p>
            </div>
          </div>

        </div>

        {/* Theme Preference */}
        <Card className="animate-slide-up stagger-1">
          <CardHeader className="border-b border-border">
            <div className="flex items-center space-x-2">
              <div className="p-2 bg-secondary rounded-lg">
                <Palette className="w-5 h-5 text-primary" />
              </div>
              <CardTitle>Appearance</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            <ToggleGroup
              type="single"
              value={theme}
              onValueChange={(value) => value && setTheme(value as 'system' | 'light' | 'dark')}
              className="grid grid-cols-3 gap-4"
            >
              <ToggleGroupItem
                value="system"
                aria-label="System theme"
                className="flex flex-col items-center gap-2 p-6 h-auto border-2 text-foreground data-[state=on]:border-primary data-[state=on]:bg-primary/10 data-[state=on]:text-primary rounded-xl"
              >
                <div className="p-3 bg-secondary rounded-xl">
                  <Monitor className="w-6 h-6" />
                </div>
                <span className="font-semibold">System</span>
              </ToggleGroupItem>
              <ToggleGroupItem
                value="light"
                aria-label="Light theme"
                className="flex flex-col items-center gap-2 p-6 h-auto border-2 text-foreground data-[state=on]:border-primary data-[state=on]:bg-primary/10 data-[state=on]:text-primary rounded-xl"
              >
                <div className="p-3 bg-secondary rounded-xl">
                  <Sun className="w-6 h-6" />
                </div>
                <span className="font-semibold">Light</span>
              </ToggleGroupItem>
              <ToggleGroupItem
                value="dark"
                aria-label="Dark theme"
                className="flex flex-col items-center gap-2 p-6 h-auto border-2 text-foreground data-[state=on]:border-primary data-[state=on]:bg-primary/10 data-[state=on]:text-primary rounded-xl"
              >
                <div className="p-3 bg-secondary rounded-xl">
                  <Moon className="w-6 h-6" />
                </div>
                <span className="font-semibold">Dark</span>
              </ToggleGroupItem>
            </ToggleGroup>
          </CardContent>
        </Card>

        {/* Notifications */}
        <Card className="animate-slide-up stagger-2">
          <CardHeader className="border-b border-border">
            <div className="flex items-center space-x-2">
              <div className="p-2 bg-secondary rounded-lg">
                <Bell className="w-5 h-5 text-primary" />
              </div>
              <CardTitle>Notifications</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-foreground">Weekly Digest</p>
                <p className="text-sm text-muted-foreground">
                  Receive a weekly email summary of feedback trends every Monday at 9 AM UTC
                </p>
              </div>
              <Switch
                checked={preferences?.weekly_digest_enabled ?? true}
                onCheckedChange={handleToggleDigest}
                disabled={savingDigest}
              />
            </div>
          </CardContent>
        </Card>

        {/* Alert Channels */}
        <Card className="animate-slide-up stagger-3">
          <CardHeader className="border-b border-border">
            <div className="flex items-center space-x-2">
              <div className="p-2 bg-secondary rounded-lg">
                <AlertTriangle className="w-5 h-5 text-primary" />
              </div>
              <div>
                <CardTitle>Alert Channels</CardTitle>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Choose how you receive anomaly and spike alerts
                </p>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-6 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-foreground">Dashboard</p>
                <p className="text-sm text-muted-foreground">
                  Show anomaly banners on the dashboard
                </p>
              </div>
              <Switch
                checked={preferences?.alert_channels?.dashboard ?? true}
                onCheckedChange={(checked) => handleToggleAlertChannel('dashboard', checked)}
                disabled={savingAlerts}
              />
            </div>
            <div className="border-t border-border" />
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-foreground">Email</p>
                <p className="text-sm text-muted-foreground">
                  Receive email alerts when sentiment spikes are detected
                </p>
              </div>
              <Switch
                checked={preferences?.alert_channels?.email ?? false}
                onCheckedChange={(checked) => handleToggleAlertChannel('email', checked)}
                disabled={savingAlerts}
              />
            </div>
            <div className="border-t border-border" />
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-foreground">Slack</p>
                <p className="text-sm text-muted-foreground">
                  Send anomaly alerts to your connected Slack channel
                </p>
              </div>
              <Switch
                checked={preferences?.alert_channels?.slack ?? false}
                onCheckedChange={(checked) => handleToggleAlertChannel('slack', checked)}
                disabled={savingAlerts}
              />
            </div>
          </CardContent>
        </Card>

        {/* Organization Details */}
        <Card className="animate-slide-up stagger-4">
          <CardHeader className="border-b border-border">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <div className="p-2 bg-secondary rounded-lg">
                  <Building2 className="w-5 h-5 text-primary" />
                </div>
                <CardTitle>Organization Details</CardTitle>
              </div>
              {isAdminOrOwner && !isEditing && (
                <Button
                  onClick={() => setIsEditing(true)}
                  variant="outline"
                  size="sm"
                  className="flex items-center space-x-2"
                >
                  <Edit3 className="w-4 h-4" />
                  <span>Edit</span>
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Organization Name */}
              <div>
                <label className="block text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                  Organization Name
                </label>
                {isEditing ? (
                  <div className="space-y-3">
                    <Input
                      type="text"
                      value={editedOrgName}
                      onChange={(e) => setEditedOrgName(e.target.value)}
                      className="h-10"
                    />
                    <div className="flex gap-2">
                      <Button
                        onClick={handleSaveOrgName}
                        variant="default"
                        size="sm"
                        className="flex items-center space-x-2"
                      >
                        <Check className="w-4 h-4" />
                        <span>Save</span>
                      </Button>
                      <Button
                        onClick={handleCancelEdit}
                        variant="outline"
                        size="sm"
                        className="flex items-center space-x-2"
                      >
                        <X className="w-4 h-4" />
                        <span>Cancel</span>
                      </Button>
                    </div>
                  </div>
                ) : (
                  <p className="text-lg font-semibold text-foreground">{org?.name}</p>
                )}
              </div>

              {/* Plan */}
              <div>
                <label className="block text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                  Subscription Plan
                </label>
                <div className="inline-flex items-center space-x-2">
                  <Crown className="w-5 h-5 text-primary" />
                  <span
                    className="px-3 py-1 rounded-lg text-sm font-bold capitalize"
                    style={{
                      backgroundColor: 'color-mix(in oklch, var(--primary) 15%, transparent)',
                      color: 'var(--primary)'
                    }}
                  >
                    {org?.plan}
                  </span>
                </div>
              </div>

              {/* Created At */}
              <div>
                <label className="block text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                  Organization Created
                </label>
                <div className="flex items-center space-x-2">
                  <Calendar className="w-5 h-5 text-muted-foreground" />
                  <p className="text-foreground font-mono">
                    {org?.created_at ? new Date(org.created_at).toLocaleDateString('en-US', {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric'
                    }) : '-'}
                  </p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Usage Statistics */}
        <div className="animate-slide-up stagger-5">
          <h3 className="text-xl font-bold text-foreground mb-4 flex items-center space-x-2">
            <span>Usage Statistics</span>
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <StatCard
              title="Total Users"
              value={stats?.total_users || 0}
              icon={Users}
              color="blue"
            />
            <StatCard
              title="Total Feedback"
              value={stats?.total_feedback || 0}
              icon={MessageSquare}
              color="purple"
            />
          </div>
        </div>

        {/* Account Information */}
        <Card className="animate-slide-up stagger-6">
          <CardHeader className="border-b border-border">
            <div className="flex items-center space-x-2">
              <div className="p-2 bg-secondary rounded-lg">
                <Users className="w-5 h-5 text-primary" />
              </div>
              <CardTitle>Account Information</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                  Role
                </label>
                <span
                  className="px-3 py-1 rounded-lg text-sm font-bold"
                  style={{
                    backgroundColor: `color-mix(in oklch, ${getRoleColor(user?.role || 'member')} 15%, transparent)`,
                    color: getRoleColor(user?.role || 'member')
                  }}
                >
                  {getRoleDisplayName(user?.role || 'member')}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Data & Privacy */}
        <Card className="animate-slide-up stagger-7">
          <CardHeader className="border-b border-border">
            <div className="flex items-center space-x-2">
              <div className="p-2 bg-secondary rounded-lg">
                <Shield className="w-5 h-5 text-primary" />
              </div>
              <div>
                <CardTitle>Data &amp; Privacy</CardTitle>
                <p className="text-sm text-muted-foreground mt-1">
                  Manage your personal data in accordance with GDPR
                </p>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="space-y-6">
              {/* Export */}
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="font-semibold text-foreground">Export My Data</h3>
                  <p className="text-sm text-muted-foreground mt-0.5">
                    Download a ZIP archive containing all your personal data — profile, feedbacks,
                    conversations, notes, and preferences.
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleExportData}
                  disabled={exportLoading}
                  className="shrink-0"
                >
                  <Download className="w-4 h-4 mr-2" />
                  {exportLoading ? 'Preparing…' : 'Export Data'}
                </Button>
              </div>

              <div className="border-t border-border" />

              {/* Delete */}
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="font-semibold text-destructive">Delete My Account</h3>
                  <p className="text-sm text-muted-foreground mt-0.5">
                    Permanently delete your account and all associated data. You have a 30-day
                    grace period to cancel after requesting deletion.
                  </p>
                </div>
                <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
                  <DialogTrigger asChild>
                    <Button variant="destructive" size="sm" className="shrink-0">
                      <Trash2 className="w-4 h-4 mr-2" />
                      Delete Account
                    </Button>
                  </DialogTrigger>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>Delete your account?</DialogTitle>
                      <DialogDescription>
                        This will permanently delete your account and all data after{' '}
                        <strong>30 days</strong>. You will be logged out immediately. You can
                        cancel within the grace period by logging back in.
                      </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                      <Button
                        variant="outline"
                        onClick={() => setDeleteDialogOpen(false)}
                        disabled={deleteLoading}
                      >
                        Cancel
                      </Button>
                      <Button
                        variant="destructive"
                        onClick={handleDeleteAccount}
                        disabled={deleteLoading}
                      >
                        {deleteLoading ? 'Scheduling deletion…' : 'Yes, delete my account'}
                      </Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              </div>
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
