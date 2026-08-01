'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  AlertCircle,
  ArrowLeft,
  Check,
  CheckCircle,
  Copy,
  Eye,
  EyeOff,
  Loader2,
  Trash2,
  XCircle,
} from 'lucide-react';
import { intercomAPI, IntercomConnectionStatus } from '@/lib/api/intercom';
import { useAuth } from '@/contexts/AuthContext';
import { IntercomIcon } from '@/components/icons/IntercomIcon';

// The webhook is served by the BACKEND, not the Next.js app — same pattern as
// the Zendesk page and settings/api-keys.
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const INTERCOM_WEBHOOK_URL = `${API_BASE}/api/v1/webhooks/intercom/events`;

export default function IntercomSettingsPage() {
  const router = useRouter();
  const { user } = useAuth();

  const [status, setStatus] = useState<IntercomConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const [tokenInput, setTokenInput] = useState('');
  const [secretInput, setSecretInput] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [showSecret, setShowSecret] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);

  const [disconnectOpen, setDisconnectOpen] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [copied, setCopied] = useState(false);

  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';

  useEffect(() => {
    if (user && !isAdminOrOwner) {
      router.replace('/settings/preferences');
    }
  }, [user, isAdminOrOwner, router]);

  const loadStatus = useCallback(async () => {
    try {
      const data = await intercomAPI.getStatus();
      setStatus(data);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    setConnectError(null);
    setConnecting(true);
    try {
      await intercomAPI.connect({
        access_token: tokenInput.trim(),
        // Omit rather than send an empty string — the backend treats an absent
        // client_secret as "keep whatever is stored" on reconnect.
        ...(secretInput.trim() ? { client_secret: secretInput.trim() } : {}),
      });
      setTokenInput('');
      setSecretInput('');
      await loadStatus();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setConnectError(detail || 'Failed to connect to Intercom');
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    setDisconnecting(true);
    try {
      await intercomAPI.disconnect();
      setDisconnectOpen(false);
      await loadStatus();
    } catch {
      // Status reload below reflects whatever actually happened.
    } finally {
      setDisconnecting(false);
    }
  };

  const copyWebhookUrl = () => {
    navigator.clipboard?.writeText(INTERCOM_WEBHOOK_URL);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!user || !isAdminOrOwner) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/settings/integrations">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="w-4 h-4 mr-1" />
            Integrations
          </Button>
        </Link>
      </div>

      <div className="flex items-center gap-3">
        <IntercomIcon className="w-8 h-8" />
        <div>
          <h1 className="text-2xl font-semibold">Intercom</h1>
          <p className="text-sm text-muted-foreground">
            Pull conversations, replies and ratings in as feedback.
          </p>
        </div>
        {status?.connected && (
          <Badge variant="secondary" className="ml-auto">
            <CheckCircle className="w-3 h-3 mr-1" />
            Connected
          </Badge>
        )}
      </div>

      {loading ? (
        <Card>
          <CardContent className="py-10 flex justify-center">
            <Loader2 className="w-5 h-5 animate-spin" />
          </CardContent>
        </Card>
      ) : status?.connected ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Connection</CardTitle>
              <CardDescription>
                {status.workspace_name
                  ? `Workspace: ${status.workspace_name}`
                  : 'Connected via an access token'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-muted-foreground">Workspace ID</dt>
                  <dd>{status.workspace_id || '—'}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Token</dt>
                  <dd>{status.token_hint ? `…${status.token_hint}` : '—'}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Last synced</dt>
                  <dd>
                    {status.last_synced_at
                      ? new Date(status.last_synced_at).toLocaleString()
                      : 'Not yet — the first pull runs within 15 minutes'}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Status</dt>
                  <dd>{status.last_sync_status || '—'}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Feedback ingested</dt>
                  <dd>{status.feedback_items_ingested ?? 0}</dd>
                </div>
              </dl>

              {status.last_error && (
                <Alert variant="destructive">
                  <AlertCircle className="w-4 h-4" />
                  <AlertDescription>{status.last_error}</AlertDescription>
                </Alert>
              )}

              {status.has_feedback_source &&
                status.feedback_items_ingested === 0 &&
                status.last_synced_at && (
                  <Alert>
                    <AlertCircle className="w-4 h-4" />
                    <AlertDescription>
                      Connected and syncing, but no feedback has been ingested
                      yet. That is expected if no one has written in since you
                      connected — Rereflect only picks up conversations updated
                      after that point, and never backfills history.
                    </AlertDescription>
                  </Alert>
                )}

              {!status.has_feedback_source && (
                <Alert>
                  <AlertCircle className="w-4 h-4" />
                  <AlertDescription>
                    No Intercom feedback source exists for this organization, so
                    nothing will be ingested. Reconnect to provision one.
                  </AlertDescription>
                </Alert>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Real-time webhook (optional)</CardTitle>
              <CardDescription>
                Conversations are pulled every 15 minutes without any webhook.
                Add one for near-instant delivery.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-2">
                <code className="flex-1 text-xs bg-muted px-2 py-1.5 rounded break-all">
                  {INTERCOM_WEBHOOK_URL}
                </code>
                <Button variant="outline" size="sm" onClick={copyWebhookUrl}>
                  {copied ? (
                    <Check className="w-4 h-4" />
                  ) : (
                    <Copy className="w-4 h-4" />
                  )}
                </Button>
              </div>
              <p className="text-sm text-muted-foreground">
                Add this URL under <strong>Developer Hub → Configure →
                Webhooks</strong> in Intercom and subscribe to the{' '}
                <code>conversation.user.created</code>,{' '}
                <code>conversation.user.replied</code> and{' '}
                <code>conversation.rating.added</code> topics. Intercom does not
                offer an API for creating subscriptions, so this step is manual.
              </p>
              {status.has_client_secret ? (
                <Alert>
                  <CheckCircle className="w-4 h-4" />
                  <AlertDescription>
                    A Client Secret is stored, so webhook deliveries are verified
                    against this workspace specifically.
                  </AlertDescription>
                </Alert>
              ) : (
                <Alert variant="destructive">
                  <XCircle className="w-4 h-4" />
                  <AlertDescription>
                    No Client Secret stored. Webhook deliveries will be rejected
                    unless a global <code>INTERCOM_CLIENT_SECRET</code> is set.
                    Reconnect with your app&apos;s Client Secret to enable
                    per-workspace verification. The 15-minute pull is unaffected.
                  </AlertDescription>
                </Alert>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Disconnect</CardTitle>
              <CardDescription>
                Stops all syncing. Feedback already ingested is kept, and the
                feedback source is left in place.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button
                variant="destructive"
                onClick={() => setDisconnectOpen(true)}
              >
                <Trash2 className="w-4 h-4 mr-2" />
                Disconnect Intercom
              </Button>
            </CardContent>
          </Card>
        </>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Connect Intercom</CardTitle>
            <CardDescription>
              Create a private app in your Intercom Developer Hub, then paste its
              Access Token below. No OAuth app registration required.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleConnect} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="access-token">Access Token</Label>
                <div className="flex gap-2">
                  <Input
                    id="access-token"
                    type={showToken ? 'text' : 'password'}
                    value={tokenInput}
                    onChange={(e) => setTokenInput(e.target.value)}
                    placeholder="dG9rOjxyYW5kb20+"
                    required
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    aria-label={showToken ? 'Hide token' : 'Show token'}
                    onClick={() => setShowToken((v) => !v)}
                  >
                    {showToken ? (
                      <EyeOff className="w-4 h-4" />
                    ) : (
                      <Eye className="w-4 h-4" />
                    )}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Developer Hub → your app → Configure → Authentication.
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="client-secret">
                  Client Secret{' '}
                  <span className="text-muted-foreground">(optional)</span>
                </Label>
                <div className="flex gap-2">
                  <Input
                    id="client-secret"
                    type={showSecret ? 'text' : 'password'}
                    value={secretInput}
                    onChange={(e) => setSecretInput(e.target.value)}
                    placeholder="Only needed for real-time webhooks"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    aria-label={showSecret ? 'Hide secret' : 'Show secret'}
                    onClick={() => setShowSecret((v) => !v)}
                  >
                    {showSecret ? (
                      <EyeOff className="w-4 h-4" />
                    ) : (
                      <Eye className="w-4 h-4" />
                    )}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Developer Hub → your app → Basic Info. Intercom signs webhook
                  deliveries with it, so storing it here lets Rereflect verify
                  them against your workspace specifically. Skip it if you only
                  want the 15-minute pull.
                </p>
              </div>

              {connectError && (
                <Alert variant="destructive">
                  <AlertCircle className="w-4 h-4" />
                  <AlertDescription>{connectError}</AlertDescription>
                </Alert>
              )}

              <Button type="submit" disabled={connecting || !tokenInput.trim()}>
                {connecting && (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                )}
                Connect
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      <Dialog open={disconnectOpen} onOpenChange={setDisconnectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Disconnect Intercom?</DialogTitle>
            <DialogDescription>
              Syncing stops immediately. Feedback already ingested is kept, and
              you can reconnect at any time.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDisconnectOpen(false)}
              disabled={disconnecting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDisconnect}
              disabled={disconnecting}
            >
              {disconnecting && (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              )}
              Disconnect
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
