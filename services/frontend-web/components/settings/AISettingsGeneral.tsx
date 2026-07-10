'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Brain, Sparkles } from 'lucide-react';
import { aiSettingsAPI, type AISettings, type SentimentStatus } from '@/lib/api/ai-settings';

interface AISettingsGeneralProps {
  settings: AISettings;
  onUpdate: (updated: AISettings) => void;
}

export function AISettingsGeneral({ settings, onUpdate }: AISettingsGeneralProps) {
  const [saving, setSaving] = useState(false);
  const [sentimentSaving, setSentimentSaving] = useState(false);
  const [sentimentError, setSentimentError] = useState<string | null>(null);
  const [sentimentStatus, setSentimentStatus] = useState<SentimentStatus | null>(null);

  useEffect(() => {
    aiSettingsAPI
      .getSentimentStatus()
      .then(setSentimentStatus)
      .catch(() => setSentimentStatus(null));
  }, [settings.sentiment_provider]);

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

  const handleToggleSentiment = async (checked: boolean) => {
    const nextProvider = checked ? 'transformer' : 'vader';
    setSentimentSaving(true);
    setSentimentError(null);
    try {
      const updated = await aiSettingsAPI.update({ sentiment_provider: nextProvider });
      onUpdate(updated);
    } catch (err: any) {
      setSentimentError(
        err?.response?.data?.detail || 'Failed to update sentiment engine'
      );
    } finally {
      setSentimentSaving(false);
    }
  };

  const isTransformer = settings.sentiment_provider === 'transformer';

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
              aria-label="Enable AI Analysis"
              checked={settings.ai_analysis_enabled}
              onCheckedChange={handleToggleAI}
              disabled={saving}
            />
          </div>
        </CardContent>
      </Card>

      {/* Sentiment Engine Toggle (M5.1 local-analyzer-sentiment-model) */}
      <Card>
        <CardHeader className="border-b border-border">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-secondary rounded-lg">
              <Sparkles className="w-5 h-5 text-primary" />
            </div>
            <CardTitle>Sentiment Engine</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="pt-6 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-semibold text-foreground">Use local transformer model</p>
              <p className="text-sm text-muted-foreground">
                Off uses VADER (fast, default). On uses a local transformer model for
                higher-accuracy sentiment scoring — runs entirely on your infrastructure.
              </p>
            </div>
            <Switch
              aria-label="Sentiment engine"
              checked={isTransformer}
              onCheckedChange={handleToggleSentiment}
              disabled={sentimentSaving}
            />
          </div>
          {sentimentError && (
            <p className="text-xs text-destructive">{sentimentError}</p>
          )}
          {isTransformer && sentimentStatus && !sentimentStatus.available && (
            <p className="text-xs text-muted-foreground">
              Transformer model dependencies are not available (not installed) on this
              deployment. Feedback will continue to be scored with VADER until torch and
              transformers are installed. See docs/SELF_HOSTING.md.
            </p>
          )}
          {isTransformer && sentimentStatus?.available && sentimentStatus.model && (
            <p className="text-xs text-muted-foreground">
              Model: {sentimentStatus.model}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
