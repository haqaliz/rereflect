'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Loader2, RefreshCw } from 'lucide-react';
import { patchAsanaStatusSync, triggerAsanaSync, type AsanaConnectionStatus } from '@/lib/api/asana';
import { timeAgo } from '@/lib/notification-utils';
import { StatusMappingEditor } from '@/components/settings/StatusMappingEditor';
import { ASANA_STATUS_MAPPING_KEYS } from '@/lib/constants/status-sync-keys';

interface AsanaStatusSyncCardProps {
  status: AsanaConnectionStatus;
  onStatusChange: (status: AsanaConnectionStatus) => void;
}

// Control surface for inbound Asana status sync (asana-status-sync,
// mirroring jira-status-sync/inbound-status-sync; extended by the
// mapping-editor aspect): a toggle, a read-only last-synced indicator, a
// manual "Sync now" trigger, and a completion → Rereflect-status mapping
// editor.
export function AsanaStatusSyncCard({ status, onStatusChange }: AsanaStatusSyncCardProps) {
  const [toggling, setToggling] = useState(false);
  const [syncing, setSyncing] = useState(false);

  if (!status.connected) {
    return null;
  }

  const handleToggle = async (checked: boolean) => {
    const previous = status;
    // Optimistic update — flip immediately, revert on failure.
    onStatusChange({ ...status, status_sync_enabled: checked });
    setToggling(true);
    try {
      const updated = await patchAsanaStatusSync(checked);
      onStatusChange(updated);
    } catch (err: any) {
      onStatusChange(previous);
      const detail = err?.response?.data?.detail;
      const message = typeof detail === 'string' ? detail : 'Failed to update status sync setting.';
      toast.error(message);
    } finally {
      setToggling(false);
    }
  };

  const handleSyncNow = async () => {
    setSyncing(true);
    try {
      await triggerAsanaSync();
      toast.success('Sync started — status updates will appear shortly.');
    } catch (err: any) {
      const statusCode = err?.response?.status;
      const detail = err?.response?.data?.detail;
      const message =
        statusCode === 502
          ? 'Could not start sync — the background worker is unavailable. Please try again shortly.'
          : typeof detail === 'string'
          ? detail
          : 'Could not start sync. Please try again.';
      toast.error(message);
    } finally {
      setSyncing(false);
    }
  };

  const handleSaveMapping = async (mapping: Record<string, string>) => {
    const updated = await patchAsanaStatusSync(status.status_sync_enabled, mapping);
    onStatusChange(updated);
  };

  const lastSyncedLabel = status.last_status_synced_at ? timeAgo(status.last_status_synced_at) : 'Never';
  const isSyncError = status.last_sync_status === 'error';

  return (
    <Card className="animate-slide-up">
      <CardHeader>
        <CardTitle className="text-base">Inbound Status Sync</CardTitle>
        <CardDescription>
          Pull Asana task status changes back into the linked feedback&apos;s workflow status.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-semibold text-foreground">Sync task status back to Rereflect</p>
            <p className="text-sm text-muted-foreground">
              Automatically update feedback status when the linked Asana task is completed.
            </p>
          </div>
          <Switch
            checked={status.status_sync_enabled}
            onCheckedChange={handleToggle}
            disabled={toggling}
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-border">
          <p className="text-sm text-muted-foreground">
            Last synced {lastSyncedLabel}
            {status.last_sync_status && ` · ${status.last_sync_status}`}
          </p>
          <Button variant="outline" size="sm" onClick={handleSyncNow} disabled={syncing}>
            {syncing ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4 mr-2" />
            )}
            Sync Now
          </Button>
        </div>

        {isSyncError && status.last_error && (
          <p className="text-sm text-destructive">{status.last_error}</p>
        )}

        <div className="pt-2 border-t border-border">
          <p className="font-semibold text-foreground mb-1">Status mapping</p>
          <StatusMappingEditor
            foreignKeys={ASANA_STATUS_MAPPING_KEYS}
            currentMapping={status.status_mapping}
            onSave={handleSaveMapping}
            description="Asana task completion maps to Rereflect workflow statuses."
          />
        </div>
      </CardContent>
    </Card>
  );
}
