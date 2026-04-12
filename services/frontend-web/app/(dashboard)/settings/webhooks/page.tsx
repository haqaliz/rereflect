'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  webhooksAPI,
  WEBHOOK_EVENTS,
  PLAN_WEBHOOK_LIMITS,
  type WebhookEndpoint,
  type TestWebhookResult,
} from '@/lib/api/webhooks';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Webhook,
  Plus,
  Trash2,
  ExternalLink,
  FlaskConical,
  Loader2,
} from 'lucide-react';
import { toast } from 'sonner';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function truncateUrl(url: string, max = 50): string {
  try {
    const u = new URL(url);
    const display = u.hostname + u.pathname;
    return display.length > max ? display.slice(0, max) + '…' : display;
  } catch {
    return url.length > max ? url.slice(0, max) + '…' : url;
  }
}

function StatusBadge({ webhook }: { webhook: WebhookEndpoint }) {
  if (!webhook.is_active) {
    return <Badge variant="destructive">Disabled</Badge>;
  }
  if (webhook.consecutive_failures >= 3) {
    return <Badge className="bg-yellow-500 text-white hover:bg-yellow-600">Failing</Badge>;
  }
  return <Badge className="bg-green-500 text-white hover:bg-green-600">Active</Badge>;
}

function EventBadges({ events }: { events: string[] }) {
  const MAX_SHOWN = 2;
  const shown = events.slice(0, MAX_SHOWN);
  const overflow = events.length - MAX_SHOWN;

  return (
    <div className="flex flex-wrap gap-1 items-center">
      {shown.map(ev => (
        <Badge key={ev} variant="outline" className="text-xs font-mono">
          {ev}
        </Badge>
      ))}
      {overflow > 0 && (
        <Badge variant="secondary" className="text-xs">
          +{overflow}
        </Badge>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function WebhooksPage() {
  const { user } = useAuth();
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [webhooks, setWebhooks] = useState<WebhookEndpoint[]>([]);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [confirmAction, setConfirmAction] = useState<(() => void) | null>(null);
  const [confirmMessage, setConfirmMessage] = useState('');

  const requestConfirm = (message: string, action: () => void) => {
    setConfirmMessage(message);
    setConfirmAction(() => action);
  };

  const plan = user?.plan ?? 'free';
  const planLimit = PLAN_WEBHOOK_LIMITS[plan];
  const atLimit = planLimit !== null && webhooks.length >= planLimit;

  useEffect(() => {
    async function load() {
      try {
        const data = await webhooksAPI.list();
        setWebhooks(data.webhooks);
      } catch {
        toast.error('Failed to load webhooks');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const handleDelete = useCallback((webhook: WebhookEndpoint) => {
    requestConfirm(
      `Delete "${webhook.name}"? This cannot be undone.`,
      async () => {
        setDeletingId(webhook.id);
        try {
          await webhooksAPI.delete(webhook.id);
          setWebhooks(prev => prev.filter(w => w.id !== webhook.id));
          toast.success('Webhook deleted');
        } catch {
          toast.error('Failed to delete webhook');
        } finally {
          setDeletingId(null);
        }
      }
    );
  }, []);

  const handleTest = useCallback(async (webhook: WebhookEndpoint) => {
    setTestingId(webhook.id);
    try {
      const result: TestWebhookResult = await webhooksAPI.test(webhook.id);
      if (result.success) {
        toast.success(`Test delivered — ${result.response_code} in ${result.latency_ms}ms`);
      } else {
        toast.error(`Test failed — ${result.response_code ?? result.error_message}`);
      }
    } catch {
      toast.error('Test delivery failed');
    } finally {
      setTestingId(null);
    }
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 border-4 border-primary/20 rounded-full" />
            <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
          <p className="text-muted-foreground font-medium">Loading webhooks...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">

        {/* Page Header */}
        <div className="animate-fade-in">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center space-x-3">
              <div className="p-3 bg-secondary rounded-xl">
                <Webhook className="w-8 h-8 text-primary" />
              </div>
              <div>
                <h1 className="text-4xl font-bold text-foreground">Webhooks</h1>
                <p className="text-muted-foreground text-lg">
                  Receive real-time HTTP notifications on feedback events
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {/* Plan limit indicator */}
              <span className="text-sm text-muted-foreground" data-testid="plan-limit-indicator">
                {webhooks.length}/{planLimit ?? '∞'} webhooks used
              </span>

              <Button
                onClick={() => !atLimit && router.push('/settings/webhooks/new')}
                disabled={atLimit}
                title={atLimit ? `Plan limit reached (${planLimit} webhooks). Upgrade to add more.` : undefined}
                className="flex items-center gap-2"
              >
                <Plus className="w-4 h-4" />
                Add Webhook
              </Button>
            </div>
          </div>
        </div>

        {/* Webhooks Table */}
        <Card className="animate-slide-up">
          <CardHeader className="border-b border-border">
            <CardTitle>Webhook Endpoints ({webhooks.length})</CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            {webhooks.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground" data-testid="empty-state">
                <Webhook className="w-10 h-10 mx-auto mb-3 opacity-30" />
                <p className="font-medium">No webhooks configured</p>
                <p className="text-sm mt-1">
                  Add a webhook to receive real-time notifications for feedback events.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground text-left">
                      <th className="pb-2 font-medium">Name</th>
                      <th className="pb-2 font-medium">URL</th>
                      <th className="pb-2 font-medium">Events</th>
                      <th className="pb-2 font-medium">Status</th>
                      <th className="pb-2 font-medium text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {webhooks.map(webhook => (
                      <tr key={webhook.id} className="hover:bg-muted/30 transition-colors">
                        <td className="py-3 font-medium">
                          <Link
                            href={`/settings/webhooks/${webhook.id}`}
                            className="hover:underline text-foreground"
                          >
                            {webhook.name}
                          </Link>
                        </td>
                        <td className="py-3 text-muted-foreground font-mono text-xs">
                          {truncateUrl(webhook.url)}
                        </td>
                        <td className="py-3">
                          <EventBadges events={webhook.events} />
                        </td>
                        <td className="py-3">
                          <StatusBadge webhook={webhook} />
                        </td>
                        <td className="py-3">
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleTest(webhook)}
                              disabled={testingId === webhook.id}
                              title="Send test delivery"
                            >
                              {testingId === webhook.id ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                              ) : (
                                <FlaskConical className="w-4 h-4" />
                              )}
                              <span className="ml-1">Test</span>
                            </Button>

                            <Button
                              variant="ghost"
                              size="sm"
                              asChild
                              title="Edit webhook"
                            >
                              <Link href={`/settings/webhooks/${webhook.id}`}>
                                <ExternalLink className="w-4 h-4" />
                                <span className="ml-1 sr-only">Edit</span>
                              </Link>
                            </Button>

                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDelete(webhook)}
                              disabled={deletingId === webhook.id}
                              className="text-destructive hover:text-destructive"
                              title="Delete webhook"
                            >
                              {deletingId === webhook.id ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                              ) : (
                                <Trash2 className="w-4 h-4" />
                              )}
                              <span className="ml-1">Delete</span>
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

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
    </div>
  );
}
