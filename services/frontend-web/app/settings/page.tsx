'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { organizationAPI, Organization, OrganizationStats } from '@/lib/api/organization';
import { authAPI } from '@/lib/api/auth';
import { useTheme } from '@/contexts/ThemeContext';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatCard } from '@/components/StatCard';
import { Header } from '@/components/Header';
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
  Moon
} from 'lucide-react';
import Link from 'next/link';

export default function SettingsPage() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [org, setOrg] = useState<Organization | null>(null);
  const [stats, setStats] = useState<OrganizationStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [editedOrgName, setEditedOrgName] = useState('');

  // Only access theme context after mounting (client-side only)
  const themeContext = mounted ? useTheme() : { theme: 'system', setTheme: () => {} };
  const { theme, setTheme } = themeContext;

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

        const [orgData, statsData] = await Promise.all([
          organizationAPI.getMe(),
          organizationAPI.getStats()
        ]);

        setOrg(orgData);
        setStats(statsData);
        setEditedOrgName(orgData.name);
      } catch (err) {
        console.error('Failed to load organization data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [router]);

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

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 border-4 border-accent-amber-200 rounded-full"></div>
            <div className="absolute inset-0 border-4 border-accent-amber-500 border-t-transparent rounded-full animate-spin"></div>
          </div>
          <p className="text-text-secondary font-medium">Loading settings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <Header />

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Page Header */}
        <div className="animate-fade-in">
          <div className="flex items-center space-x-3 mb-2">
            <div className="p-3 bg-accent-amber-100 rounded-xl">
              <SettingsIcon className="w-8 h-8 text-accent-amber-700" />
            </div>
            <div>
              <h1 className="text-4xl font-bold text-text-primary">Settings</h1>
              <p className="text-text-secondary text-lg">Manage your organization and preferences</p>
            </div>
          </div>
        </div>

        {/* Theme Preference */}
        <div className="surface-raised rounded-2xl overflow-hidden border border-border-subtle animate-slide-up stagger-1">
          <div className="px-5 py-3 border-b border-border" style={{ backgroundColor: 'var(--background-secondary)' }}>
            <div className="flex items-center space-x-2">
              <div className="p-1.5 bg-accent-amber-100 rounded-lg">
                <Palette className="w-4 h-4 text-accent-amber-700" />
              </div>
              <h3 className="text-base font-bold text-text-primary">Appearance</h3>
            </div>
          </div>
          <div className="p-4">
            <div className="grid grid-cols-3 gap-2">
              {/* System Theme Option */}
              <button
                onClick={() => setTheme('system')}
                className={`relative p-3 rounded-lg border-2 transition-all group ${
                  theme === 'system'
                    ? 'border-accent-amber-500 bg-accent-amber-50'
                    : 'border-border hover:border-accent-amber-300 bg-surface'
                }`}
              >
                <div className="flex flex-col items-center space-y-2">
                  <div className={`p-2 rounded-lg transition-colors ${
                    theme === 'system' ? 'bg-accent-amber-100' : 'bg-background-secondary'
                  }`}>
                    <Monitor className={`w-5 h-5 ${
                      theme === 'system' ? 'text-accent-amber-700' : 'text-text-secondary'
                    }`} />
                  </div>
                  <p className={`text-sm font-semibold ${
                    theme === 'system' ? 'text-accent-amber-700' : 'text-text-primary'
                  }`}>
                    System
                  </p>
                </div>
                {theme === 'system' && (
                  <div className="absolute top-2 right-2 w-4 h-4 bg-accent-amber-500 rounded-full flex items-center justify-center">
                    <Check className="w-2.5 h-2.5 text-white" />
                  </div>
                )}
              </button>

              {/* Light Theme Option */}
              <button
                onClick={() => setTheme('light')}
                className={`relative p-3 rounded-lg border-2 transition-all group ${
                  theme === 'light'
                    ? 'border-accent-amber-500 bg-accent-amber-50'
                    : 'border-border hover:border-accent-amber-300 bg-surface'
                }`}
              >
                <div className="flex flex-col items-center space-y-2">
                  <div className={`p-2 rounded-lg transition-colors ${
                    theme === 'light' ? 'bg-accent-amber-100' : 'bg-background-secondary'
                  }`}>
                    <Sun className={`w-5 h-5 ${
                      theme === 'light' ? 'text-accent-amber-700' : 'text-text-secondary'
                    }`} />
                  </div>
                  <p className={`text-sm font-semibold ${
                    theme === 'light' ? 'text-accent-amber-700' : 'text-text-primary'
                  }`}>
                    Light
                  </p>
                </div>
                {theme === 'light' && (
                  <div className="absolute top-2 right-2 w-4 h-4 bg-accent-amber-500 rounded-full flex items-center justify-center">
                    <Check className="w-2.5 h-2.5 text-white" />
                  </div>
                )}
              </button>

              {/* Dark Theme Option */}
              <button
                onClick={() => setTheme('dark')}
                className={`relative p-3 rounded-lg border-2 transition-all group ${
                  theme === 'dark'
                    ? 'border-accent-amber-500 bg-accent-amber-50'
                    : 'border-border hover:border-accent-amber-300 bg-surface'
                }`}
              >
                <div className="flex flex-col items-center space-y-2">
                  <div className={`p-2 rounded-lg transition-colors ${
                    theme === 'dark' ? 'bg-accent-amber-100' : 'bg-background-secondary'
                  }`}>
                    <Moon className={`w-5 h-5 ${
                      theme === 'dark' ? 'text-accent-amber-700' : 'text-text-secondary'
                    }`} />
                  </div>
                  <p className={`text-sm font-semibold ${
                    theme === 'dark' ? 'text-accent-amber-700' : 'text-text-primary'
                  }`}>
                    Dark
                  </p>
                </div>
                {theme === 'dark' && (
                  <div className="absolute top-2 right-2 w-4 h-4 bg-accent-amber-500 rounded-full flex items-center justify-center">
                    <Check className="w-2.5 h-2.5 text-white" />
                  </div>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Organization Details */}
        <div className="surface-raised rounded-2xl overflow-hidden border border-border-subtle animate-slide-up stagger-2">
          <div className="px-6 py-4 border-b border-border" style={{ backgroundColor: 'var(--background-secondary)' }}>
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <div className="p-2 bg-accent-amber-100 rounded-lg">
                  <Building2 className="w-5 h-5 text-accent-amber-700" />
                </div>
                <h3 className="text-lg font-bold text-text-primary">Organization Details</h3>
              </div>
              {!isEditing && (
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
          </div>
          <div className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Organization Name */}
              <div>
                <label className="block text-sm font-semibold text-text-secondary uppercase tracking-wider mb-2">
                  Organization Name
                </label>
                {isEditing ? (
                  <div className="space-y-3">
                    <input
                      type="text"
                      value={editedOrgName}
                      onChange={(e) => setEditedOrgName(e.target.value)}
                      className="w-full px-4 py-2.5 bg-background-secondary border border-border rounded-xl text-text-primary placeholder:text-text-tertiary focus:ring-2 focus:ring-accent-amber-500 focus:border-accent-amber-500 transition-all"
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
                  <p className="text-lg font-semibold text-text-primary">{org?.name}</p>
                )}
              </div>

              {/* Plan */}
              <div>
                <label className="block text-sm font-semibold text-text-secondary uppercase tracking-wider mb-2">
                  Subscription Plan
                </label>
                <div className="flex items-center space-x-2">
                  <Crown className="w-5 h-5 text-accent-amber-500" />
                  <span className="px-3 py-1 bg-accent-amber-100 text-accent-amber-700 rounded-lg text-sm font-bold capitalize">
                    {org?.plan}
                  </span>
                </div>
              </div>

              {/* Created At */}
              <div>
                <label className="block text-sm font-semibold text-text-secondary uppercase tracking-wider mb-2">
                  Organization Created
                </label>
                <div className="flex items-center space-x-2">
                  <Calendar className="w-5 h-5 text-text-tertiary" />
                  <p className="text-text-primary font-mono">
                    {org?.created_at ? new Date(org.created_at).toLocaleDateString('en-US', {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric'
                    }) : '-'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Usage Statistics */}
        <div className="animate-slide-up stagger-3">
          <h3 className="text-xl font-bold text-text-primary mb-4 flex items-center space-x-2">
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
        <div className="surface-raised rounded-2xl overflow-hidden border border-border-subtle animate-slide-up stagger-4">
          <div className="px-6 py-4 border-b border-border" style={{ backgroundColor: 'var(--background-secondary)' }}>
            <div className="flex items-center space-x-2">
              <div className="p-2 bg-accent-amber-100 rounded-lg">
                <Users className="w-5 h-5 text-accent-amber-700" />
              </div>
              <h3 className="text-lg font-bold text-text-primary">Account Information</h3>
            </div>
          </div>
          <div className="p-6">
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-text-secondary uppercase tracking-wider mb-2">
                  Role
                </label>
                <span className="px-3 py-1 bg-success-bg text-success-text rounded-lg text-sm font-bold">
                  Administrator
                </span>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
