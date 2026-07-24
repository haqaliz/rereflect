'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { TrendingDown } from 'lucide-react';
import { aiSettingsAPI, type AISettings } from '@/lib/api/ai-settings';
import { listChurnSuggestions } from '@/lib/api/churn-suggestions';

const MODE_LABELS: Record<string, string> = {
  off: 'Off',
  shadow: 'Shadow',
  active: 'Active',
};

const MIN_SUSTAIN_DAYS = 1;
const MAX_SUSTAIN_DAYS = 90;
const DEFAULT_SUSTAIN_DAYS = 14;

interface UsageChurnLabelsCardProps {
  settings: AISettings;
  onUpdate: (updated: AISettings) => void;
}

interface PrecisionCounts {
  confirmed: number;
  rejected: number;
  pending: number;
}

function validateSustainDays(value: number): string | null {
  if (!Number.isInteger(value) || value < MIN_SUSTAIN_DAYS || value > MAX_SUSTAIN_DAYS) {
    return `Sustain days must be a whole number between ${MIN_SUSTAIN_DAYS} and ${MAX_SUSTAIN_DAYS}.`;
  }
  return null;
}

export function UsageChurnLabelsCard({ settings, onUpdate }: UsageChurnLabelsCardProps) {
  const [modeSaving, setModeSaving] = useState(false);
  const [modeError, setModeError] = useState<string | null>(null);

  const [sustainDaysInput, setSustainDaysInput] = useState<string>(
    String(settings.usage_churn_label_config?.sustain_days ?? DEFAULT_SUSTAIN_DAYS)
  );
  const [sustainDaysSaving, setSustainDaysSaving] = useState(false);
  const [sustainDaysError, setSustainDaysError] = useState<string | null>(null);

  const [counts, setCounts] = useState<PrecisionCounts | null>(null);
  const [countsLoading, setCountsLoading] = useState(true);
  const [countsError, setCountsError] = useState<string | null>(null);

  useEffect(() => {
    setSustainDaysInput(String(settings.usage_churn_label_config?.sustain_days ?? DEFAULT_SUSTAIN_DAYS));
  }, [settings.usage_churn_label_config?.sustain_days]);

  // Precision read-out data source (Phase 4 open question, resolved): rather
  // than a new backend endpoint, we ride the existing suggestions-list
  // endpoint with page_size=1 per status — `total` on that response is a
  // cheap GROUP-BY-status count already indexed by (org, status, provider).
  useEffect(() => {
    let cancelled = false;
    async function loadCounts() {
      setCountsLoading(true);
      setCountsError(null);
      try {
        const [confirmed, rejected, pending] = await Promise.all([
          listChurnSuggestions({ provider: 'usage_decline', status: 'confirmed', page_size: 1 }),
          listChurnSuggestions({ provider: 'usage_decline', status: 'rejected', page_size: 1 }),
          listChurnSuggestions({ provider: 'usage_decline', status: 'pending', page_size: 1 }),
        ]);
        if (cancelled) return;
        setCounts({
          confirmed: confirmed.total,
          rejected: rejected.total,
          pending: pending.total,
        });
      } catch {
        if (!cancelled) setCountsError('Could not load suggestion counts right now.');
      } finally {
        if (!cancelled) setCountsLoading(false);
      }
    }
    loadCounts();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleModeChange = async (mode: string) => {
    if (mode === settings.usage_churn_labels_mode) return;
    setModeSaving(true);
    setModeError(null);
    try {
      const updated = await aiSettingsAPI.update({ usage_churn_labels_mode: mode });
      onUpdate(updated);
    } catch (err: any) {
      setModeError(err?.response?.data?.detail || 'Failed to update usage churn labels mode');
    } finally {
      setModeSaving(false);
    }
  };

  const handleSustainDaysBlur = async () => {
    const value = Number(sustainDaysInput);
    const validationError = validateSustainDays(value);
    setSustainDaysError(validationError);
    if (validationError) return;

    const current = settings.usage_churn_label_config?.sustain_days ?? DEFAULT_SUSTAIN_DAYS;
    if (value === current) return;

    setSustainDaysSaving(true);
    try {
      const updated = await aiSettingsAPI.update({
        usage_churn_label_config: { sustain_days: value },
      });
      onUpdate(updated);
    } catch (err: any) {
      setSustainDaysError(err?.response?.data?.detail || 'Failed to update sustain days');
    } finally {
      setSustainDaysSaving(false);
    }
  };

  const totalCount = counts ? counts.confirmed + counts.rejected + counts.pending : null;

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <div className="flex items-center space-x-2">
          <div className="p-2 bg-secondary rounded-lg">
            <TrendingDown className="w-5 h-5 text-primary" />
          </div>
          <CardTitle>Usage-Decline Churn Labels</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="pt-6 space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="font-semibold text-foreground">Detection mode</p>
            <p className="text-sm text-muted-foreground">
              <strong>Off</strong> disables usage-decline detection entirely.{' '}
              <strong>Shadow</strong> evaluates and shows what would be suggested, but writes
              nothing &mdash; recommended while you build confidence in the signal.{' '}
              <strong>Active</strong> writes real suggestions into the review queue for a human
              to confirm or reject.
            </p>
          </div>
          <Select
            value={settings.usage_churn_labels_mode ?? 'off'}
            onValueChange={handleModeChange}
            disabled={modeSaving}
          >
            <SelectTrigger aria-label="Usage churn labels mode" className="w-32 shrink-0">
              <SelectValue>
                {MODE_LABELS[settings.usage_churn_labels_mode ?? 'off'] ??
                  settings.usage_churn_labels_mode}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="off">Off</SelectItem>
              <SelectItem value="shadow">Shadow</SelectItem>
              <SelectItem value="active">Active</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {modeError && <p className="text-xs text-destructive">{modeError}</p>}

        <div className="space-y-1.5">
          <Label htmlFor="usage-churn-sustain-days">Sustain days</Label>
          <p className="text-sm text-muted-foreground">
            How many consecutive days a decline must persist before it is suggested (1&ndash;90).
          </p>
          <Input
            id="usage-churn-sustain-days"
            aria-label="Sustain days"
            type="number"
            min={MIN_SUSTAIN_DAYS}
            max={MAX_SUSTAIN_DAYS}
            className="w-32"
            value={sustainDaysInput}
            onChange={(e) => setSustainDaysInput(e.target.value)}
            onBlur={handleSustainDaysBlur}
            disabled={sustainDaysSaving}
          />
          {sustainDaysError && <p className="text-xs text-destructive">{sustainDaysError}</p>}
        </div>

        <div className="rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground space-y-1.5">
          <p className="font-medium text-foreground">Before you enable this</p>
          <p>
            New customers need a roughly <strong>12-16 day warm-up</strong> before usage trends
            are reliable, plus your configured <strong>sustain days</strong> window on top of
            that before a decline can be suggested.
          </p>
          <p>
            Customers whose usage never reaches at least{' '}
            <strong>5 active days in a 14-day baseline window</strong> can{' '}
            <strong>never</strong> produce a suggestion &mdash; there is no established baseline
            to decline from.
          </p>
          <p>
            Only <strong>recently</strong> declining customers are surfaced. A customer who
            churned or went quiet long ago will <strong>never appear</strong> here &mdash; if you
            enable this and see nothing, that is often why.
          </p>
        </div>

        <div className="pt-2 border-t border-border">
          <p className="text-sm font-medium text-foreground mb-2">Suggestion precision</p>
          {countsLoading ? (
            <p className="text-sm text-muted-foreground">Loading counts&hellip;</p>
          ) : countsError ? (
            <p className="text-xs text-destructive">{countsError}</p>
          ) : (
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                  Confirmed
                </p>
                <p className="text-foreground">{counts?.confirmed ?? 0}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                  Rejected
                </p>
                <p className="text-foreground">{counts?.rejected ?? 0}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                  Pending
                </p>
                <p className="text-foreground">{counts?.pending ?? 0}</p>
              </div>
            </div>
          )}
          {!countsLoading && !countsError && totalCount === 0 && (
            <p className="text-xs text-muted-foreground mt-2">
              No usage-decline suggestions yet. That is expected during the warm-up window
              described above &mdash; check back once customers have enough usage history.
            </p>
          )}
          {/* TODO(usage-decline-churn-labels): surface last_detection_at /
              last_detection_status, including the M3b suppression-state
              counts, once worker-detector exposes them via the settings or
              status API. Not available yet — intentionally not fabricated. */}
        </div>
      </CardContent>
    </Card>
  );
}
