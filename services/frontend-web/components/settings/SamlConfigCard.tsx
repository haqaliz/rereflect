'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  getSamlConfig,
  putSamlConfig,
  deleteSamlConfig,
  type SamlConfigUpdate,
} from '@/lib/api/saml';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
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
import { Loader2, Trash2, X, AlertCircle, AlertTriangle, CheckCircle } from 'lucide-react';

const DEFAULT_BUTTON_LABEL = 'Sign in with SSO';

const DEFAULT_CROSS_PROVIDER_MESSAGE =
  'Disable your OIDC provider before enabling SAML — only one single sign-on method can be active at a time.';

// Self-contained sibling to the OIDC card on /settings/sso: its own state,
// load, save, and delete flow so the OIDC card above it is never touched.
// Only mounted/loaded when the parent page has already confirmed the
// current user is admin/owner (see isAdminOrOwner prop).
export function SamlConfigCard({ isAdminOrOwner }: { isAdminOrOwner: boolean }) {
  const [loading, setLoading] = useState(true);

  // Form state
  const [configured, setConfigured] = useState(false);
  const [entityId, setEntityId] = useState('');
  const [ssoUrl, setSsoUrl] = useState('');
  const [certInput, setCertInput] = useState('');
  const [certFingerprint, setCertFingerprint] = useState<string | null>(null);
  const [emailAttribute, setEmailAttribute] = useState('');
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

  const applyConfig = (data: {
    configured: boolean;
    idp_entity_id: string | null;
    idp_sso_url: string | null;
    cert_fingerprint: string | null;
    email_attribute: string | null;
    enabled: boolean;
    allowed_email_domains: string[];
    button_label: string | null;
  }) => {
    setConfigured(data.configured);
    setEntityId(data.idp_entity_id ?? '');
    setSsoUrl(data.idp_sso_url ?? '');
    setCertFingerprint(data.cert_fingerprint ?? null);
    setEmailAttribute(data.email_attribute ?? '');
    setEnabled(data.enabled);
    setDomains(data.allowed_email_domains ?? []);
    setButtonLabel(data.button_label ?? DEFAULT_BUTTON_LABEL);
    setCertInput('');
  };

  useEffect(() => {
    if (!isAdminOrOwner) return;
    let cancelled = false;
    async function load() {
      try {
        const data = await getSamlConfig();
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
      const payload: SamlConfigUpdate = {
        idp_entity_id: entityId.trim(),
        idp_sso_url: ssoUrl.trim(),
        enabled,
        allowed_email_domains: domains,
        email_attribute: emailAttribute.trim() || undefined,
        button_label: buttonLabel.trim() || undefined,
      };
      if (certInput.trim()) {
        payload.idp_x509_cert = certInput.trim();
      }
      const result = await putSamlConfig(payload);
      applyConfig(result);
      setSaveSuccess(true);
    } catch (err: any) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      if (status === 422) {
        setSaveError(detail || DEFAULT_CROSS_PROVIDER_MESSAGE);
      } else {
        setSaveError(detail ?? 'Failed to save SAML configuration. Please try again.');
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteSamlConfig();
      applyConfig({
        configured: false,
        idp_entity_id: null,
        idp_sso_url: null,
        cert_fingerprint: null,
        email_attribute: null,
        enabled: false,
        allowed_email_domains: [],
        button_label: null,
      });
      setSaveSuccess(false);
    } catch (err: any) {
      if (err?.response?.status === 404) {
        setDeleteError('Nothing to remove — no SAML configuration is currently set up.');
      } else {
        setDeleteError(
          err?.response?.data?.detail ?? 'Failed to remove the SAML configuration. Please try again.'
        );
      }
    } finally {
      setDeleting(false);
      setDeleteConfirmOpen(false);
    }
  };

  if (!isAdminOrOwner || loading) {
    return null;
  }

  const showEmptyAllowlistWarning = enabled && domains.length === 0;

  return (
    <div data-testid="saml-config-card">
      <Card className="animate-slide-up">
        <CardHeader>
          <div className="flex items-center gap-2">
            <CardTitle>SAML Identity Provider</CardTitle>
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
          <CardDescription>
            Enter your IdP&apos;s SAML 2.0 details (Entity ID, SSO URL, signing certificate). The
            certificate is public and is never shown again in full after saving — only a fingerprint.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="saml-entity-id">IdP Entity ID</Label>
            <Input
              id="saml-entity-id"
              type="text"
              value={entityId}
              onChange={(e) => setEntityId(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="saml-sso-url">IdP SSO URL</Label>
            <Input
              id="saml-sso-url"
              type="text"
              placeholder="https://idp.example.com/sso"
              value={ssoUrl}
              onChange={(e) => setSsoUrl(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="saml-cert">IdP X.509 Certificate</Label>
            <Textarea
              id="saml-cert"
              placeholder="-----BEGIN CERTIFICATE-----"
              value={certInput}
              onChange={(e) => setCertInput(e.target.value)}
              className="font-mono text-xs min-h-[100px]"
            />
            {configured && certFingerprint && (
              <p className="text-xs text-muted-foreground">
                A certificate is already stored ({certFingerprint}). Leave blank to keep it unchanged.
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="saml-email-attr">Email Attribute (optional)</Label>
            <Input
              id="saml-email-attr"
              type="text"
              value={emailAttribute}
              onChange={(e) => setEmailAttribute(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Leave blank to use the NameID / default mapping.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="saml-button-label">Button Label</Label>
            <Input
              id="saml-button-label"
              type="text"
              value={buttonLabel}
              onChange={(e) => setButtonLabel(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="saml-new-domain">Allowed Email Domains</Label>
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
                id="saml-new-domain"
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
              <Label htmlFor="saml-enabled-toggle">Enable SAML</Label>
              <p className="text-xs text-muted-foreground">
                When enabled, the SSO button appears on the login page.
              </p>
            </div>
            <Switch id="saml-enabled-toggle" checked={enabled} onCheckedChange={setEnabled} />
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
              <AlertDescription>SAML configuration saved.</AlertDescription>
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

      {/* Disconnect confirm dialog */}
      <Dialog open={deleteConfirmOpen} onOpenChange={(open) => { if (!open) setDeleteConfirmOpen(false); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Disconnect SAML?</DialogTitle>
            <DialogDescription>
              This will remove the SAML configuration. Users will no longer be able to sign in via SAML.
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
