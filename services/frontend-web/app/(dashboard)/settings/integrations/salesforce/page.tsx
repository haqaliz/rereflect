'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
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
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle,
  Loader2,
  Send,
  Trash2,
  XCircle,
} from 'lucide-react';
import { salesforceAPI, SalesforceConnectionStatus } from '@/lib/api/salesforce';
import { SalesforceIcon } from '@/components/icons/SalesforceIcon';
import { useAuth } from '@/contexts/AuthContext';

export default function SalesforceSettingsPage() {
  const router = useRouter();
  const { user } = useAuth();

  // Connection state
  const [status, setStatus] = useState<SalesforceConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);

  // OAuth connect state
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
      const s = await salesforceAPI.getStatus();
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
    setConnecting(true);
    setConnectError(null);
    try {
      const { auth_url } = await salesforceAPI.getConnectUrl();
      window.location.href = auth_url;
    } catch (err: any) {
      const msg: string =
        err?.response?.data?.detail ?? 'Failed to start Salesforce authorization. Please try again.';
      setConnectError(msg);
      setConnecting(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await salesforceAPI.test();
      setTestResult(res);
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
      await salesforceAPI.disconnect();
      setStatus(null);
      setTestResult(null);
      await fetchStatus();
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
            <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-[#00A1E0]/10">
              <SalesforceIcon className="w-7 h-7 text-[#00A1E0]" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground">Salesforce CRM</h1>
              <p className="text-muted-foreground text-sm">
                Connect your Salesforce org to enrich customer profiles with CRM data.
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

        {/* Connection status / connect CTA */}
        <Card className="animate-slide-up">
          <CardHeader>
            <CardTitle>
              {status?.connected ? 'Connection Details' : 'Connect Salesforce'}
            </CardTitle>
            <CardDescription>
              {status?.connected
                ? 'Your Salesforce org is connected. You can test or disconnect below.'
                : 'Authorize Rereflect to read Accounts, Contacts, and Opportunities from your Salesforce org.'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {status?.connected ? (
              /* Connected state */
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  {status.instance_url && (
                    <div>
                      <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                        Instance URL
                      </p>
                      <p className="font-medium text-foreground font-mono break-all">{status.instance_url}</p>
                    </div>
                  )}
                  {status.sf_org_id && (
                    <div>
                      <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                        Org ID
                      </p>
                      <p className="font-medium text-foreground font-mono">{status.sf_org_id}</p>
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
                  {status.contacts_synced !== undefined && (
                    <div>
                      <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                        Contacts Synced
                      </p>
                      <p className="text-foreground">{status.contacts_synced.toLocaleString()}</p>
                    </div>
                  )}
                  {status.contacts_matched !== undefined && (
                    <div>
                      <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                        Contacts Matched
                      </p>
                      <p className="text-foreground">{status.contacts_matched.toLocaleString()}</p>
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
              /* Disconnected state — OAuth CTA (never a token form) */
              isAdminOrOwner ? (
                <div className="space-y-4">
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
                        Redirecting…
                      </>
                    ) : (
                      'Connect with Salesforce'
                    )}
                  </Button>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Contact an admin to connect Salesforce CRM.
                </p>
              )
            )}
          </CardContent>
        </Card>

        {/* Help card */}
        <Card className="animate-slide-up stagger-1">
          <CardHeader>
            <CardTitle className="text-base">What Rereflect can access</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="text-sm text-muted-foreground space-y-1 list-decimal list-inside">
              <li>Click <strong>Connect with Salesforce</strong> to start the OAuth flow</li>
              <li>Log in to Salesforce and approve the requested scopes (<code className="font-mono">refresh_token offline_access api</code>)</li>
              <li>You&apos;ll be redirected back here once the connection succeeds</li>
              <li>Rereflect reads Accounts, Contacts, and Opportunities to enrich Customer 360 profiles</li>
            </ol>
          </CardContent>
        </Card>
      </main>

      {/* Disconnect confirm dialog */}
      <Dialog open={confirmDisconnect} onOpenChange={(open) => { if (!open) setConfirmDisconnect(false); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Disconnect Salesforce?</DialogTitle>
            <DialogDescription>
              This will remove the Salesforce connection. Existing enrichment data will not be deleted.
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
