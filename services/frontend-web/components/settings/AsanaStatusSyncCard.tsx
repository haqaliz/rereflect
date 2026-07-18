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
  patchAsanaStatusSync,
  triggerAsanaSync,
  enableAsanaWebhook,
  disableAsanaWebhook,
  asanaAPI,
  type AsanaConnectionStatus,
  type AsanaWorkspace,
  type AsanaProject,
} from '@/lib/api/asana';
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

  // Real-time webhook (asana-webhook aspect). Unlike Jira (which generates
  // its own secret and just needs the operator to paste it into Jira's own
  // webhook UI), Asana's webhook is registered automatically by our backend
  // calling Asana's API — the operator only needs to pick which project to
  // watch (v1 scope: a single project, reusing the same workspace/project
  // wiring as task creation). The handshake secret itself is captured
  // server-side on Asana's first delivery and is never shown here.
  const [settingUpWebhook, setSettingUpWebhook] = useState(false);
  const [webhookBusy, setWebhookBusy] = useState(false);
  const [loadingWorkspaces, setLoadingWorkspaces] = useState(false);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [workspaces, setWorkspaces] = useState<AsanaWorkspace[]>([]);
  const [projects, setProjects] = useState<AsanaProject[]>([]);
  const [selectedWorkspace, setSelectedWorkspace] = useState('');
  const [selectedProject, setSelectedProject] = useState('');
  const [webhookUrl, setWebhookUrl] = useState<string | null>(null);
  const [copiedUrl, setCopiedUrl] = useState(false);

  if (!status.connected) {
    return null;
  }

  const handleStartWebhookSetup = async () => {
    setSettingUpWebhook(true);
    if (workspaces.length > 0) return;
    setLoadingWorkspaces(true);
    try {
      const data = await asanaAPI.getWorkspaces();
      setWorkspaces(data);
    } catch {
      // Swallow — the select stays empty; the operator can retry via the
      // button (no dedicated retry UI needed for this v1 scope).
    } finally {
      setLoadingWorkspaces(false);
    }
  };

  const handleWorkspaceChange = async (workspaceGid: string) => {
    setSelectedWorkspace(workspaceGid);
    setSelectedProject('');
    setProjects([]);
    if (!workspaceGid) return;
    setLoadingProjects(true);
    try {
      const data = await asanaAPI.getProjects(workspaceGid);
      setProjects(data);
    } catch {
      // Swallow — see handleStartWebhookSetup.
    } finally {
      setLoadingProjects(false);
    }
  };

  const handleEnableWebhook = async () => {
    if (!selectedProject) return;
    setWebhookBusy(true);
    try {
      const result = await enableAsanaWebhook(selectedProject);
      setWebhookUrl(result.webhook_url);
      toast.success('Asana webhook registered. It will activate once Asana completes the handshake.');
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      const message = typeof detail === 'string' ? detail : 'Failed to enable the Asana webhook.';
      toast.error(message);
    } finally {
      setWebhookBusy(false);
    }
  };

  const handleDisableWebhook = async () => {
    setWebhookBusy(true);
    try {
      await disableAsanaWebhook();
      setSettingUpWebhook(false);
      setWebhookUrl(null);
      setSelectedWorkspace('');
      setSelectedProject('');
      setWorkspaces([]);
      setProjects([]);
      onStatusChange({ ...status, webhook_enabled: false });
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      const message = typeof detail === 'string' ? detail : 'Failed to disable the Asana webhook.';
      toast.error(message);
    } finally {
      setWebhookBusy(false);
    }
  };

  const copyWebhookUrl = () => {
    if (webhookUrl) {
      navigator.clipboard.writeText(webhookUrl);
      setCopiedUrl(true);
      setTimeout(() => setCopiedUrl(false), 2000);
    }
  };

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

        <div className="pt-2 border-t border-border space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-semibold text-foreground">Real-time webhook</p>
              <p className="text-sm text-muted-foreground">
                Optional — the 15-min poll above always runs as a fallback. Enabling registers a
                webhook with Asana for one project so task completion changes land in seconds.
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
            ) : !settingUpWebhook ? (
              <Button size="sm" onClick={handleStartWebhookSetup}>
                Set up webhook
              </Button>
            ) : null}
          </div>

          {!status.webhook_enabled && settingUpWebhook && (
            <div className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="asana-webhook-workspace">Workspace</Label>
                <select
                  id="asana-webhook-workspace"
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm"
                  value={selectedWorkspace}
                  onChange={(e) => handleWorkspaceChange(e.target.value)}
                  disabled={loadingWorkspaces}
                >
                  <option value="">
                    {loadingWorkspaces ? 'Loading workspaces…' : 'Select a workspace…'}
                  </option>
                  {workspaces.map((ws) => (
                    <option key={ws.gid ?? ''} value={ws.gid ?? ''}>
                      {ws.name}
                    </option>
                  ))}
                </select>
              </div>

              {selectedWorkspace && (
                <div className="space-y-2">
                  <Label htmlFor="asana-webhook-project">Project</Label>
                  <select
                    id="asana-webhook-project"
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm"
                    value={selectedProject}
                    onChange={(e) => setSelectedProject(e.target.value)}
                    disabled={loadingProjects}
                  >
                    <option value="">
                      {loadingProjects ? 'Loading projects…' : 'Select a project…'}
                    </option>
                    {projects.map((p) => (
                      <option key={p.gid ?? ''} value={p.gid ?? ''}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <Button size="sm" onClick={handleEnableWebhook} disabled={!selectedProject || webhookBusy}>
                {webhookBusy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                Enable webhook
              </Button>
            </div>
          )}

          {webhookUrl ? (
            <div className="space-y-2">
              <Label>Webhook URL</Label>
              <div className="flex items-center gap-2">
                <Input readOnly value={webhookUrl} className="font-mono text-sm" />
                <Button variant="outline" onClick={copyWebhookUrl}>
                  {copiedUrl ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Registered with Asana. No further setup is needed — Asana completes the handshake
                automatically; refresh this page in a moment to confirm the webhook is active.
              </p>
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
