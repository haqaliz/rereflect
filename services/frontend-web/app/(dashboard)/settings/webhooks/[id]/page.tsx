'use client';

import React, { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  webhooksAPI,
  WEBHOOK_EVENTS,
  type WebhookEndpoint,
  type WebhookDelivery,
  type UpdateWebhookRequest,
} from '@/lib/api/webhooks';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  ArrowLeft,
  RefreshCw,
  Trash2,
  Save,
  Loader2,
  Copy,
  Check,
} from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { toast } from 'sonner';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function DeliveryStatusBadge({ status }: { status: WebhookDelivery['status'] }) {
  if (status === 'sent') {
    return <Badge className="bg-green-500 text-white hover:bg-green-600">sent</Badge>;
  }
  if (status === 'retrying') {
    return <Badge className="bg-yellow-500 text-white hover:bg-yellow-600">retrying</Badge>;
  }
  return <Badge variant="destructive">failed</Badge>;
}

function formatTs(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

// ─── Copy Button ──────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Failed to copy');
    }
  };

  return (
    <Button variant="ghost" size="sm" onClick={handleCopy} title="Copy to clipboard">
      {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
    </Button>
  );
}

// ─── Secret Display ───────────────────────────────────────────────────────────

function SecretReveal({ secret }: { secret: string }) {
  return (
    <div
      data-testid="new-secret-display"
      className="mt-3 p-3 rounded-md bg-muted border border-border font-mono text-sm break-all flex items-start gap-2"
    >
      <span className="flex-1">{secret}</span>
      <CopyButton text={secret} />
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function WebhookDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();

  const webhookId = Number(params?.id);

  const [loading, setLoading] = useState(true);
  const [webhook, setWebhook] = useState<WebhookEndpoint | null>(null);
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([]);

  // Config form state
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);
  const [categoryFilters, setCategoryFilters] = useState<string[]>([]);
  const [retryMode, setRetryMode] = useState<'fire_and_forget' | 'exponential_backoff'>('fire_and_forget');
  const [customHeaders, setCustomHeaders] = useState<{ key: string; value: string }[]>([]);
  const [isActive, setIsActive] = useState(true);
  const [saving, setSaving] = useState(false);

  // Secret rotation
  const [rotateDialogOpen, setRotateDialogOpen] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [newSecret, setNewSecret] = useState<string | null>(null);

  // Delete
  const [deleting, setDeleting] = useState(false);
  const [confirmAction, setConfirmAction] = useState<(() => void) | null>(null);
  const [confirmMessage, setConfirmMessage] = useState('');

  const requestConfirm = (message: string, action: () => void) => {
    setConfirmMessage(message);
    setConfirmAction(() => action);
  };

  // Expandable delivery rows
  const [expandedDelivery, setExpandedDelivery] = useState<number | null>(null);

  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';

  useEffect(() => {
    if (!webhookId || isNaN(webhookId)) return;

    async function load() {
      try {
        const [wh, dels] = await Promise.all([
          webhooksAPI.get(webhookId),
          webhooksAPI.listDeliveries(webhookId),
        ]);
        setWebhook(wh);
        setDeliveries(dels);

        // Populate form
        setName(wh.name);
        setUrl(wh.url);
        setSelectedEvents(wh.events);
        setCategoryFilters(wh.category_filters);
        setRetryMode(wh.retry_mode);
        setIsActive(wh.is_active);
        setCustomHeaders(
          Object.entries(wh.custom_headers).map(([key, value]) => ({ key, value }))
        );
      } catch {
        toast.error('Failed to load webhook');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [webhookId]);

  const toggleEvent = (eventId: string) => {
    setSelectedEvents(prev =>
      prev.includes(eventId) ? prev.filter(e => e !== eventId) : [...prev, eventId]
    );
  };

  const handleSave = useCallback(async () => {
    if (!webhook) return;
    setSaving(true);
    try {
      const headersObj = customHeaders.reduce<Record<string, string>>((acc, { key, value }) => {
        if (key.trim()) acc[key.trim()] = value;
        return acc;
      }, {});

      const payload: UpdateWebhookRequest = {
        name,
        url,
        events: selectedEvents,
        category_filters: categoryFilters,
        retry_mode: retryMode,
        custom_headers: headersObj,
        is_active: isActive,
      };

      const updated = await webhooksAPI.update(webhook.id, payload);
      setWebhook(updated);
      toast.success('Webhook saved');
    } catch {
      toast.error('Failed to save webhook');
    } finally {
      setSaving(false);
    }
  }, [webhook, name, url, selectedEvents, categoryFilters, retryMode, customHeaders, isActive]);

  const handleRotateSecret = useCallback(() => {
    if (!webhook) return;
    requestConfirm(
      'Rotate the signing secret? Your receiver will need updating with the new secret.',
      async () => {
        setRotating(true);
        try {
          const result = await webhooksAPI.rotateSecret(webhook.id);
          setNewSecret(result.signing_secret);
          setWebhook(result);
          toast.success('Signing secret rotated');
        } catch {
          toast.error('Failed to rotate secret');
        } finally {
          setRotating(false);
        }
      }
    );
  }, [webhook]);

  const handleDelete = useCallback(() => {
    if (!webhook) return;
    requestConfirm(
      `Delete "${webhook.name}"? This cannot be undone.`,
      async () => {
        setDeleting(true);
        try {
          await webhooksAPI.delete(webhook.id);
          toast.success('Webhook deleted');
          router.push('/settings/webhooks');
        } catch {
          toast.error('Failed to delete webhook');
          setDeleting(false);
        }
      }
    );
  }, [webhook, router]);

  const addHeader = () => setCustomHeaders(prev => [...prev, { key: '', value: '' }]);
  const removeHeader = (i: number) => setCustomHeaders(prev => prev.filter((_, idx) => idx !== i));
  const updateHeader = (i: number, field: 'key' | 'value', val: string) => {
    setCustomHeaders(prev => prev.map((h, idx) => (idx === i ? { ...h, [field]: val } : h)));
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 border-4 border-primary/20 rounded-full" />
            <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
          <p className="text-muted-foreground font-medium">Loading webhook...</p>
        </div>
      </div>
    );
  }

  if (!webhook) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-muted-foreground">Webhook not found.</p>
          <Button asChild variant="ghost" className="mt-4">
            <Link href="/settings/webhooks">Back to Webhooks</Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">

        {/* Back nav + header */}
        <div className="animate-fade-in">
          <Button asChild variant="ghost" size="sm" className="mb-4 -ml-2 text-muted-foreground">
            <Link href="/settings/webhooks">
              <ArrowLeft className="w-4 h-4 mr-1" />
              Back to Webhooks
            </Link>
          </Button>

          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold text-foreground">{webhook.name}</h1>
              <p className="text-muted-foreground font-mono text-sm mt-1 break-all">{webhook.url}</p>
            </div>

            <div className="flex items-center gap-2 flex-shrink-0">
              {webhook.is_active ? (
                <Badge className="bg-green-500 text-white">Active</Badge>
              ) : (
                <Badge variant="destructive">Disabled</Badge>
              )}

              <Button
                variant="outline"
                size="sm"
                onClick={handleRotateSecret}
                disabled={rotating || !isAdminOrOwner}
                title="Rotate signing secret"
              >
                {rotating ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <RefreshCw className="w-4 h-4" />
                )}
                <span className="ml-1.5">Rotate Secret</span>
              </Button>

              <Button
                variant="outline"
                size="sm"
                onClick={handleDelete}
                disabled={deleting || !isAdminOrOwner}
                className="text-destructive hover:text-destructive border-destructive/30 hover:border-destructive"
                title="Delete webhook"
              >
                {deleting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Trash2 className="w-4 h-4" />
                )}
                <span className="ml-1.5">Delete</span>
              </Button>
            </div>
          </div>

          {/* New secret reveal */}
          {newSecret && (
            <div className="mt-4 p-4 rounded-lg border border-yellow-400 bg-yellow-50 dark:bg-yellow-950/30">
              <p className="text-sm font-medium text-yellow-800 dark:text-yellow-300">
                New signing secret — copy it now. It will not be shown again.
              </p>
              <SecretReveal secret={newSecret} />
            </div>
          )}
        </div>

        {/* Tabs */}
        <Tabs defaultValue="configuration" className="animate-slide-up">
          <TabsList>
            <TabsTrigger value="configuration">Configuration</TabsTrigger>
            <TabsTrigger value="delivery-log">Delivery Log</TabsTrigger>
          </TabsList>

          {/* ── Configuration Tab ──────────────────────────────────── */}
          <TabsContent value="configuration" className="mt-4 space-y-6">

            <Card>
              <CardHeader className="border-b border-border">
                <CardTitle>General</CardTitle>
              </CardHeader>
              <CardContent className="pt-5 space-y-4">

                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Name</label>
                  <Input
                    data-testid="webhook-name-input"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    placeholder="e.g. Slack Bot"
                    disabled={!isAdminOrOwner}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-sm font-medium">URL</label>
                  <Input
                    data-testid="webhook-url-input"
                    value={url}
                    onChange={e => setUrl(e.target.value)}
                    placeholder="https://example.com/webhook"
                    type="url"
                    disabled={!isAdminOrOwner}
                  />
                </div>

                <div className="flex items-center gap-2">
                  <Checkbox
                    id="is-active"
                    checked={isActive}
                    onCheckedChange={(checked) => setIsActive(!!checked)}
                    disabled={!isAdminOrOwner}
                  />
                  <label htmlFor="is-active" className="text-sm font-medium cursor-pointer">
                    Active (receive deliveries)
                  </label>
                </div>

              </CardContent>
            </Card>

            {/* Events */}
            <Card>
              <CardHeader className="border-b border-border">
                <CardTitle>Events</CardTitle>
              </CardHeader>
              <CardContent className="pt-4 space-y-2">
                {WEBHOOK_EVENTS.map(ev => (
                  <div key={ev.id} className="flex items-center gap-3">
                    <Checkbox
                      id={`event-${ev.id}`}
                      checked={selectedEvents.includes(ev.id)}
                      onCheckedChange={() => toggleEvent(ev.id)}
                      disabled={!isAdminOrOwner}
                      data-testid={`event-checkbox-${ev.id}`}
                    />
                    <label htmlFor={`event-${ev.id}`} className="font-mono text-sm cursor-pointer">{ev.id}</label>
                    <span className="text-sm text-muted-foreground">{ev.label}</span>
                  </div>
                ))}

                {/* Category filter — only shown when category_match is selected */}
                {selectedEvents.includes('feedback.category_match') && (
                  <div className="mt-3 pl-7 space-y-1.5">
                    <label className="text-sm font-medium">Category Filters</label>
                    <Input
                      placeholder="Comma-separated tags, e.g. billing,authentication"
                      value={categoryFilters.join(', ')}
                      onChange={e =>
                        setCategoryFilters(
                          e.target.value
                            .split(',')
                            .map(s => s.trim())
                            .filter(Boolean)
                        )
                      }
                      disabled={!isAdminOrOwner}
                      data-testid="category-filters-input"
                    />
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Retry Mode */}
            <Card>
              <CardHeader className="border-b border-border">
                <CardTitle>Retry Mode</CardTitle>
              </CardHeader>
              <CardContent className="pt-4">
                <ToggleGroup
                  type="single"
                  value={retryMode}
                  onValueChange={(val) => { if (val) setRetryMode(val as typeof retryMode); }}
                  disabled={!isAdminOrOwner}
                  className="flex flex-col items-stretch gap-2"
                >
                  <ToggleGroupItem
                    value="fire_and_forget"
                    variant="outline"
                    className="justify-start gap-2 h-auto py-2.5 px-3 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground data-[state=on]:border-primary"
                  >
                    <div className="text-left">
                      <span className="text-sm font-medium">Fire and forget</span>
                      <p className="text-xs opacity-70">Single POST attempt. No retries.</p>
                    </div>
                  </ToggleGroupItem>
                  <ToggleGroupItem
                    value="exponential_backoff"
                    variant="outline"
                    className="justify-start gap-2 h-auto py-2.5 px-3 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground data-[state=on]:border-primary"
                  >
                    <div className="text-left">
                      <span className="text-sm font-medium">Exponential backoff</span>
                      <p className="text-xs opacity-70">Up to 3 retries at 1 min, 5 min, 30 min intervals.</p>
                    </div>
                  </ToggleGroupItem>
                </ToggleGroup>
              </CardContent>
            </Card>

            {/* Custom Headers */}
            <Card>
              <CardHeader className="border-b border-border">
                <div className="flex items-center justify-between">
                  <CardTitle>Custom Headers</CardTitle>
                  {isAdminOrOwner && (
                    <Button variant="outline" size="sm" onClick={addHeader}>
                      Add Header
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent className="pt-4 space-y-2">
                {customHeaders.length === 0 ? (
                  <p className="text-sm text-muted-foreground italic">No custom headers</p>
                ) : (
                  customHeaders.map((h, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <Input
                        placeholder="Header name"
                        value={h.key}
                        onChange={e => updateHeader(i, 'key', e.target.value)}
                        disabled={!isAdminOrOwner}
                        className="flex-1 font-mono text-sm"
                      />
                      <Input
                        placeholder="Value"
                        value={h.value}
                        onChange={e => updateHeader(i, 'value', e.target.value)}
                        disabled={!isAdminOrOwner}
                        className="flex-1 font-mono text-sm"
                        type="password"
                      />
                      {isAdminOrOwner && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => removeHeader(i)}
                          className="text-destructive hover:text-destructive"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      )}
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            {/* Save */}
            {isAdminOrOwner && (
              <div className="flex justify-end">
                <Button onClick={handleSave} disabled={saving}>
                  {saving ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Saving…</>
                  ) : (
                    <><Save className="w-4 h-4 mr-2" />Save Changes</>
                  )}
                </Button>
              </div>
            )}

          </TabsContent>

          {/* ── Delivery Log Tab ───────────────────────────────────── */}
          <TabsContent value="delivery-log" className="mt-4">
            <Card>
              <CardHeader className="border-b border-border">
                <CardTitle>Delivery Log (last 50)</CardTitle>
              </CardHeader>
              <CardContent className="pt-4">
                {deliveries.length === 0 ? (
                  <p className="text-center py-8 text-muted-foreground text-sm">
                    No deliveries yet.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border text-muted-foreground text-left">
                          <th className="pb-2 font-medium">Timestamp</th>
                          <th className="pb-2 font-medium">Event</th>
                          <th className="pb-2 font-medium">Status</th>
                          <th className="pb-2 font-medium">Response Code</th>
                          <th className="pb-2 font-medium">Latency</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {deliveries.map(del => (
                          <React.Fragment key={del.id}>
                            <tr
                              className="hover:bg-muted/30 transition-colors cursor-pointer"
                              onClick={() =>
                                setExpandedDelivery(prev => (prev === del.id ? null : del.id))
                              }
                            >
                              <td className="py-2.5 text-muted-foreground text-xs">
                                {formatTs(del.created_at)}
                              </td>
                              <td className="py-2.5">
                                <Badge variant="outline" className="font-mono text-xs">
                                  {del.event}
                                </Badge>
                              </td>
                              <td className="py-2.5">
                                <DeliveryStatusBadge status={del.status} />
                              </td>
                              <td className="py-2.5 font-mono">
                                {del.response_code ?? '—'}
                              </td>
                              <td className="py-2.5 text-muted-foreground">
                                {del.latency_ms != null ? `${del.latency_ms}ms` : '—'}
                              </td>
                            </tr>

                            {expandedDelivery === del.id && (
                              <tr>
                                <td colSpan={5} className="pb-3 px-2">
                                  <div className="rounded-md bg-muted p-3 space-y-2 text-xs font-mono">
                                    {del.error_message && (
                                      <div>
                                        <span className="font-semibold text-destructive">Error: </span>
                                        {del.error_message}
                                      </div>
                                    )}
                                    {del.response_body && (
                                      <div>
                                        <span className="font-semibold">Response body: </span>
                                        <span className="text-muted-foreground">{del.response_body}</span>
                                      </div>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

        </Tabs>
      </main>

      {/* Confirm Dialog */}
      <Dialog open={!!confirmAction} onOpenChange={(open) => { if (!open) setConfirmAction(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Confirm Action</DialogTitle>
            <DialogDescription>{confirmMessage}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmAction(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => { confirmAction?.(); setConfirmAction(null); }}>Confirm</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rotate Secret Confirmation Dialog (unused — handled via confirm() inline) */}
      <Dialog open={rotateDialogOpen} onOpenChange={setRotateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rotate Signing Secret</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This will invalidate your current signing secret. All receivers must be updated with
            the new secret to continue verifying deliveries.
          </p>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={() => setRotateDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                setRotateDialogOpen(false);
                handleRotateSecret();
              }}
              disabled={rotating}
            >
              {rotating ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null}
              Rotate Secret
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
