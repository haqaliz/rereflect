'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { AlertCircle, Loader2, Send } from 'lucide-react';
import { intercomAPI, type IntercomConnectionStatus } from '@/lib/api/intercom';

// Friendly copy for machine-readable reasons returned by the backend (both
// the PATCH /writeback error bodies and POST /writeback/test).
const REASON_COPY: Record<string, string> = {
  missing_write_scope: 'Intercom token is missing the conversation:write scope.',
  auth_error: 'Intercom rejected the token — write-back is paused.',
  no_admin: 'Could not resolve an Intercom admin to author the note.',
  missing_encryption_key:
    'The stored token could not be decrypted — the server encryption key is not set.',
};

// Friendly copy for last_writeback_status values set by the background task.
// Keys must match the worker's recorded statuses exactly
// (worker-service/src/tasks/intercom_writeback.py).
const STATUS_COPY: Record<string, string> = {
  ok: 'Last write succeeded',
  retrying: 'Retrying after a transient error',
  'error: missing_write_scope': 'Intercom token is missing the conversation:write scope',
  'noop: already_closed': 'Conversation was already closed — nothing to do',
  'error: no_admin': 'Could not resolve an Intercom admin',
  error: 'Write-back failed',
};

function friendlyReason(reason: string | null | undefined): string {
  if (!reason) return '';
  return REASON_COPY[reason] ?? reason;
}

function friendlyStatus(value: string | null | undefined): string {
  if (!value) return '';
  return STATUS_COPY[value] ?? value;
}

interface IntercomWritebackCardProps {
  status: IntercomConnectionStatus;
  onStatusChange: (status: IntercomConnectionStatus) => void;
}

// Control surface for the resolve write-back (intercom-writeback feature):
// when Intercom-sourced feedback is marked resolved, add a note to the linked
// conversation and (optionally) close it. Never-optimistic — every change
// PATCHes, refetches status, and only then calls onStatusChange.
export function IntercomWritebackCard({ status, onStatusChange }: IntercomWritebackCardProps) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);

  if (!status.connected) {
    return null;
  }

  const extractErrorMessage = (err: any): string => {
    const detail = err?.response?.data?.detail;
    if (typeof detail === 'string') {
      return detail;
    } else if (detail?.message) {
      return detail.message;
    } else if (detail?.reason) {
      return friendlyReason(detail.reason);
    }
    return 'Failed to update write-back settings. Please try again.';
  };

  const handleToggle = async (checked: boolean) => {
    setError(null);
    setSaving(true);
    try {
      await intercomAPI.updateWriteback({ enabled: checked });
      const refreshed = await intercomAPI.getStatus();
      onStatusChange(refreshed);
    } catch (err: any) {
      setError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleActionChange = async (action: 'note_only' | 'note_and_close') => {
    setError(null);
    setSaving(true);
    try {
      await intercomAPI.updateWriteback({
        enabled: status.writeback_enabled,
        action,
      });
      const refreshed = await intercomAPI.getStatus();
      onStatusChange(refreshed);
    } catch (err: any) {
      setError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const res = await intercomAPI.testWriteback();
      if (res.ok) {
        toast.success('Write-back test passed — scope is valid.');
      } else {
        toast.error(friendlyReason(res.reason) || 'Write-back test failed.');
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? 'Could not run write-back test.');
    } finally {
      setTesting(false);
    }
  };

  const actionValue = status.writeback_action ?? 'note_and_close';

  return (
    <Card className="animate-slide-up">
      <CardHeader>
        <CardTitle>Resolve Write-Back</CardTitle>
        <CardDescription>
          When you mark Intercom-sourced feedback as resolved, Rereflect adds a
          note to the linked conversation and closes it. Off by default —
          nothing is written until you enable it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-semibold text-foreground">Enable write-back</p>
            <p className="text-sm text-muted-foreground">
              Only resolutions after you enable it are written back.
            </p>
          </div>
          <Switch
            checked={status.writeback_enabled}
            onCheckedChange={handleToggle}
            disabled={saving}
          />
        </div>

        <div className="space-y-2">
          <Label>Write-back action</Label>
          <Select
            value={actionValue}
            onValueChange={handleActionChange}
            disabled={saving}
          >
            <SelectTrigger className="w-full sm:w-72">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="note_and_close">
                Add a note and close the conversation
              </SelectItem>
              <SelectItem value="note_only">
                Add a note only — leave closing to your team
              </SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Requires the conversation:write scope on your Intercom app. If the
            scope is missing, you&apos;ll see missing_write_scope here — the
            integration stays connected.
          </p>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <Button
          variant="outline"
          size="sm"
          onClick={handleTest}
          disabled={testing}
        >
          {testing ? (
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
          ) : (
            <Send className="w-4 h-4 mr-2" />
          )}
          Test write-back
        </Button>

        {(status.last_writeback_at || status.last_writeback_status) && (
          <div className="grid grid-cols-2 gap-4 text-sm pt-2 border-t border-border">
            {status.last_writeback_at && (
              <div>
                <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                  Last Write-back
                </p>
                <p className="text-foreground">
                  {new Date(status.last_writeback_at).toLocaleString()}
                </p>
              </div>
            )}
            {status.last_writeback_status && (
              <div>
                <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                  Last Status
                </p>
                <p className="text-foreground">
                  {friendlyStatus(status.last_writeback_status)}
                </p>
              </div>
            )}
          </div>
        )}

        {status.last_writeback_error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              {friendlyReason(status.last_writeback_error)}
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
