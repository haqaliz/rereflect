'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Brain, Sparkles, Wand2, Tags, AlertTriangle } from 'lucide-react';
import { aiSettingsAPI, type AISettings, type SentimentStatus } from '@/lib/api/ai-settings';

const CLASSIFIER_MODE_LABELS: Record<string, string> = {
  off: 'Off',
  shadow: 'Shadow',
  auto: 'Auto',
};

interface AISettingsGeneralProps {
  settings: AISettings;
  onUpdate: (updated: AISettings) => void;
}

export function AISettingsGeneral({ settings, onUpdate }: AISettingsGeneralProps) {
  const [saving, setSaving] = useState(false);
  const [sentimentSaving, setSentimentSaving] = useState(false);
  const [sentimentError, setSentimentError] = useState<string | null>(null);
  const [sentimentStatus, setSentimentStatus] = useState<SentimentStatus | null>(null);
  const [classifierSaving, setClassifierSaving] = useState(false);
  const [classifierError, setClassifierError] = useState<string | null>(null);
  const [categoryClassifierSaving, setCategoryClassifierSaving] = useState(false);
  const [categoryClassifierError, setCategoryClassifierError] = useState<string | null>(null);
  const [urgencyClassifierSaving, setUrgencyClassifierSaving] = useState(false);
  const [urgencyClassifierError, setUrgencyClassifierError] = useState<string | null>(null);

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

  const handleClassifierMode = async (classifier_mode: string) => {
    if (classifier_mode === settings.classifier_mode) return;
    setClassifierSaving(true);
    setClassifierError(null);
    try {
      const updated = await aiSettingsAPI.update({ classifier_mode });
      onUpdate(updated);
    } catch (err: any) {
      setClassifierError(
        err?.response?.data?.detail || 'Failed to update classifier mode'
      );
    } finally {
      setClassifierSaving(false);
    }
  };

  const handleCategoryClassifierMode = async (category_classifier_mode: string) => {
    if (category_classifier_mode === settings.category_classifier_mode) return;
    setCategoryClassifierSaving(true);
    setCategoryClassifierError(null);
    try {
      const updated = await aiSettingsAPI.update({ category_classifier_mode });
      onUpdate(updated);
    } catch (err: any) {
      setCategoryClassifierError(
        err?.response?.data?.detail || 'Failed to update category classifier mode'
      );
    } finally {
      setCategoryClassifierSaving(false);
    }
  };

  const handleUrgencyClassifierMode = async (urgency_classifier_mode: string) => {
    if (urgency_classifier_mode === settings.urgency_classifier_mode) return;
    setUrgencyClassifierSaving(true);
    setUrgencyClassifierError(null);
    try {
      const updated = await aiSettingsAPI.update({ urgency_classifier_mode });
      onUpdate(updated);
    } catch (err: any) {
      setUrgencyClassifierError(
        err?.response?.data?.detail || 'Failed to update urgency classifier mode'
      );
    } finally {
      setUrgencyClassifierSaving(false);
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

      {/* Self-Improving Classifier Mode (M5.2 per-org-corrections-classifier) */}
      <Card>
        <CardHeader className="border-b border-border">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-secondary rounded-lg">
              <Wand2 className="w-5 h-5 text-primary" />
            </div>
            <CardTitle>Self-Improving Classifier</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="pt-6 space-y-3">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="font-semibold text-foreground">Corrections-trained sentiment model</p>
              <p className="text-sm text-muted-foreground">
                Learns from your team&apos;s sentiment corrections. <strong>Off</strong> disables
                it. <strong>Shadow</strong> observes and scores in the background without
                changing stored sentiment — recommended until you have accumulated a
                substantial number of corrections. <strong>Auto</strong> lets the trained
                model override stored sentiment once it beats the incumbent.
              </p>
            </div>
            <Select
              value={settings.classifier_mode}
              onValueChange={handleClassifierMode}
              disabled={classifierSaving}
            >
              <SelectTrigger aria-label="Classifier mode" className="w-32 shrink-0">
                <SelectValue>{CLASSIFIER_MODE_LABELS[settings.classifier_mode] ?? settings.classifier_mode}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="off">Off</SelectItem>
                <SelectItem value="shadow">Shadow</SelectItem>
                <SelectItem value="auto">Auto</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {classifierError && (
            <p className="text-xs text-destructive">{classifierError}</p>
          )}
        </CardContent>
      </Card>

      {/* Self-Improving Category Classifier Mode (M5.2 v2 per-org-category-classifier) */}
      <Card>
        <CardHeader className="border-b border-border">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-secondary rounded-lg">
              <Tags className="w-5 h-5 text-primary" />
            </div>
            <CardTitle>Self-Improving Category Classifier</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="pt-6 space-y-3">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="font-semibold text-foreground">Corrections-trained category model</p>
              <p className="text-sm text-muted-foreground">
                Learns from your team&apos;s category corrections on pain-point/feature-request
                items. <strong>Off</strong> disables it. <strong>Shadow</strong> observes and
                scores in the background without changing stored categories &mdash;
                recommended until you have accumulated a substantial number of corrections.{' '}
                <strong>Auto</strong> lets the trained model override the stored category once
                it beats the keyword categorizer, and only when its predicted label is
                unambiguous (belongs to exactly one built-in category type).
              </p>
            </div>
            <Select
              value={settings.category_classifier_mode ?? 'off'}
              onValueChange={handleCategoryClassifierMode}
              disabled={categoryClassifierSaving}
            >
              <SelectTrigger aria-label="Category classifier mode" className="w-32 shrink-0">
                <SelectValue>
                  {CLASSIFIER_MODE_LABELS[settings.category_classifier_mode ?? 'off'] ??
                    settings.category_classifier_mode}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="off">Off</SelectItem>
                <SelectItem value="shadow">Shadow</SelectItem>
                <SelectItem value="auto">Auto</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {categoryClassifierError && (
            <p className="text-xs text-destructive">{categoryClassifierError}</p>
          )}
        </CardContent>
      </Card>

      {/* Self-Improving Urgency Classifier Mode (urgency classifier head) */}
      <Card>
        <CardHeader className="border-b border-border">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-secondary rounded-lg">
              <AlertTriangle className="w-5 h-5 text-primary" />
            </div>
            <CardTitle>Self-Improving Urgency Classifier</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="pt-6 space-y-3">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="font-semibold text-foreground">Corrections-trained urgency model</p>
              <p className="text-sm text-muted-foreground">
                Your model, trained on your team&apos;s urgency corrections. <strong>Off</strong>{' '}
                disables it. <strong>Shadow</strong> observes and scores in the background
                without changing stored urgency &mdash; recommended until you have accumulated a
                substantial number of corrections. <strong>Auto</strong> lets the trained model
                override stored urgency, but only when it beats the keyword urgency heuristic on
                held-out data, and it is <strong>add-only</strong>: it can escalate a feedback
                item from not-urgent to urgent, but it never de-escalates an already-urgent item.
              </p>
            </div>
            <Select
              value={settings.urgency_classifier_mode ?? 'off'}
              onValueChange={handleUrgencyClassifierMode}
              disabled={urgencyClassifierSaving}
            >
              <SelectTrigger aria-label="Urgency classifier mode" className="w-32 shrink-0">
                <SelectValue>
                  {CLASSIFIER_MODE_LABELS[settings.urgency_classifier_mode ?? 'off'] ??
                    settings.urgency_classifier_mode}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="off">Off</SelectItem>
                <SelectItem value="shadow">Shadow</SelectItem>
                <SelectItem value="auto">Auto</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {urgencyClassifierError && (
            <p className="text-xs text-destructive">{urgencyClassifierError}</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
