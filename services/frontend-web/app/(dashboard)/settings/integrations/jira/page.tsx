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
  Eye,
  EyeOff,
  Loader2,
  Send,
  Trash2,
  XCircle,
} from 'lucide-react';
import { jiraAPI, JiraConnectionStatus } from '@/lib/api/jira';
import { useAuth } from '@/contexts/AuthContext';
import { JiraIcon } from '@/components/icons/JiraIcon';
import { JiraStatusSyncCard } from '@/components/settings/JiraStatusSyncCard';

export default function JiraSettingsPage() {
  const router = useRouter();
  const { user } = useAuth();

  // Connection state
  const [status, setStatus] = useState<JiraConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);

  // Connect form state
  const [siteUrl, setSiteUrl] = useState('');
  const [email, setEmail] = useState('');
  const [tokenInput, setTokenInput] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);

  // Test state
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

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
      const s = await jiraAPI.getStatus();
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
    if (!siteUrl.trim() || !email.trim() || !tokenInput.trim()) {
      setConnectError('Please enter your Jira site URL, email, and API token.');
      return;
    }
    setConnecting(true);
    setConnectError(null);
    setTestResult(null);
    try {
      const result = await jiraAPI.connect({
        site_url: siteUrl.trim(),
        email: email.trim(),
        api_token: tokenInput.trim(),
      });
      setStatus({
        connected: result.connected,
        site_url: result.site_url,
        email: result.email,
        token_hint: result.token_hint,
        account_id: result.account_id,
        display_name: result.display_name,
        is_active: true,
        last_synced_at: null,
        last_sync_status: null,
        last_error: null,
        connected_at: null,
        status_sync_enabled: false,
        status_mapping: null,
        last_status_synced_at: null,
        webhook_enabled: false,
      });
      setTokenInput('');  // clear after successful connect
    } catch (err: any) {
      const msg: string =
        err?.response?.data?.detail ?? 'Failed to connect Jira. Check your site URL, email, and API token.';
      setConnectError(msg);
    } finally {
      setConnecting(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await jiraAPI.testConnection();
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

  const handleDisconnect = async () => {
    setDisconnecting(true);
    try {
      await jiraAPI.disconnect();
      setStatus(null);
      setTestResult(null);
    } catch {
      // ignore
    } finally {
      setDisconnecting(false);
      setConfirmDisconnect(false);
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
            <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-[#0052CC]/10">
              <JiraIcon className="w-7 h-7 text-[#0052CC]" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground">Jira Cloud</h1>
              <p className="text-muted-foreground text-sm">
                Connect your Jira Cloud site to create issues directly from feedback.
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
              {status?.connected ? 'Connection Details' : 'Connect Jira'}
            </CardTitle>
            <CardDescription>
              {status?.connected
                ? 'Your Jira site is connected. You can test or disconnect below.'
                : 'Create an API token in Jira and paste it below along with your site URL and email.'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {status?.connected ? (
              /* Connected state */
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  {status.site_url && (
                    <div>
                      <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                        Site
                      </p>
                      <p className="font-medium text-foreground font-mono">{status.site_url}</p>
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

                {status.last_error && (
                  <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{status.last_error}</AlertDescription>
                  </Alert>
                )}

                {isAdminOrOwner && (
                  <div className="flex items-center gap-3 pt-2">
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
              </div>
            ) : (
              /* Disconnected state — connect form */
              isAdminOrOwner ? (
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="site-url">Jira Site URL</Label>
                    <Input
                      id="site-url"
                      type="text"
                      placeholder="your-company.atlassian.net"
                      value={siteUrl}
                      onChange={(e) => setSiteUrl(e.target.value)}
                      className="font-mono text-sm"
                      autoComplete="off"
                    />
                    <p className="text-xs text-muted-foreground">
                      Your Jira Cloud site, e.g. <code className="font-mono">your-company.atlassian.net</code>.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="jira-email">Email</Label>
                    <Input
                      id="jira-email"
                      type="email"
                      placeholder="you@company.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      autoComplete="off"
                    />
                    <p className="text-xs text-muted-foreground">
                      The Atlassian account email associated with the API token below.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="api-token">API Token</Label>
                    <div className="relative">
                      <Input
                        id="api-token"
                        type={showToken ? 'text' : 'password'}
                        placeholder="ATATT3xFfGF0..."
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
                      Create an API token at{' '}
                      <code className="font-mono">id.atlassian.com/manage-profile/security/api-tokens</code>.
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
                      'Connect Jira'
                    )}
                  </Button>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Contact an admin to connect Jira.
                </p>
              )
            )}
          </CardContent>
        </Card>

        {/* Inbound status sync (connected state only) */}
        {status?.connected && isAdminOrOwner && (
          <JiraStatusSyncCard status={status} onStatusChange={setStatus} />
        )}

        {/* Help card */}
        <Card className="animate-slide-up stagger-1">
          <CardHeader>
            <CardTitle className="text-base">How to get your API token</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="text-sm text-muted-foreground space-y-1 list-decimal list-inside">
              <li>Go to <strong>id.atlassian.com</strong> → Security → API tokens</li>
              <li>Click <strong>Create API token</strong></li>
              <li>Name the token and copy it</li>
              <li>Paste your site URL, Atlassian account email, and the token above</li>
              <li>Click <strong>Connect Jira</strong></li>
            </ol>
          </CardContent>
        </Card>
      </main>

      {/* Disconnect confirm dialog */}
      <Dialog open={confirmDisconnect} onOpenChange={(open) => { if (!open) setConfirmDisconnect(false); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Disconnect Jira?</DialogTitle>
            <DialogDescription>
              This will remove the Jira connection. Existing linked issues will not be deleted.
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
