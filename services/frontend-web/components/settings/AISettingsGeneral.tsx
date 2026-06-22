'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Brain } from 'lucide-react';
import { aiSettingsAPI, type AISettings } from '@/lib/api/ai-settings';

interface AISettingsGeneralProps {
  settings: AISettings;
  onUpdate: (updated: AISettings) => void;
}

export function AISettingsGeneral({ settings, onUpdate }: AISettingsGeneralProps) {
  const [saving, setSaving] = useState(false);

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
    </div>
  );
}
