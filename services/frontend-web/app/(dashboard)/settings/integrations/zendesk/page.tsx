'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
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
  CheckCircle,
  Check,
  Copy,
  Eye,
  EyeOff,
  Loader2,
  RefreshCw,
  Send,
  Trash2,
  XCircle,
} from 'lucide-react';
import { zendeskAPI, ZendeskConnectionStatus } from '@/lib/api/zendesk';
import { useAuth } from '@/contexts/AuthContext';
import { ZendeskIcon } from '@/components/icons/ZendeskIcon';
import { ZendeskStatusSyncCard } from '@/components/settings/ZendeskStatusSyncCard';

// The public API is served by the BACKEND, not the Next.js app — same
// pattern as settings/api-keys/page.tsx.
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const ZENDESK_WEBHOOK_URL = `${API_BASE}/api/v1/webhooks/zendesk/events`;

export default function ZendeskSettingsPage() {
  const router = useRouter();
  const { user } = useAuth();

  // Connection state
  const [status, setStatus] = useState<ZendeskConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);

  // Connect form state
  const [subdomain, setSubdomain] = useState('');
  const [email, setEmail] = useState('');
  const [tokenInput, setTokenInput] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);

  // One-time webhook secret reveal (from the connect response only —
  // GET /status never returns it; degrade gracefully if we don't have it).
  const [webhookSecret, setWebhookSecret] = useState<string | null>(null);
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [copiedSecret, setCopiedSecret] = useState(false);

  // Test state
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  // Sync state (should-have: manual "Sync now")
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<{ success: boolean; message: string } | null>(null);

  // Disconnect confirm dialog
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';

  // Redirect members to preferences
  useEffect(() => {
    if (user && !isAdminOrOwner) {
      router.replace('/settings/preferences');
    }
  }, [user, isAdminOrOwner, router]);

  const fetchStatus = useCallback(async () => {
    try {
      const s = await zendeskAPI.getStatus();
      setStatus(s);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchStatus().finally(() => setLoading(false));
  }, [fetchStatus]);

  const handleConnect = async () => {
    if (!subdomain.trim() || !email.trim() || !tokenInput.trim()) {
      setConnectError('Please enter your Zendesk subdomain, email, and API token.');
      return;
    }
    setConnecting(true);
    setConnectError(null);
    setTestResult(null);
    setSyncResult(null);
    try {
      const result = await zendeskAPI.connect({
        subdomain: subdomain.trim(),
        email: email.trim(),
        api_token: tokenInput.trim(),
      });
      setStatus({
        connected: result.connected,
        subdomain: result.subdomain,
        email: result.email,
        token_hint: result.token_hint,
        account_user_id: result.account_user_id,
        display_name: result.display_name,
        is_active: true,
        last_synced_at: null,
        last_sync_status: null,
        last_error: null,
        connected_at: null,
        has_feedback_source: result.has_feedback_source,
        status_sync_enabled: false,
        status_mapping: null,
        last_status_synced_at: null,
        last_status_sync_error: null,
      });
      // Display-once: only ever present on the connect response.
      setWebhookSecret(result.webhook_secret ?? null);
      setTokenInput('');  // clear after successful connect
    } catch (err: any) {
      const msg: string =
        err?.response?.data?.detail ?? 'Failed to connect Zendesk. Check your subdomain, email, and API token.';
      setConnectError(msg);
    } finally {
      setConnecting(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await zendeskAPI.testConnection();
      setTestResult({ success: res.success, message: res.message ?? '' });
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err?.response?.data?.detail ?? 'Connection test failed.',
      });
    } finally {
      setTesting(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      await zendeskAPI.triggerSync();
      setSyncResult({ success: true, message: 'Sync started — new tickets will appear shortly.' });
    } catch (err: any) {
      setSyncResult({
        success: false,
        message: err?.response?.data?.detail ?? 'Could not start sync. Please try again shortly.',
      });
    } finally {
      setSyncing(false);
    }
  };

  const handleDisconnect = async () => {
    setDisconnecting(true);
    try {
      await zendeskAPI.disconnect();
      setStatus(null);
      setTestResult(null);
      setSyncResult(null);
      setWebhookSecret(null);
    } catch {
      // ignore
    } finally {
      setDisconnecting(false);
      setConfirmDisconnect(false);
    }
  };

  const copyWebhookUrl = () => {
    navigator.clipboard.writeText(ZENDESK_WEBHOOK_URL);
    setCopiedUrl(true);
    setTimeout(() => setCopiedUrl(false), 2000);
  };

  const copyWebhookSecret = () => {
    if (webhookSecret) {
      navigator.clipboard.writeText(webhookSecret);
      setCopiedSecret(true);
      setTimeout(() => setCopiedSecret(false), 2000);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen pattern-bg">
        <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Header */}
        <div className="animate-fade-in">
          <Link
            href="/settings/integrations"
            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors mb-4"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Integrations
          </Link>

          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-[#03363D]/10">
              <ZendeskIcon className="w-7 h-7 text-[#03363D]" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground">Zendesk</h1>
              <p className="text-muted-foreground text-sm">
                Connect your Zendesk account to turn support tickets into feedback.
              </p>
            </div>
            {status?.connected && (
              <Badge
                variant="outline"
                className="ml-auto text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950"
              >
                Connected
              </Badge>
            )}
          </div>
        </div>

        {/* Connection status / connect form */}
        <Card className="animate-slide-up">
          <CardHeader>
            <CardTitle>
              {status?.connected ? 'Connection Details' : 'Connect Zendesk'}
            </CardTitle>
            <CardDescription>
              {status?.connected
                ? 'Your Zendesk account is connected. You can test, sync, or disconnect below.'
                : 'Create an API token in Zendesk and paste it below along with your subdomain and agent email.'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {status?.connected ? (
              /* Connected state */
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  {status.subdomain && (
                    <div>
                      <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                        Subdomain
                      </p>
                      <p className="font-medium text-foreground font-mono">{status.subdomain}.zendesk.com</p>
                    </div>
                  )}
                  {status.email && (
                    <div>
                      <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                        Email
                      </p>
                      <p className="font-medium text-foreground">{status.email}</p>
                    </div>
                  )}
                  {status.token_hint && (
                    <div>
                      <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                        Token
                      </p>
                      <p className="font-mono text-foreground">{status.token_hint}</p>
                    </div>
                  )}
                  {status.display_name && (
                    <div>
                      <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                        Connected As
                      </p>
                      <p className="text-foreground">{status.display_name}</p>
                    </div>
                  )}
                  {status.connected_at && (
                    <div>
                      <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                        Connected
                      </p>
                      <p className="text-foreground">{new Date(status.connected_at).toLocaleString()}</p>
                    </div>
                  )}
                  {status.last_synced_at && (
                    <div>
                      <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                        Last Synced
                      </p>
                      <p className="text-foreground">{new Date(status.last_synced_at).toLocaleString()}</p>
                    </div>
                  )}
                </div>

                {/* has_feedback_source guard: connect auto-provisions a
                    zendesk FeedbackSource, but surface it clearly if it's
                    somehow missing (edge case per plan §edge cases) so the
                    operator knows tickets won't flow yet. */}
                {status.has_feedback_source === false && (
                  <Alert>
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>
                      No Zendesk feedback source exists yet, so tickets won&apos;t be ingested.{' '}
                      <Link href="/feedback-sources/new?type=zendesk" className="underline">
                        Create one
                      </Link>{' '}
                      to start receiving tickets.
                    </AlertDescription>
                  </Alert>
                )}

                {status.last_error && (
                  <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{status.last_error}</AlertDescription>
                  </Alert>
                )}

                {isAdminOrOwner && (
                  <div className="flex flex-wrap items-center gap-3 pt-2">
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
                      Test Connection
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleSync}
                      disabled={syncing}
                    >
                      {syncing ? (
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      ) : (
                        <RefreshCw className="w-4 h-4 mr-2" />
                      )}
                      Sync tickets
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-destructive hover:bg-destructive hover:text-destructive-foreground"
                      onClick={() => setConfirmDisconnect(true)}
                    >
                      <Trash2 className="w-4 h-4 mr-2" />
                      Disconnect
                    </Button>
                  </div>
                )}

                {testResult && (
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

                {syncResult && (
                  <div
                    className={`p-3 rounded-lg text-sm flex items-center gap-2 ${
                      syncResult.success
                        ? 'bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300'
                        : 'bg-destructive/10 text-destructive'
                    }`}
                  >
                    {syncResult.success ? (
                      <CheckCircle className="w-4 h-4 flex-shrink-0" />
                    ) : (
                      <XCircle className="w-4 h-4 flex-shrink-0" />
                    )}
                    {syncResult.message}
                  </div>
                )}
              </div>
            ) : (
              /* Disconnected state — connect form */
              isAdminOrOwner ? (
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="zendesk-subdomain">Subdomain</Label>
                    <Input
                      id="zendesk-subdomain"
                      type="text"
                      placeholder="your-company"
                      value={subdomain}
                      onChange={(e) => setSubdomain(e.target.value)}
                      className="font-mono text-sm"
                      autoComplete="off"
                    />
                    <p className="text-xs text-muted-foreground">
                      Your Zendesk subdomain, e.g. <code className="font-mono">your-company.zendesk.com</code>.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="zendesk-email">Email</Label>
                    <Input
                      id="zendesk-email"
                      type="email"
                      placeholder="you@company.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      autoComplete="off"
                    />
                    <p className="text-xs text-muted-foreground">
                      The Zendesk agent email associated with the API token below.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="zendesk-api-token">API Token</Label>
                    <div className="relative">
                      <Input
                        id="zendesk-api-token"
                        type={showToken ? 'text' : 'password'}
                        placeholder="zdsk-api-token..."
                        value={tokenInput}
                        onChange={(e) => setTokenInput(e.target.value)}
                        className="pr-10 font-mono text-sm"
                        autoComplete="off"
                      />
                      <button
                        type="button"
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                        onClick={() => setShowToken((v) => !v)}
                        aria-label={showToken ? 'Hide token' : 'Show token'}
                      >
                        {showToken ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Create an API token in Zendesk Admin Center → Apps and integrations → APIs →
                      Zendesk API → enable token access → add API token.
                    </p>
                  </div>

                  {connectError && (
                    <Alert variant="destructive">
                      <AlertCircle className="h-4 w-4" />
                      <AlertDescription>{connectError}</AlertDescription>
                    </Alert>
                  )}

                  <Button onClick={handleConnect} disabled={connecting}>
                    {connecting ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Connecting…
                      </>
                    ) : (
                      'Connect Zendesk'
                    )}
                  </Button>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Contact an admin to connect Zendesk.
                </p>
              )
            )}
          </CardContent>
        </Card>

        {/* Inbound status sync (connected state only) */}
        {status?.connected && isAdminOrOwner && (
          <ZendeskStatusSyncCard status={status} onStatusChange={setStatus} />
        )}

        {/* One-time webhook URL + secret reveal (new — no Jira equivalent).
            Only rendered once we actually have a plaintext secret in hand
            (from this session's connect response); GET /status never
            returns it, so a page refresh can't re-show it. */}
        {status?.connected && isAdminOrOwner && (
          <Card className="animate-slide-up">
            <CardHeader>
              <CardTitle className="text-base">Set up real-time sync (optional)</CardTitle>
              <CardDescription>
                Polling works without this — add a Zendesk trigger/webhook target for real-time
                ticket ingestion.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>Webhook URL</Label>
                <div className="flex items-center gap-2">
                  <Input readOnly value={ZENDESK_WEBHOOK_URL} className="font-mono text-sm" />
                  <Button variant="outline" onClick={copyWebhookUrl}>
                    {copiedUrl ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  </Button>
                </div>
              </div>

              {webhookSecret ? (
                <div className="space-y-2">
                  <Label>Webhook Secret</Label>
                  <div className="flex items-center gap-2">
                    <Input readOnly value={webhookSecret} className="font-mono text-sm" />
                    <Button variant="outline" onClick={copyWebhookSecret}>
                      {copiedSecret ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Save this secret now — you won&apos;t be able to view it again. Add it as a
                    Zendesk trigger/webhook target to get real-time ticket ingestion (optional;
                    polling works without it).
                  </p>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Webhook secret already configured — reconnect (re-enter your API token) to view
                  it again.
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {/* Help card */}
        <Card className="animate-slide-up stagger-1">
          <CardHeader>
            <CardTitle className="text-base">How to get your API token</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="text-sm text-muted-foreground space-y-1 list-decimal list-inside">
              <li>Go to <strong>{subdomain || 'your-company'}.zendesk.com</strong> → Admin Center</li>
              <li>Navigate to <strong>Apps and integrations</strong> → <strong>APIs</strong> → <strong>Zendesk API</strong></li>
              <li>Enable <strong>Token access</strong> and click <strong>Add API token</strong></li>
              <li>Name the token and copy it</li>
              <li>Paste your subdomain, agent email, and the token above, then click <strong>Connect Zendesk</strong></li>
            </ol>
          </CardContent>
        </Card>
      </main>

      {/* Disconnect confirm dialog */}
      <Dialog open={confirmDisconnect} onOpenChange={(open) => { if (!open) setConfirmDisconnect(false); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Disconnect Zendesk?</DialogTitle>
            <DialogDescription>
              This will remove the Zendesk connection. Existing feedback ingested from tickets
              will not be deleted.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDisconnect(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDisconnect}
              disabled={disconnecting}
            >
              {disconnecting ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : null}
              Disconnect
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
