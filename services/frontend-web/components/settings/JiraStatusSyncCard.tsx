'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, RefreshCw, Copy, Check } from 'lucide-react';
import {
  patchJiraStatusSync,
  triggerJiraSync,
  enableJiraWebhook,
  disableJiraWebhook,
  type JiraConnectionStatus,
} from '@/lib/api/jira';
import { timeAgo } from '@/lib/notification-utils';
import { StatusMappingEditor } from '@/components/settings/StatusMappingEditor';
import { JIRA_STATUS_MAPPING_KEYS } from '@/lib/constants/status-sync-keys';

interface JiraStatusSyncCardProps {
  status: JiraConnectionStatus;
  onStatusChange: (status: JiraConnectionStatus) => void;
}

// Control surface for inbound Jira status sync (Phase 6 of
// jira-status-sync/inbound-status-sync, extended by the mapping-editor
// aspect): a toggle, a read-only last-synced indicator, a manual "Sync now"
// trigger, and a status-category → Rereflect-status mapping editor.
export function JiraStatusSyncCard({ status, onStatusChange }: JiraStatusSyncCardProps) {
  const [toggling, setToggling] = useState(false);
  const [syncing, setSyncing] = useState(false);

  // Real-time webhook (jira-webhook aspect): display-once secret reveal.
  // GET /status never returns the secret, so a page refresh cannot recover
  // it — this state only ever holds what THIS session's enable call
  // returned, mirroring Zendesk's connect-time reveal.
  const [webhookBusy, setWebhookBusy] = useState(false);
  const [webhookSecret, setWebhookSecret] = useState<string | null>(null);
  const [webhookUrl, setWebhookUrl] = useState<string | null>(null);
  const [copiedSecret, setCopiedSecret] = useState(false);
  const [copiedUrl, setCopiedUrl] = useState(false);

  if (!status.connected) {
    return null;
  }

  const handleToggle = async (checked: boolean) => {
    const previous = status;
    // Optimistic update — flip immediately, revert on failure.
    onStatusChange({ ...status, status_sync_enabled: checked });
    setToggling(true);
    try {
      const updated = await patchJiraStatusSync(checked);
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
      await triggerJiraSync();
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
    const updated = await patchJiraStatusSync(status.status_sync_enabled, mapping);
    onStatusChange(updated);
  };

  const handleEnableWebhook = async () => {
    setWebhookBusy(true);
    try {
      const result = await enableJiraWebhook();
      setWebhookSecret(result.webhook_secret);
      setWebhookUrl(result.webhook_url);
      onStatusChange({ ...status, webhook_enabled: true });
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      const message = typeof detail === 'string' ? detail : 'Failed to enable the Jira webhook.';
      toast.error(message);
    } finally {
      setWebhookBusy(false);
    }
  };

  const handleDisableWebhook = async () => {
    setWebhookBusy(true);
    try {
      await disableJiraWebhook();
      setWebhookSecret(null);
      setWebhookUrl(null);
      onStatusChange({ ...status, webhook_enabled: false });
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      const message = typeof detail === 'string' ? detail : 'Failed to disable the Jira webhook.';
      toast.error(message);
    } finally {
      setWebhookBusy(false);
    }
  };

  const copyWebhookSecret = () => {
    if (webhookSecret) {
      navigator.clipboard.writeText(webhookSecret);
      setCopiedSecret(true);
      setTimeout(() => setCopiedSecret(false), 2000);
    }
  };

  const copyWebhookUrl = () => {
    if (webhookUrl) {
      navigator.clipboard.writeText(webhookUrl);
      setCopiedUrl(true);
      setTimeout(() => setCopiedUrl(false), 2000);
    }
  };

  const lastSyncedLabel = status.last_status_synced_at ? timeAgo(status.last_status_synced_at) : 'Never';
  const isSyncError = status.last_sync_status === 'error';

  return (
    <Card className="animate-slide-up">
      <CardHeader>
        <CardTitle className="text-base">Inbound Status Sync</CardTitle>
        <CardDescription>
          Pull Jira issue status changes back into the linked feedback&apos;s workflow status.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-semibold text-foreground">Sync issue status back to Rereflect</p>
            <p className="text-sm text-muted-foreground">
              Automatically update feedback status when the linked Jira issue&apos;s status changes.
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
            foreignKeys={JIRA_STATUS_MAPPING_KEYS}
            currentMapping={status.status_mapping}
            onSave={handleSaveMapping}
            description="Jira status categories map to Rereflect workflow statuses. This is category-level, not per raw status name."
          />
        </div>

        <div className="pt-2 border-t border-border space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-semibold text-foreground">Real-time webhook</p>
              <p className="text-sm text-muted-foreground">
                Optional — the 15-min poll above always runs as a fallback. Enabling adds a
                signed inbound webhook so Jira status changes land in seconds.
              </p>
            </div>
            {status.webhook_enabled ? (
              <Button
                variant="outline"
                size="sm"
                onClick={handleDisableWebhook}
                disabled={webhookBusy}
              >
                {webhookBusy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                Disable webhook
              </Button>
            ) : (
              <Button size="sm" onClick={handleEnableWebhook} disabled={webhookBusy}>
                {webhookBusy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                Enable webhook
              </Button>
            )}
          </div>

          {webhookSecret && webhookUrl ? (
            <div className="space-y-3">
              <div className="space-y-2">
                <Label>Webhook URL</Label>
                <div className="flex items-center gap-2">
                  <Input readOnly value={webhookUrl} className="font-mono text-sm" />
                  <Button variant="outline" onClick={copyWebhookUrl}>
                    {copiedUrl ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  </Button>
                </div>
              </div>
              <div className="space-y-2">
                <Label>Webhook Secret</Label>
                <div className="flex items-center gap-2">
                  <Input readOnly value={webhookSecret} className="font-mono text-sm" />
                  <Button variant="outline" onClick={copyWebhookSecret}>
                    {copiedSecret ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Save this secret now — you won&apos;t be able to view it again. Add it to a Jira
                  Cloud webhook (Settings → System → WebHooks) pointed at the URL above, signed
                  with this secret.
                </p>
              </div>
            </div>
          ) : status.webhook_enabled ? (
            <p className="text-xs text-muted-foreground">
              Webhook enabled — re-enable (rotates the secret) to view the URL and secret again.
            </p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
