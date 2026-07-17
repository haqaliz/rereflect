'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  getOidcConfig,
  putOidcConfig,
  deleteOidcConfig,
  type OidcConfigUpdate,
} from '@/lib/api/oidc';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  ShieldCheck,
  Loader2,
  Trash2,
  X,
  AlertCircle,
  AlertTriangle,
  CheckCircle,
} from 'lucide-react';

const DEFAULT_BUTTON_LABEL = 'Sign in with SSO';

export default function SsoSettingsPage() {
  const router = useRouter();
  const { user } = useAuth();

  const [loading, setLoading] = useState(true);

  // Form state
  const [configured, setConfigured] = useState(false);
  const [issuerUrl, setIssuerUrl] = useState('');
  const [clientId, setClientId] = useState('');
  const [clientSecretInput, setClientSecretInput] = useState('');
  const [secretHint, setSecretHint] = useState<string | null>(null);
  const [buttonLabel, setButtonLabel] = useState(DEFAULT_BUTTON_LABEL);
  const [enabled, setEnabled] = useState(false);
  const [domains, setDomains] = useState<string[]>([]);
  const [newDomainInput, setNewDomainInput] = useState('');

  // Save state
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Delete state
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';

  // Redirect non-admin/owner to preferences
  useEffect(() => {
    if (user && !isAdminOrOwner) {
      router.replace('/settings/preferences');
    }
  }, [user, isAdminOrOwner, router]);

  const applyConfig = (data: {
    configured: boolean;
    issuer_url: string | null;
    client_id: string | null;
    secret_hint: string | null;
    enabled: boolean;
    allowed_email_domains: string[];
    button_label: string | null;
  }) => {
    setConfigured(data.configured);
    setIssuerUrl(data.issuer_url ?? '');
    setClientId(data.client_id ?? '');
    setSecretHint(data.secret_hint ?? null);
    setEnabled(data.enabled);
    setDomains(data.allowed_email_domains ?? []);
    setButtonLabel(data.button_label ?? DEFAULT_BUTTON_LABEL);
    setClientSecretInput('');
  };

  useEffect(() => {
    if (!isAdminOrOwner) return;
    let cancelled = false;
    async function load() {
      try {
        const data = await getOidcConfig();
        if (!cancelled) applyConfig(data);
      } catch {
        // Fall back to an empty, unconfigured form.
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [isAdminOrOwner]);

  const handleAddDomain = useCallback(() => {
    const d = newDomainInput.trim().toLowerCase();
    if (!d) return;
    setDomains(prev => (prev.includes(d) ? prev : [...prev, d]));
    setNewDomainInput('');
  }, [newDomainInput]);

  const handleRemoveDomain = useCallback((d: string) => {
    setDomains(prev => prev.filter(x => x !== d));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(false);
    try {
      const payload: OidcConfigUpdate = {
        issuer_url: issuerUrl.trim(),
        client_id: clientId.trim(),
        enabled,
        allowed_email_domains: domains,
        button_label: buttonLabel.trim() || undefined,
      };
      if (clientSecretInput.trim()) {
        payload.client_secret = clientSecretInput.trim();
      }
      const result = await putOidcConfig(payload);
      applyConfig(result);
      setSaveSuccess(true);
    } catch (err: any) {
      setSaveError(
        err?.response?.data?.detail ?? 'Failed to save SSO configuration. Please try again.'
      );
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteOidcConfig();
      applyConfig({
        configured: false,
        issuer_url: null,
        client_id: null,
        secret_hint: null,
        enabled: false,
        allowed_email_domains: [],
        button_label: null,
      });
      setSaveSuccess(false);
    } catch (err: any) {
      if (err?.response?.status === 404) {
        setDeleteError('Nothing to remove — no SSO configuration is currently set up.');
      } else {
        setDeleteError(
          err?.response?.data?.detail ?? 'Failed to remove the SSO configuration. Please try again.'
        );
      }
    } finally {
      setDeleting(false);
      setDeleteConfirmOpen(false);
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

  const showEmptyAllowlistWarning = enabled && domains.length === 0;

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Header */}
        <div className="animate-fade-in">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-secondary rounded-xl">
              <ShieldCheck className="w-8 h-8 text-primary" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground">Single Sign-On (SSO)</h1>
              <p className="text-muted-foreground text-sm">
                Configure an OpenID Connect identity provider so your team can sign in with SSO.
              </p>
            </div>
            {configured && (
              <Badge
                variant="outline"
                className={
                  enabled
                    ? 'ml-auto text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950'
                    : 'ml-auto text-muted-foreground'
                }
              >
                {enabled ? 'Enabled' : 'Configured'}
              </Badge>
            )}
          </div>
        </div>

        <Card className="animate-slide-up">
          <CardHeader>
            <CardTitle>Identity Provider</CardTitle>
            <CardDescription>
              Enter your IdP&apos;s OpenID Connect details. The client secret is never shown again after saving.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="issuer-url">Issuer URL</Label>
              <Input
                id="issuer-url"
                type="text"
                placeholder="https://idp.example.com"
                value={issuerUrl}
                onChange={(e) => setIssuerUrl(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="client-id">Client ID</Label>
              <Input
                id="client-id"
                type="text"
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="client-secret">Client Secret</Label>
              <Input
                id="client-secret"
                type="password"
                placeholder={configured && secretHint ? `•••• ${secretHint}` : 'Enter client secret'}
                value={clientSecretInput}
                onChange={(e) => setClientSecretInput(e.target.value)}
                autoComplete="off"
              />
              {configured && (
                <p className="text-xs text-muted-foreground">
                  A secret is already stored ({secretHint}). Leave blank to keep it unchanged.
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="button-label">Button Label</Label>
              <Input
                id="button-label"
                type="text"
                value={buttonLabel}
                onChange={(e) => setButtonLabel(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="new-domain">Allowed Email Domains</Label>
              {domains.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {domains.map((d) => (
                    <Badge key={d} variant="secondary" className="flex items-center gap-1">
                      {d}
                      <button
                        type="button"
                        aria-label={`Remove ${d}`}
                        onClick={() => handleRemoveDomain(d)}
                        className="ml-1 hover:text-destructive"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              )}
              <div className="flex gap-2">
                <Input
                  id="new-domain"
                  type="text"
                  placeholder="example.com"
                  value={newDomainInput}
                  onChange={(e) => setNewDomainInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleAddDomain();
                    }
                  }}
                />
                <Button type="button" variant="outline" onClick={handleAddDomain}>
                  Add
                </Button>
              </div>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-border p-3">
              <div>
                <Label htmlFor="enabled-toggle">Enable SSO</Label>
                <p className="text-xs text-muted-foreground">
                  When enabled, the SSO button appears on the login page.
                </p>
              </div>
              <Switch id="enabled-toggle" checked={enabled} onCheckedChange={setEnabled} />
            </div>

            {showEmptyAllowlistWarning && (
              <Alert>
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>
                  Empty allowlist = deny-all: no one can sign in via SSO.
                </AlertDescription>
              </Alert>
            )}

            {saveError && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{saveError}</AlertDescription>
              </Alert>
            )}

            {saveSuccess && (
              <Alert>
                <CheckCircle className="h-4 w-4" />
                <AlertDescription>SSO configuration saved.</AlertDescription>
              </Alert>
            )}

            {deleteError && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{deleteError}</AlertDescription>
              </Alert>
            )}

            <div className="flex items-center gap-3 pt-2">
              <Button onClick={handleSave} disabled={saving}>
                {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                Save
              </Button>
              {configured && (
                <Button
                  variant="outline"
                  className="text-destructive hover:bg-destructive hover:text-destructive-foreground"
                  onClick={() => setDeleteConfirmOpen(true)}
                  disabled={deleting}
                >
                  <Trash2 className="w-4 h-4 mr-2" />
                  Disconnect
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      </main>

      {/* Disconnect confirm dialog */}
      <Dialog open={deleteConfirmOpen} onOpenChange={(open) => { if (!open) setDeleteConfirmOpen(false); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Disconnect SSO?</DialogTitle>
            <DialogDescription>
              This will remove the SSO configuration. Users will no longer be able to sign in via SSO.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Disconnect
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
