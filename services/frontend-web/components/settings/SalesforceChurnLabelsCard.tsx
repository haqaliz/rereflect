'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AlertCircle, Loader2 } from 'lucide-react';
import {
  salesforceAPI,
  type SalesforceConnectionStatus,
  type ChurnLabelOption,
} from '@/lib/api/salesforce';

const BACKFILL_MONTH_OPTIONS = [12, 24, 36, 60];
const DEFAULT_BACKFILL_MONTHS = 24;
const BACKFILL_POLL_INTERVAL_MS = 5000;

function formatWindowSince(since: string | undefined): string {
  if (!since) return '';
  const parsed = new Date(since);
  if (Number.isNaN(parsed.getTime())) return since;
  return parsed.toLocaleDateString();
}

// Friendly copy for machine-readable validation reasons returned by the
// backend (PATCH .../churn-labels 422/502 body).
const REASON_COPY: Record<string, string> = {
  unknown_opportunity_type:
    'Unknown opportunity type selected — one or more types are not recognized by Salesforce.',
  no_active_integration: 'No active Salesforce integration.',
  options_fetch_failed: 'Could not fetch live opportunity types from Salesforce right now.',
  missing_read_scope: 'Salesforce token is missing read permission for opportunity types.',
  validation_error: 'Could not validate the configuration right now. Please try again.',
};

// Friendly copy for last_harvest_status values set by the harvester task.
const STATUS_COPY: Record<string, string> = {
  ok: 'Last harvest succeeded',
  retrying: 'Retrying after a transient error',
  'error: missing_read_scope': 'Salesforce token is missing read permission',
  'deferred: daily_limit': "Deferred — Salesforce's daily API limit was reached",
};

function friendlyReason(reason: string | null | undefined): string {
  if (!reason) return '';
  return REASON_COPY[reason] ?? reason;
}

function friendlyStatus(value: string | null | undefined): string {
  if (!value) return '';
  return STATUS_COPY[value] ?? value;
}

interface SalesforceChurnLabelsCardProps {
  status: SalesforceConnectionStatus;
  onStatusChange: (status: SalesforceConnectionStatus) => void;
}

export function SalesforceChurnLabelsCard({
  status,
  onStatusChange,
}: SalesforceChurnLabelsCardProps) {
  const [selected, setSelected] = useState<string[]>(
    status.churn_label_config?.renewal_opportunity_types ?? []
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [popoverOpen, setPopoverOpen] = useState(false);
  const [options, setOptions] = useState<ChurnLabelOption[] | null>(null);
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [optionsError, setOptionsError] = useState<string | null>(null);

  // Historical churn-label backfill (historical-backfill aspect)
  const [backfillMonths, setBackfillMonths] = useState<number>(DEFAULT_BACKFILL_MONTHS);
  const [backfillActionLoading, setBackfillActionLoading] = useState(false);
  const [backfillActionError, setBackfillActionError] = useState<string | null>(null);

  const isBackfillRunning = status.backfill_status === 'running';

  useEffect(() => {
    if (!isBackfillRunning) return;
    const interval = setInterval(async () => {
      try {
        const refreshed = await salesforceAPI.getStatus();
        onStatusChange(refreshed);
      } catch {
        // Polling failures are non-fatal — the next tick retries.
      }
    }, BACKFILL_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isBackfillRunning]);

  if (!status.connected) {
    return null;
  }

  // Picker is locked while enabled — avoids re-pointing a live harvester's
  // renewal set out from under an in-flight run (matches
  // SalesforceWritebackCard.tsx's inputDisabled precedent).
  const inputDisabled = saving || Boolean(status.churn_labels_enabled);

  const loadOptions = async () => {
    setOptionsLoading(true);
    setOptionsError(null);
    try {
      const res = await salesforceAPI.getChurnLabelOptions();
      setOptions(res.options);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      const reason = typeof detail === 'object' ? detail?.reason : null;
      setOptionsError(friendlyReason(reason) || 'Could not fetch live opportunity types.');
    } finally {
      setOptionsLoading(false);
    }
  };

  const handlePopoverOpenChange = (open: boolean) => {
    setPopoverOpen(open);
    if (open) {
      // Fetch lazily on open — never on card mount, never blocking the toggle (R-A).
      loadOptions();
    }
  };

  const toggleId = (id: string) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((existing) => existing !== id) : [...prev, id]
    );
  };

  const handleToggle = async (checked: boolean) => {
    setError(null);
    setSaving(true);
    try {
      await salesforceAPI.updateChurnLabels({
        enabled: checked,
        config: checked ? { renewal_opportunity_types: selected } : null,
      });
      const refreshed = await salesforceAPI.getStatus();
      onStatusChange(refreshed);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      let message: string;
      if (typeof detail === 'string') {
        message = detail;
      } else if (detail?.message) {
        message = detail.message;
      } else if (detail?.reason) {
        message = friendlyReason(detail.reason);
      } else {
        message = 'Failed to update churn-label settings. Please try again.';
      }
      setError(message);
    } finally {
      setSaving(false);
    }
  };

  const handleRunBackfill = async () => {
    setBackfillActionError(null);
    setBackfillActionLoading(true);
    try {
      await salesforceAPI.triggerChurnBackfill(backfillMonths);
      const refreshed = await salesforceAPI.getStatus();
      onStatusChange(refreshed);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      const message = typeof detail === 'string' ? detail : 'Failed to start backfill. Please try again.';
      setBackfillActionError(message);
    } finally {
      setBackfillActionLoading(false);
    }
  };

  const handleCancelBackfill = async () => {
    setBackfillActionError(null);
    setBackfillActionLoading(true);
    try {
      await salesforceAPI.cancelChurnBackfill();
      const refreshed = await salesforceAPI.getStatus();
      onStatusChange(refreshed);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      const message = typeof detail === 'string' ? detail : 'Failed to cancel backfill. Please try again.';
      setBackfillActionError(message);
    } finally {
      setBackfillActionLoading(false);
    }
  };

  const knownIds = new Set((options ?? []).map((opt) => opt.id));
  const staleSelectedIds = selected.filter((id) => !knownIds.has(id));

  const showEmptyStateWarning = Boolean(status.churn_labels_enabled) && selected.length === 0;

  const runDisabled =
    backfillActionLoading || !status.churn_labels_enabled || selected.length === 0;
  const droppedByCap = status.backfill_progress?.dropped_by_cap ?? 0;

  return (
    <Card className="animate-slide-up">
      <CardHeader>
        <CardTitle>CRM Churn-Label Suggestions</CardTitle>
        <CardDescription>
          Suggest churn labels from lost Salesforce renewal opportunities, reviewed by an
          operator before they ever train the calibrator.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-semibold text-foreground">Enable churn-label suggestions</p>
            <p className="text-sm text-muted-foreground">
              Only lost opportunities in the types you pick below are ever suggested.
            </p>
          </div>
          <Switch
            checked={status.churn_labels_enabled ?? false}
            onCheckedChange={handleToggle}
            disabled={saving}
          />
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium">Renewal opportunity types</p>
          <Popover open={popoverOpen} onOpenChange={handlePopoverOpenChange}>
            <PopoverTrigger asChild>
              <Button variant="outline" disabled={inputDisabled} className="w-full justify-start">
                {selected.length} opportunity type{selected.length === 1 ? '' : 's'} selected
              </Button>
            </PopoverTrigger>
            <PopoverContent>
              {optionsLoading && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Loading opportunity types…
                </div>
              )}
              {!optionsLoading && optionsError && (
                <div className="space-y-2">
                  <p className="text-sm text-destructive">{optionsError}</p>
                  <Button variant="outline" size="sm" onClick={loadOptions}>
                    Retry
                  </Button>
                </div>
              )}
              {!optionsLoading && !optionsError && options && options.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  Salesforce returned no opportunity types.
                </p>
              )}
              {!optionsLoading && !optionsError && options && options.length > 0 && (
                <div className="space-y-2">
                  {options.map((opt) => (
                    <div key={opt.id} className="flex items-center gap-2">
                      <Checkbox
                        id={`opp-type-${opt.id}`}
                        checked={selected.includes(opt.id)}
                        onCheckedChange={() => toggleId(opt.id)}
                      />
                      <label htmlFor={`opp-type-${opt.id}`} className="text-sm cursor-pointer">
                        {opt.label}
                      </label>
                    </div>
                  ))}
                </div>
              )}
            </PopoverContent>
          </Popover>

          {staleSelectedIds.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-1">
              {staleSelectedIds.map((id) => (
                <Badge key={id} variant="warning">
                  {id} — not found in Salesforce
                </Badge>
              ))}
            </div>
          )}
        </div>

        {showEmptyStateWarning && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              No renewal opportunity types selected — no suggestions will be created. Pick the
              opportunity type your renewals close as.
            </AlertDescription>
          </Alert>
        )}

        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="grid grid-cols-2 gap-4 text-sm pt-2 border-t border-border">
          {status.last_harvest_at && (
            <div>
              <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                Last Harvest
              </p>
              <p className="text-foreground">{new Date(status.last_harvest_at).toLocaleString()}</p>
            </div>
          )}
          {status.last_harvest_status && (
            <div>
              <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                Last Status
              </p>
              <p className="text-foreground">{friendlyStatus(status.last_harvest_status)}</p>
            </div>
          )}
          <div>
            <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
              Suggestions Created
            </p>
            <p className="text-foreground">{(status.suggestions_created ?? 0).toLocaleString()}</p>
          </div>
        </div>

        {status.last_harvest_error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{friendlyReason(status.last_harvest_error)}</AlertDescription>
          </Alert>
        )}

        {/* Historical churn-label backfill (historical-backfill aspect) */}
        <div className="space-y-3 pt-2 border-t border-border">
          <div>
            <p className="font-semibold text-foreground">Backfill history</p>
            <p className="text-sm text-muted-foreground">
              Run a one-time pass over closed-lost Opportunities from up to 5 years back — years
              of lost renewals land in the review queue as suggestions, never labels.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Select
              value={String(backfillMonths)}
              onValueChange={(value) => setBackfillMonths(Number(value))}
              disabled={isBackfillRunning || backfillActionLoading}
            >
              <SelectTrigger aria-label="Backfill window" className="w-28 shrink-0">
                <SelectValue>{backfillMonths}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {BACKFILL_MONTH_OPTIONS.map((m) => (
                  <SelectItem key={m} value={String(m)}>
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-sm text-muted-foreground">months back</span>

            {isBackfillRunning ? (
              <Button
                variant="outline"
                size="sm"
                onClick={handleCancelBackfill}
                disabled={backfillActionLoading}
              >
                {backfillActionLoading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                Cancel
              </Button>
            ) : (
              <Button size="sm" onClick={handleRunBackfill} disabled={runDisabled}>
                {backfillActionLoading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                Run
              </Button>
            )}
          </div>

          {status.backfill_status && (
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                  Scanned
                </p>
                <p className="text-foreground">{status.backfill_progress?.scanned ?? 0}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                  Suggested
                </p>
                <p className="text-foreground">{status.backfill_progress?.suggested ?? 0}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                  Skipped
                </p>
                <p className="text-foreground">{status.backfill_progress?.skipped_existing ?? 0}</p>
              </div>
            </div>
          )}

          {droppedByCap > 0 && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                {droppedByCap} dropped by the per-run cap; covered window: since{' '}
                {formatWindowSince(status.backfill_progress?.since)}.
              </AlertDescription>
            </Alert>
          )}

          {status.backfill_error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{status.backfill_error}</AlertDescription>
            </Alert>
          )}

          {backfillActionError && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{backfillActionError}</AlertDescription>
            </Alert>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
