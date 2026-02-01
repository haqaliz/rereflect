'use client';

import { useState, useEffect } from 'react';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  integrationsAPI,
  Integration,
  TRIGGER_OPTIONS,
  FIELD_OPTIONS,
} from '@/lib/api/integrations';
import {
  Slack,
  Plus,
  Trash2,
  Send,
  CheckCircle,
  XCircle,
  AlertCircle,
  Loader2,
  Settings2,
  Clock,
  ToggleLeft,
  ToggleRight,
} from 'lucide-react';

export function SlackIntegration() {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [selectedIntegration, setSelectedIntegration] = useState<Integration | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<{ id: number; success: boolean; message: string } | null>(null);

  // Create form state
  const [createForm, setCreateForm] = useState({
    name: '',
    webhook_url: '',
    triggers: ['urgent'] as string[],
    included_fields: ['text', 'sentiment'] as string[],
    digest_time: '09:00',
  });
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Config form state
  const [configForm, setConfigForm] = useState({
    name: '',
    triggers: [] as string[],
    included_fields: [] as string[],
    digest_time: '09:00',
    is_active: true,
  });
  const [configLoading, setConfigLoading] = useState(false);

  useEffect(() => {
    fetchIntegrations();
  }, []);

  const fetchIntegrations = async () => {
    try {
      setLoading(true);
      const response = await integrationsAPI.list();
      setIntegrations(response.integrations.filter(i => i.type === 'slack'));
    } catch (err) {
      console.error('Failed to load integrations:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    setCreateError(null);
    setCreateLoading(true);
    try {
      await integrationsAPI.createSlackWebhook({
        name: createForm.name,
        webhook_url: createForm.webhook_url,
        triggers: createForm.triggers,
        included_fields: createForm.included_fields,
        digest_time: createForm.digest_time,
      });
      setIsCreateOpen(false);
      setCreateForm({
        name: '',
        webhook_url: '',
        triggers: ['urgent'],
        included_fields: ['text', 'sentiment'],
        digest_time: '09:00',
      });
      await fetchIntegrations();
    } catch (err: any) {
      setCreateError(err.response?.data?.detail || 'Failed to create integration');
    } finally {
      setCreateLoading(false);
    }
  };

  const handleTest = async (integration: Integration) => {
    setTestingId(integration.id);
    setTestResult(null);
    try {
      const result = await integrationsAPI.testSlack(integration.id);
      setTestResult({ id: integration.id, success: result.success, message: result.message });
      // Refresh to get updated last_used_at
      await fetchIntegrations();
    } catch (err: any) {
      setTestResult({
        id: integration.id,
        success: false,
        message: err.response?.data?.detail || 'Test failed',
      });
    } finally {
      setTestingId(null);
    }
  };

  const handleDelete = async (integration: Integration) => {
    if (!confirm(`Delete integration "${integration.name}"? This cannot be undone.`)) return;
    try {
      await integrationsAPI.delete(integration.id);
      await fetchIntegrations();
    } catch (err) {
      console.error('Failed to delete integration:', err);
    }
  };

  const openConfig = (integration: Integration) => {
    setSelectedIntegration(integration);
    setConfigForm({
      name: integration.name || '',
      triggers: integration.triggers || ['urgent'],
      included_fields: integration.included_fields || ['text', 'sentiment'],
      digest_time: integration.digest_time || '09:00',
      is_active: integration.is_active,
    });
    setIsConfigOpen(true);
  };

  const handleSaveConfig = async () => {
    if (!selectedIntegration) return;
    setConfigLoading(true);
    try {
      await integrationsAPI.update(selectedIntegration.id, configForm);
      setIsConfigOpen(false);
      await fetchIntegrations();
    } catch (err) {
      console.error('Failed to update integration:', err);
    } finally {
      setConfigLoading(false);
    }
  };

  const toggleTrigger = (trigger: string, form: 'create' | 'config') => {
    if (form === 'create') {
      setCreateForm(prev => ({
        ...prev,
        triggers: prev.triggers.includes(trigger)
          ? prev.triggers.filter(t => t !== trigger)
          : [...prev.triggers, trigger],
      }));
    } else {
      setConfigForm(prev => ({
        ...prev,
        triggers: prev.triggers.includes(trigger)
          ? prev.triggers.filter(t => t !== trigger)
          : [...prev.triggers, trigger],
      }));
    }
  };

  const toggleField = (field: string, form: 'create' | 'config') => {
    if (form === 'create') {
      setCreateForm(prev => ({
        ...prev,
        included_fields: prev.included_fields.includes(field)
          ? prev.included_fields.filter(f => f !== field)
          : [...prev.included_fields, field],
      }));
    } else {
      setConfigForm(prev => ({
        ...prev,
        included_fields: prev.included_fields.includes(field)
          ? prev.included_fields.filter(f => f !== field)
          : [...prev.included_fields, field],
      }));
    }
  };

  const needsDigestTime = (triggers: string[]) =>
    triggers.includes('daily_digest') || triggers.includes('weekly_digest');

  if (loading) {
    return (
      <Card>
        <CardHeader className="border-b border-border">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-secondary rounded-lg">
              <Slack className="w-5 h-5 text-primary" />
            </div>
            <CardTitle>Slack Integration</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="pt-6">
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-secondary rounded-lg">
              <Slack className="w-5 h-5 text-primary" />
            </div>
            <CardTitle>Slack Integration</CardTitle>
          </div>
          <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
            <DialogTrigger asChild>
              <Button size="sm" className="flex items-center gap-2">
                <Plus className="w-4 h-4" />
                Add Webhook
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Add Slack Webhook</DialogTitle>
                <DialogDescription>
                  Connect Rereflect to a Slack channel via Incoming Webhook.
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Integration Name</Label>
                  <Input
                    id="name"
                    placeholder="e.g., #feedback-alerts"
                    value={createForm.name}
                    onChange={e => setCreateForm(prev => ({ ...prev, name: e.target.value }))}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="webhook_url">Webhook URL</Label>
                  <Input
                    id="webhook_url"
                    type="url"
                    placeholder="https://hooks.slack.com/services/..."
                    value={createForm.webhook_url}
                    onChange={e => setCreateForm(prev => ({ ...prev, webhook_url: e.target.value }))}
                  />
                  <p className="text-xs text-muted-foreground">
                    Get this from Slack: App Settings &gt; Incoming Webhooks
                  </p>
                </div>

                <div className="space-y-3">
                  <Label>Alert Triggers</Label>
                  <div className="space-y-2">
                    {TRIGGER_OPTIONS.map(opt => (
                      <div key={opt.value} className="flex items-start space-x-3">
                        <Checkbox
                          id={`create-trigger-${opt.value}`}
                          checked={createForm.triggers.includes(opt.value)}
                          onCheckedChange={() => toggleTrigger(opt.value, 'create')}
                        />
                        <div className="grid gap-0.5">
                          <Label htmlFor={`create-trigger-${opt.value}`} className="font-medium cursor-pointer">
                            {opt.label}
                          </Label>
                          <p className="text-xs text-muted-foreground">{opt.description}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {needsDigestTime(createForm.triggers) && (
                  <div className="space-y-2">
                    <Label htmlFor="digest_time">Digest Time (UTC)</Label>
                    <Input
                      id="digest_time"
                      type="time"
                      value={createForm.digest_time}
                      onChange={e => setCreateForm(prev => ({ ...prev, digest_time: e.target.value }))}
                    />
                  </div>
                )}

                <div className="space-y-3">
                  <Label>Included Fields</Label>
                  <div className="grid grid-cols-2 gap-2">
                    {FIELD_OPTIONS.map(opt => (
                      <div key={opt.value} className="flex items-center space-x-2">
                        <Checkbox
                          id={`create-field-${opt.value}`}
                          checked={createForm.included_fields.includes(opt.value)}
                          onCheckedChange={() => toggleField(opt.value, 'create')}
                        />
                        <Label htmlFor={`create-field-${opt.value}`} className="text-sm cursor-pointer">
                          {opt.label}
                        </Label>
                      </div>
                    ))}
                  </div>
                </div>

                {createError && (
                  <div className="p-3 bg-destructive/10 text-destructive rounded-lg text-sm flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 flex-shrink-0" />
                    {createError}
                  </div>
                )}
              </div>

              <DialogFooter>
                <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
                  Cancel
                </Button>
                <Button
                  onClick={handleCreate}
                  disabled={!createForm.name || !createForm.webhook_url || createLoading}
                >
                  {createLoading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                  Create Integration
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </CardHeader>

      <CardContent className="pt-6">
        {integrations.length === 0 ? (
          <div className="text-center py-8">
            <Slack className="w-12 h-12 mx-auto text-muted-foreground/50 mb-3" />
            <h3 className="font-semibold text-foreground mb-1">No Slack integrations</h3>
            <p className="text-sm text-muted-foreground mb-4">
              Add a webhook to receive feedback alerts in Slack
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {integrations.map(integration => (
              <div
                key={integration.id}
                className="p-4 border border-border rounded-xl bg-card/50 space-y-3"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-secondary rounded-lg">
                      <Slack className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-foreground">
                          {integration.name || 'Unnamed Integration'}
                        </span>
                        {integration.is_active ? (
                          <Badge variant="outline" className="text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950">
                            Active
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-muted-foreground">
                            Disabled
                          </Badge>
                        )}
                      </div>
                      {integration.channel_name && (
                        <span className="text-sm text-muted-foreground">
                          #{integration.channel_name}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleTest(integration)}
                      disabled={testingId === integration.id}
                    >
                      {testingId === integration.id ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Send className="w-4 h-4" />
                      )}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => openConfig(integration)}
                    >
                      <Settings2 className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDelete(integration)}
                      className="text-destructive hover:bg-destructive hover:text-destructive-foreground"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>

                {/* Triggers */}
                <div className="flex flex-wrap gap-2">
                  {integration.triggers.map(trigger => (
                    <Badge key={trigger} variant="secondary" className="text-xs">
                      {TRIGGER_OPTIONS.find(t => t.value === trigger)?.label || trigger}
                    </Badge>
                  ))}
                </div>

                {/* Status info */}
                <div className="flex items-center gap-4 text-xs text-muted-foreground">
                  {integration.last_used_at && (
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      Last used: {new Date(integration.last_used_at).toLocaleString()}
                    </span>
                  )}
                  {integration.error_count > 0 && (
                    <span className="flex items-center gap-1 text-destructive">
                      <AlertCircle className="w-3 h-3" />
                      {integration.error_count} error(s)
                    </span>
                  )}
                </div>

                {/* Test result */}
                {testResult && testResult.id === integration.id && (
                  <div
                    className={`p-3 rounded-lg text-sm flex items-center gap-2 ${
                      testResult.success
                        ? 'bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300'
                        : 'bg-destructive/10 text-destructive'
                    }`}
                  >
                    {testResult.success ? (
                      <CheckCircle className="w-4 h-4 flex-shrink-0" />
                    ) : (
                      <XCircle className="w-4 h-4 flex-shrink-0" />
                    )}
                    {testResult.message}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>

      {/* Config Dialog */}
      <Dialog open={isConfigOpen} onOpenChange={setIsConfigOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Configure Integration</DialogTitle>
            <DialogDescription>
              Update the settings for this Slack integration.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="config-name">Integration Name</Label>
              <Input
                id="config-name"
                value={configForm.name}
                onChange={e => setConfigForm(prev => ({ ...prev, name: e.target.value }))}
              />
            </div>

            <div className="flex items-center justify-between p-3 border border-border rounded-lg">
              <div>
                <Label className="font-medium">Integration Status</Label>
                <p className="text-xs text-muted-foreground">
                  {configForm.is_active ? 'Alerts are being sent' : 'Alerts are paused'}
                </p>
              </div>
              <Button
                variant={configForm.is_active ? 'default' : 'outline'}
                size="sm"
                onClick={() => setConfigForm(prev => ({ ...prev, is_active: !prev.is_active }))}
              >
                {configForm.is_active ? (
                  <ToggleRight className="w-5 h-5" />
                ) : (
                  <ToggleLeft className="w-5 h-5" />
                )}
              </Button>
            </div>

            <div className="space-y-3">
              <Label>Alert Triggers</Label>
              <div className="space-y-2">
                {TRIGGER_OPTIONS.map(opt => (
                  <div key={opt.value} className="flex items-start space-x-3">
                    <Checkbox
                      id={`config-trigger-${opt.value}`}
                      checked={configForm.triggers.includes(opt.value)}
                      onCheckedChange={() => toggleTrigger(opt.value, 'config')}
                    />
                    <div className="grid gap-0.5">
                      <Label htmlFor={`config-trigger-${opt.value}`} className="font-medium cursor-pointer">
                        {opt.label}
                      </Label>
                      <p className="text-xs text-muted-foreground">{opt.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {needsDigestTime(configForm.triggers) && (
              <div className="space-y-2">
                <Label htmlFor="config-digest-time">Digest Time (UTC)</Label>
                <Input
                  id="config-digest-time"
                  type="time"
                  value={configForm.digest_time}
                  onChange={e => setConfigForm(prev => ({ ...prev, digest_time: e.target.value }))}
                />
              </div>
            )}

            <div className="space-y-3">
              <Label>Included Fields</Label>
              <div className="grid grid-cols-2 gap-2">
                {FIELD_OPTIONS.map(opt => (
                  <div key={opt.value} className="flex items-center space-x-2">
                    <Checkbox
                      id={`config-field-${opt.value}`}
                      checked={configForm.included_fields.includes(opt.value)}
                      onCheckedChange={() => toggleField(opt.value, 'config')}
                    />
                    <Label htmlFor={`config-field-${opt.value}`} className="text-sm cursor-pointer">
                      {opt.label}
                    </Label>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsConfigOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSaveConfig} disabled={configLoading}>
              {configLoading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
