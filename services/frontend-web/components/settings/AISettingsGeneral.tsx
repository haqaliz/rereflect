'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Progress } from '@/components/ui/progress';
import { AlertTriangle, Brain } from 'lucide-react';
import { aiSettingsAPI, type AISettings } from '@/lib/api/ai-settings';

interface AISettingsGeneralProps {
  settings: AISettings;
  onUpdate: (updated: AISettings) => void;
}

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function formatResetDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export function AISettingsGeneral({ settings, onUpdate }: AISettingsGeneralProps) {
  const [saving, setSaving] = useState(false);

  const { budget } = settings;
  const budgetPercent = budget.monthly_limit_cents > 0
    ? Math.min(100, Math.round((budget.used_cents / budget.monthly_limit_cents) * 100))
    : 0;

  const handleToggleAI = async (checked: boolean) => {
    setSaving(true);
    try {
      const updated = await aiSettingsAPI.update({ ai_analysis_enabled: checked });
      onUpdate(updated);
    } catch (err) {
      console.error('Failed to update AI settings:', err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* AI Toggle */}
      <Card>
        <CardHeader className="border-b border-border">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-secondary rounded-lg">
              <Brain className="w-5 h-5 text-primary" />
            </div>
            <CardTitle>AI-Powered Analysis</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-semibold text-foreground">Enable AI Analysis</p>
              <p className="text-sm text-muted-foreground">
                Use AI models for intelligent feedback categorization, churn risk scoring, and suggested actions
              </p>
            </div>
            <Switch
              checked={settings.ai_analysis_enabled}
              onCheckedChange={handleToggleAI}
              disabled={saving}
            />
          </div>
        </CardContent>
      </Card>

      {/* Budget Status */}
      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>AI Budget</CardTitle>
        </CardHeader>
        <CardContent className="pt-6 space-y-4">
          {budget.is_exceeded && (
            <div className="flex items-center gap-2 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
              <p className="text-sm font-medium text-amber-700 dark:text-amber-400">
                Budget exceeded — new feedback won&apos;t be analyzed until {formatResetDate(budget.resets_at)}.
              </p>
            </div>
          )}

          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Used this month</span>
              <span className="font-medium">
                {formatCents(budget.used_cents)} / {formatCents(budget.monthly_limit_cents)}
              </span>
            </div>
            <Progress
              value={budgetPercent}
              className={budget.is_exceeded ? '[&>div]:bg-amber-500' : ''}
            />
            <p className="text-xs text-muted-foreground">
              Resets {formatResetDate(budget.resets_at)} &middot; BYOK calls don&apos;t count toward budget
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
