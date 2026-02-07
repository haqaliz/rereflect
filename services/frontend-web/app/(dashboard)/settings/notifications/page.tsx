'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { notificationsAPI, AlertPreference, RetentionInfo } from '@/lib/api/notifications';
import { preferencesAPI, Preferences } from '@/lib/api/preferences';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import {
  Settings as SettingsIcon,
  Bell,
  Mail,
  Monitor,
  Sliders,
  Clock,
  Save,
} from 'lucide-react';
import { SlackIcon } from '@/components/icons/SlackIcon';

const ALERT_TYPE_CONFIG: Record<string, { label: string; description: string; hasThreshold: boolean; thresholdLabel?: string; thresholdUnit?: string }> = {
  urgent_feedback: {
    label: 'Urgent Feedback',
    description: 'Get notified when urgent or churn-risk feedback is detected',
    hasThreshold: false,
  },
  sentiment_spike: {
    label: 'Negative Sentiment Spike',
    description: 'Alert when negative sentiment exceeds your threshold',
    hasThreshold: true,
    thresholdLabel: 'Negative sentiment threshold',
    thresholdUnit: '%',
  },
  churn_risk: {
    label: 'Churn Risk Detected',
    description: 'Alert when high churn-risk feedback is identified',
    hasThreshold: false,
  },
  volume_spike: {
    label: 'Feedback Volume Spike',
    description: 'Alert when volume exceeds a multiplier of the daily average',
    hasThreshold: true,
    thresholdLabel: 'Volume multiplier threshold',
    thresholdUnit: 'x',
  },
};

const DEFAULT_PREFERENCES: AlertPreference[] = [
  { alert_type: 'urgent_feedback', is_enabled: true, channel_email: false, channel_slack: true, channel_inapp: true, threshold_value: null, retention_days: 30 },
  { alert_type: 'sentiment_spike', is_enabled: true, channel_email: false, channel_slack: true, channel_inapp: true, threshold_value: 50, retention_days: 30 },
  { alert_type: 'churn_risk', is_enabled: true, channel_email: false, channel_slack: true, channel_inapp: true, threshold_value: null, retention_days: 30 },
  { alert_type: 'volume_spike', is_enabled: true, channel_email: false, channel_slack: true, channel_inapp: true, threshold_value: 2.0, retention_days: 30 },
];

const HOUR_OPTIONS = [
  { value: '6', label: '6:00 AM UTC' },
  { value: '8', label: '8:00 AM UTC' },
  { value: '10', label: '10:00 AM UTC' },
  { value: '12', label: '12:00 PM UTC' },
  { value: '14', label: '2:00 PM UTC' },
];

const DAY_OPTIONS = [
  { value: '0', label: 'Monday' },
  { value: '1', label: 'Tuesday' },
  { value: '2', label: 'Wednesday' },
  { value: '3', label: 'Thursday' },
  { value: '4', label: 'Friday' },
  { value: '5', label: 'Saturday' },
  { value: '6', label: 'Sunday' },
];

const RETENTION_OPTIONS = [
  { value: '30', label: '30d' },
  { value: '60', label: '60d' },
  { value: '90', label: '90d' },
  { value: '180', label: '180d' },
  { value: '365', label: '1yr' },
];

export default function NotificationsSettingsPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [preferences, setPreferences] = useState<AlertPreference[]>([]);
  const [retention, setRetention] = useState<RetentionInfo | null>(null);
  const [userPrefs, setUserPrefs] = useState<Preferences | null>(null);
  const [savingPrefs, setSavingPrefs] = useState(false);
  const [savingRetention, setSavingRetention] = useState(false);
  const [savingDigest, setSavingDigest] = useState(false);
  const [retentionByType, setRetentionByType] = useState<Record<string, number>>({});
  const [hasChanges, setHasChanges] = useState(false);
  const [hasRetentionChanges, setHasRetentionChanges] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const token = localStorage.getItem('access_token');
        if (!token) {
          router.push('/login');
          return;
        }

        const [prefsData, retentionData, userPrefsData] = await Promise.all([
          notificationsAPI.getPreferences(),
          notificationsAPI.getRetention(),
          preferencesAPI.get(),
        ]);

        // Use fetched prefs or defaults if empty
        const prefs = prefsData.preferences.length > 0
          ? prefsData.preferences
          : DEFAULT_PREFERENCES;

        setPreferences(prefs);
        setRetention(retentionData);
        setUserPrefs(userPrefsData);

        // Initialize retention by type from retention response
        const retMap: Record<string, number> = {};
        if (retentionData.types) {
          for (const t of retentionData.types) {
            retMap[t.alert_type] = t.retention_days;
          }
        }
        // Fill in defaults for any missing types
        for (const p of prefs) {
          if (!(p.alert_type in retMap)) {
            retMap[p.alert_type] = p.retention_days ?? 30;
          }
        }
        setRetentionByType(retMap);
      } catch (err) {
        console.error('Failed to load notification settings:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [router]);

  const updatePref = (alertType: string, field: keyof AlertPreference, value: boolean | number | null) => {
    setPreferences(prev =>
      prev.map(p =>
        p.alert_type === alertType ? { ...p, [field]: value } : p
      )
    );
    setHasChanges(true);
  };

  const handleSavePreferences = async () => {
    setSavingPrefs(true);
    try {
      const result = await notificationsAPI.updatePreferences(preferences);
      setPreferences(result.preferences);
      setHasChanges(false);
    } catch (err) {
      console.error('Failed to save preferences:', err);
    } finally {
      setSavingPrefs(false);
    }
  };

  const handleSaveRetention = async () => {
    setSavingRetention(true);
    try {
      const retentions = Object.entries(retentionByType).map(([alert_type, days]) => ({
        alert_type,
        days,
      }));
      const result = await notificationsAPI.updateRetention(retentions);
      setRetention(result);
      setHasRetentionChanges(false);
    } catch (err) {
      console.error('Failed to update retention:', err);
    } finally {
      setSavingRetention(false);
    }
  };

  const handleToggleDailyDigest = async (checked: boolean) => {
    setSavingDigest(true);
    try {
      const updated = await preferencesAPI.update({ daily_digest_enabled: checked });
      setUserPrefs(updated);
    } catch (err) {
      console.error('Failed to update daily digest:', err);
    } finally {
      setSavingDigest(false);
    }
  };

  const handleToggleWeeklyDigest = async (checked: boolean) => {
    setSavingDigest(true);
    try {
      const updated = await preferencesAPI.update({ weekly_digest_enabled: checked });
      setUserPrefs(updated);
    } catch (err) {
      console.error('Failed to update weekly digest:', err);
    } finally {
      setSavingDigest(false);
    }
  };

  const handleUpdateDigestSchedule = async (field: string, value: number) => {
    setSavingDigest(true);
    try {
      const updated = await preferencesAPI.update({ [field]: value });
      setUserPrefs(updated);
    } catch (err) {
      console.error('Failed to update digest schedule:', err);
    } finally {
      setSavingDigest(false);
    }
  };

  // Compute total extra days and cost from retentionByType
  const totalExtraDays = Object.values(retentionByType).reduce((sum, days) => sum + Math.max(0, days - 30), 0);
  const totalMonthlyCost = totalExtraDays * 0.10;

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 border-4 border-primary/20 rounded-full"></div>
            <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
          </div>
          <p className="text-muted-foreground font-medium">Loading notification settings...</p>
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
              <h1 className="text-4xl font-bold text-foreground">Notification Settings</h1>
              <p className="text-muted-foreground text-lg">Configure how and when you receive alerts</p>
            </div>
          </div>
        </div>

        {/* Alert Preferences */}
        <Card className="animate-slide-up stagger-1">
          <CardHeader className="border-b border-border">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <div className="p-2 bg-secondary rounded-lg">
                  <Sliders className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <CardTitle>Alert Preferences</CardTitle>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Configure which alerts to receive and through which channels
                  </p>
                </div>
              </div>
              {hasChanges && (
                <Button
                  onClick={handleSavePreferences}
                  disabled={savingPrefs}
                  size="sm"
                >
                  <Save className="w-4 h-4 mr-1" />
                  {savingPrefs ? 'Saving...' : 'Save Changes'}
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            {/* Channel headers */}
            <div className="hidden sm:grid grid-cols-[1fr,60px,60px,60px] gap-4 pb-3 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              <div>Alert Type</div>
              <div className="text-center" title="In-App">
                <Monitor className="w-4 h-4 mx-auto" />
              </div>
              <div className="text-center" title="Slack">
                <SlackIcon className="w-4 h-4 mx-auto" />
              </div>
              <div className="text-center" title="Email">
                <Mail className="w-4 h-4 mx-auto" />
              </div>
            </div>

            <div className="space-y-2">
              {preferences.map(pref => {
                const config = ALERT_TYPE_CONFIG[pref.alert_type];
                if (!config) return null;

                return (
                  <div
                    key={pref.alert_type}
                    className={`rounded-lg border p-4 transition-colors ${
                      pref.is_enabled ? 'bg-background border-border' : 'bg-muted/50 border-muted opacity-60'
                    }`}
                  >
                    <div className="grid grid-cols-1 sm:grid-cols-[1fr,60px,60px,60px] gap-4 items-center">
                      {/* Alert type info + enable toggle */}
                      <div className="flex items-center justify-between sm:justify-start gap-3">
                        <Switch
                          checked={pref.is_enabled}
                          onCheckedChange={(checked) => updatePref(pref.alert_type, 'is_enabled', checked)}
                        />
                        <div className="flex-1">
                          <p className="font-medium text-foreground">{config.label}</p>
                          <p className="text-xs text-muted-foreground">{config.description}</p>
                        </div>
                      </div>

                      {/* Channel toggles */}
                      <div className="flex sm:justify-center">
                        <div className="sm:hidden text-xs text-muted-foreground mr-2">In-App</div>
                        <Switch
                          checked={pref.channel_inapp}
                          onCheckedChange={(checked) => updatePref(pref.alert_type, 'channel_inapp', checked)}
                          disabled={!pref.is_enabled}
                        />
                      </div>
                      <div className="flex sm:justify-center">
                        <div className="sm:hidden text-xs text-muted-foreground mr-2">Slack</div>
                        <Switch
                          checked={pref.channel_slack}
                          onCheckedChange={(checked) => updatePref(pref.alert_type, 'channel_slack', checked)}
                          disabled={!pref.is_enabled}
                        />
                      </div>
                      <div className="flex sm:justify-center">
                        <div className="sm:hidden text-xs text-muted-foreground mr-2">Email</div>
                        <Switch
                          checked={pref.channel_email}
                          onCheckedChange={(checked) => updatePref(pref.alert_type, 'channel_email', checked)}
                          disabled={!pref.is_enabled}
                        />
                      </div>
                    </div>

                    {/* Threshold input */}
                    {config.hasThreshold && pref.is_enabled && (
                      <div className="mt-3 flex items-center gap-2 pl-12">
                        <span className="text-sm text-muted-foreground">{config.thresholdLabel}:</span>
                        <Input
                          type="number"
                          className="w-24 h-8 text-sm"
                          value={pref.threshold_value ?? ''}
                          onChange={(e) => {
                            const val = e.target.value === '' ? null : parseFloat(e.target.value);
                            updatePref(pref.alert_type, 'threshold_value', val);
                          }}
                          step={pref.alert_type === 'volume_spike' ? '0.5' : '5'}
                          min={pref.alert_type === 'volume_spike' ? '1' : '0'}
                          max={pref.alert_type === 'volume_spike' ? '10' : '100'}
                        />
                        <span className="text-sm text-muted-foreground">{config.thresholdUnit}</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* Email Digests */}
        <Card className="animate-slide-up stagger-2">
          <CardHeader className="border-b border-border">
            <div className="flex items-center space-x-2">
              <div className="p-2 bg-secondary rounded-lg">
                <Mail className="w-5 h-5 text-primary" />
              </div>
              <CardTitle>Email Digests</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="pt-6 space-y-4">
            {/* Daily Digest */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-semibold text-foreground">Daily Alert Digest</p>
                  <p className="text-sm text-muted-foreground">
                    Receive a daily email summary of alerts
                  </p>
                </div>
                <Switch
                  checked={userPrefs?.daily_digest_enabled ?? true}
                  onCheckedChange={handleToggleDailyDigest}
                  disabled={savingDigest}
                />
              </div>
              {userPrefs?.daily_digest_enabled && (
                <div className="flex items-center gap-3 pl-1">
                  <span className="text-sm text-muted-foreground">Delivery time:</span>
                  <Select
                    value={String(userPrefs?.daily_digest_hour ?? 8)}
                    onValueChange={(value) => handleUpdateDigestSchedule('daily_digest_hour', Number(value))}
                    disabled={savingDigest}
                  >
                    <SelectTrigger className="w-[160px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {HOUR_OPTIONS.map(opt => (
                        <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>

            <div className="border-t border-border" />

            {/* Weekly Digest */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-semibold text-foreground">Weekly Digest</p>
                  <p className="text-sm text-muted-foreground">
                    Receive a weekly email summary of feedback trends
                  </p>
                </div>
                <Switch
                  checked={userPrefs?.weekly_digest_enabled ?? true}
                  onCheckedChange={handleToggleWeeklyDigest}
                  disabled={savingDigest}
                />
              </div>
              {userPrefs?.weekly_digest_enabled && (
                <div className="flex items-center gap-3 pl-1 flex-wrap">
                  <span className="text-sm text-muted-foreground">Delivery:</span>
                  <Select
                    value={String(userPrefs?.weekly_digest_day ?? 1)}
                    onValueChange={(value) => handleUpdateDigestSchedule('weekly_digest_day', Number(value))}
                    disabled={savingDigest}
                  >
                    <SelectTrigger className="w-[140px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {DAY_OPTIONS.map(opt => (
                        <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <span className="text-sm text-muted-foreground">at</span>
                  <Select
                    value={String(userPrefs?.weekly_digest_hour ?? 9)}
                    onValueChange={(value) => handleUpdateDigestSchedule('weekly_digest_hour', Number(value))}
                    disabled={savingDigest}
                  >
                    <SelectTrigger className="w-[160px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {HOUR_OPTIONS.map(opt => (
                        <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Notification Retention (Per-Type) */}
        <Card className="animate-slide-up stagger-3">
          <CardHeader className="border-b border-border">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <div className="p-2 bg-secondary rounded-lg">
                  <Clock className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <CardTitle>Notification Retention</CardTitle>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    First 30 days are free. Extended retention is $0.10 per extra day per month.
                  </p>
                </div>
              </div>
              {hasRetentionChanges && (
                <Button
                  onClick={handleSaveRetention}
                  disabled={savingRetention}
                  size="sm"
                >
                  <Save className="w-4 h-4 mr-1" />
                  {savingRetention ? 'Saving...' : 'Update Retention'}
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="pt-6 space-y-4">
            {preferences.map(pref => {
              const config = ALERT_TYPE_CONFIG[pref.alert_type];
              if (!config) return null;
              const days = retentionByType[pref.alert_type] ?? 30;
              const extraDays = Math.max(0, days - 30);
              const cost = extraDays * 0.10;

              return (
                <div key={pref.alert_type} className="flex flex-col sm:flex-row sm:items-center gap-3 py-2">
                  <div className="min-w-[180px]">
                    <p className="text-sm font-medium text-foreground">{config.label}</p>
                    {extraDays > 0 && (
                      <p className="text-xs text-muted-foreground">
                        +{extraDays} days (${cost.toFixed(2)}/mo)
                      </p>
                    )}
                  </div>
                  <ToggleGroup
                    type="single"
                    variant="outline"
                    size="sm"
                    value={String(days)}
                    onValueChange={(value) => {
                      if (value) {
                        setRetentionByType(prev => ({ ...prev, [pref.alert_type]: Number(value) }));
                        setHasRetentionChanges(true);
                      }
                    }}
                  >
                    {RETENTION_OPTIONS.map(opt => (
                      <ToggleGroupItem key={opt.value} value={opt.value} className="text-xs px-3">
                        {opt.label}
                      </ToggleGroupItem>
                    ))}
                  </ToggleGroup>
                </div>
              );
            })}

            {/* Total cost summary */}
            {totalExtraDays > 0 && (
              <div className="mt-2 pt-4 border-t border-border flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">Total extended retention: {totalExtraDays} extra days</p>
                  <p className="text-xs text-muted-foreground">${totalMonthlyCost.toFixed(2)}/month</p>
                </div>
                {!hasRetentionChanges && (
                  <p className="text-xs text-muted-foreground">Saved</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
