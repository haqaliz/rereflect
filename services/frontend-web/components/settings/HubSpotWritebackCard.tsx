'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AlertCircle, CheckCircle, Loader2, Send, XCircle } from 'lucide-react';
import { hubspotAPI, type HubSpotConnectionStatus } from '@/lib/api/hubspot';

const DEFAULT_FIELD_NAME = 'rereflect_health_score';

// Friendly copy for machine-readable validation reasons returned by the
// backend (both the PATCH /writeback 400 body and POST /writeback/test).
const REASON_COPY: Record<string, string> = {
  field_not_found: 'Field not found in HubSpot.',
  wrong_type: 'Field exists but is not a number property.',
  missing_write_scope: 'HubSpot token is missing write permission for this property.',
};

// Friendly copy for last_writeback_status values set by the background task.
const STATUS_COPY: Record<string, string> = {
  ok: 'Last write succeeded',
  field_not_found: 'Field not found in HubSpot',
  contact_not_found: 'Contact not found in HubSpot',
  retrying: 'Retrying after a transient error',
  'error: missing_write_scope': 'HubSpot token is missing write permission',
};

function friendlyReason(reason: string | null | undefined): string {
  if (!reason) return '';
  return REASON_COPY[reason] ?? reason;
}

function friendlyStatus(value: string | null | undefined): string {
  if (!value) return '';
  return STATUS_COPY[value] ?? value;
}

interface HubSpotWritebackCardProps {
  status: HubSpotConnectionStatus;
  onStatusChange: (status: HubSpotConnectionStatus) => void;
}

export function HubSpotWritebackCard({ status, onStatusChange }: HubSpotWritebackCardProps) {
  const [fieldName, setFieldName] = useState(status.writeback_field_name || DEFAULT_FIELD_NAME);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; reason: string | null } | null>(null);

  if (!status.connected) {
    return null;
  }

  // Input is editable while writeback is off (so the user can prepare/fix the
  // field name) and locked once confirmed enabled — avoids renaming a live
  // writeback field out from under an in-flight job.
  const inputDisabled = saving || status.writeback_enabled;

  const handleToggle = async (checked: boolean) => {
    setError(null);

    if (checked) {
      const trimmed = fieldName.trim();
      if (!trimmed) {
        setError('Field name is required to enable writeback.');
        return;
      }
    }

    setSaving(true);
    try {
      await hubspotAPI.updateWriteback({
        enabled: checked,
        field_name: checked ? fieldName.trim() : null,
      });
      const refreshed = await hubspotAPI.getStatus();
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
        message = 'Failed to update writeback settings. Please try again.';
      }
      setError(message);
    } finally {
      setSaving(false);
    }
  };

  const handleValidate = async () => {
    const trimmed = fieldName.trim();
    if (!trimmed) {
      setTestResult({ ok: false, reason: null });
      return;
    }
    setTesting(true);
    setTestResult(null);
    try {
      const res = await hubspotAPI.testWriteback(trimmed);
      setTestResult(res);
    } catch (err: any) {
      setTestResult({
        ok: false,
        reason: err?.response?.data?.detail ?? 'Validation failed.',
      });
    } finally {
      setTesting(false);
    }
  };

  return (
    <Card className="animate-slide-up">
      <CardHeader>
        <CardTitle>Health-Score Writeback</CardTitle>
        <CardDescription>
          Push each customer&apos;s Rereflect health score back into HubSpot as a custom contact property.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-semibold text-foreground">Enable writeback</p>
            <p className="text-sm text-muted-foreground">
              Automatically write the health score to HubSpot whenever it changes.
            </p>
          </div>
          <Switch
            checked={status.writeback_enabled}
            onCheckedChange={handleToggle}
            disabled={saving}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="writeback-field-name">Field Name</Label>
          <Input
            id="writeback-field-name"
            type="text"
            placeholder={DEFAULT_FIELD_NAME}
            value={fieldName}
            onChange={(e) => setFieldName(e.target.value)}
            disabled={inputDisabled}
            className="font-mono text-sm"
          />
          <p className="text-xs text-muted-foreground">
            The HubSpot contact property to write the health score into.
            Defaults to <code className="font-mono">{DEFAULT_FIELD_NAME}</code>.
          </p>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={handleValidate}
            disabled={testing || !fieldName.trim()}
          >
            {testing ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Send className="w-4 h-4 mr-2" />
            )}
            Validate
          </Button>
        </div>

        {testResult && (
          <div
            className={`p-3 rounded-lg text-sm flex items-center gap-2 ${
              testResult.ok
                ? 'bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300'
                : 'bg-destructive/10 text-destructive'
            }`}
          >
            {testResult.ok ? (
              <CheckCircle className="w-4 h-4 flex-shrink-0" />
            ) : (
              <XCircle className="w-4 h-4 flex-shrink-0" />
            )}
            {testResult.ok
              ? 'Field is valid and ready for writeback.'
              : friendlyReason(testResult.reason) || 'Field failed validation.'}
          </div>
        )}

        <div className="grid grid-cols-2 gap-4 text-sm pt-2 border-t border-border">
          {status.last_writeback_at && (
            <div>
              <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                Last Writeback
              </p>
              <p className="text-foreground">{new Date(status.last_writeback_at).toLocaleString()}</p>
            </div>
          )}
          {status.last_writeback_status && (
            <div>
              <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                Last Status
              </p>
              <p className="text-foreground">{friendlyStatus(status.last_writeback_status)}</p>
            </div>
          )}
          <div>
            <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
              Contacts Written
            </p>
            <p className="text-foreground">{status.contacts_written.toLocaleString()}</p>
          </div>
        </div>

        {status.last_writeback_error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{status.last_writeback_error}</AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
