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
import { hubspotAPI, HubSpotConnectionStatus } from '@/lib/api/hubspot';
import { useAuth } from '@/contexts/AuthContext';
import { HubSpotWritebackCard } from '@/components/settings/HubSpotWritebackCard';

export default function HubSpotSettingsPage() {
  const router = useRouter();
  const { user } = useAuth();

  // Connection state
  const [status, setStatus] = useState<HubSpotConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);

  // Connect form state
  const [tokenInput, setTokenInput] = useState('');
  const [arrPropertyName, setArrPropertyName] = useState('annualrevenue');
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
      const s = await hubspotAPI.getStatus();
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
    if (!tokenInput.trim()) {
      setConnectError('Please enter your HubSpot private app access token.');
      return;
    }
    setConnecting(true);
    setConnectError(null);
    setTestResult(null);
    try {
      const result = await hubspotAPI.connect(tokenInput.trim(), arrPropertyName);
      setStatus({
        connected: result.connected,
        portal_name: result.portal_name,
        hub_id: result.hub_id,
        token_hint: result.token_hint,
        last_synced_at: null,
        last_sync_status: null,
        last_error: null,
        contacts_synced: 0,
        contacts_matched: 0,
        arr_property_name: arrPropertyName,
        connected_at: null,
        writeback_enabled: false,
        writeback_field_name: null,
        last_writeback_at: null,
        last_writeback_status: null,
        last_writeback_error: null,
        contacts_written: 0,
      });
      setTokenInput('');  // clear after successful connect
    } catch (err: any) {
      const msg: string =
        err?.response?.data?.detail ?? 'Failed to connect HubSpot. Check your token and try again.';
      setConnectError(msg);
    } finally {
      setConnecting(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await hubspotAPI.testConnection();
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
      await hubspotAPI.disconnect();
      setStatus(null);
      setTestResult(null);
    } catch (err: any) {
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
            {/* HubSpot brand orange icon */}
            <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-[#FF7A59] text-white text-base font-bold shadow-sm">
              HS
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground">HubSpot CRM</h1>
              <p className="text-muted-foreground text-sm">
                Connect your HubSpot portal to enrich customer profiles with CRM data.
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
              {status?.connected ? 'Connection Details' : 'Connect HubSpot'}
            </CardTitle>
            <CardDescription>
              {status?.connected
                ? 'Your HubSpot portal is connected. You can test or disconnect below.'
                : 'Create a private app in HubSpot and paste the access token below.'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {status?.connected ? (
              /* Connected state */
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  {status.portal_name && (
                    <div>
                      <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                        Portal
                      </p>
                      <p className="font-medium text-foreground">{status.portal_name}</p>
                    </div>
                  )}
                  {status.hub_id && (
                    <div>
                      <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                        Hub ID
                      </p>
                      <p className="font-medium text-foreground font-mono">{status.hub_id}</p>
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
                  {status.arr_property_name && (
                    <div>
                      <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide mb-1">
                        ARR Property
                      </p>
                      <p className="font-mono text-foreground">{status.arr_property_name}</p>
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
                    <Label htmlFor="access-token">Private App Access Token</Label>
                    <div className="relative">
                      <Input
                        id="access-token"
                        type={showToken ? 'text' : 'password'}
                        placeholder="pat-na1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
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
                      Create a private app in your HubSpot account under Settings → Integrations → Private Apps.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="arr-property">ARR Property Name</Label>
                    <Input
                      id="arr-property"
                      type="text"
                      placeholder="annualrevenue"
                      value={arrPropertyName}
                      onChange={(e) => setArrPropertyName(e.target.value)}
                      className="font-mono text-sm"
                    />
                    <p className="text-xs text-muted-foreground">
                      The HubSpot company property used for Annual Recurring Revenue.
                      Defaults to <code className="font-mono">annualrevenue</code>.
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
                      'Connect HubSpot'
                    )}
                  </Button>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Contact an admin to connect HubSpot CRM.
                </p>
              )
            )}
          </CardContent>
        </Card>

        {/* Health-score writeback (connected state only) */}
        {status?.connected && isAdminOrOwner && (
          <HubSpotWritebackCard status={status} onStatusChange={setStatus} />
        )}

        {/* Help card */}
        <Card className="animate-slide-up stagger-1">
          <CardHeader>
            <CardTitle className="text-base">How to get your access token</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="text-sm text-muted-foreground space-y-1 list-decimal list-inside">
              <li>Go to <strong>HubSpot</strong> → Settings → Integrations → Private Apps</li>
              <li>Click <strong>Create a private app</strong></li>
              <li>Name the app and grant <strong>CRM</strong> read scopes (contacts, companies, deals)</li>
              <li>Click <strong>Create app</strong> and copy the access token</li>
              <li>Paste it above and click <strong>Connect HubSpot</strong></li>
            </ol>
          </CardContent>
        </Card>
      </main>

      {/* Disconnect confirm dialog */}
      <Dialog open={confirmDisconnect} onOpenChange={(open) => { if (!open) setConfirmDisconnect(false); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Disconnect HubSpot?</DialogTitle>
            <DialogDescription>
              This will remove the HubSpot connection. Existing enrichment data will not be deleted.
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
