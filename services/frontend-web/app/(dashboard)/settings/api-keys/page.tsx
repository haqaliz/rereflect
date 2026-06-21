'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  apiKeysAPI,
  type ApiKeyListItem,
  type ApiKeyCreateResponse,
  type ApiKeyScope,
} from '@/lib/api/api-keys';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Key,
  Plus,
  Copy,
  Check,
  Trash2,
  Loader2,
  ExternalLink,
  Eye,
  EyeOff,
} from 'lucide-react';
import { toast } from 'sonner';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso: string | null): string {
  if (!iso) return 'Never';
  return new Date(iso).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function ScopeBadge({ scope }: { scope: string }) {
  const styles: Record<string, string> = {
    read: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    ingest: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${styles[scope] ?? 'bg-gray-100 text-gray-800'}`}
    >
      {scope}
    </span>
  );
}

function ScopeList({ scopes }: { scopes: string }) {
  return (
    <div className="flex flex-wrap gap-1">
      {scopes.split(',').map(s => s.trim()).filter(Boolean).map(s => (
        <ScopeBadge key={s} scope={s} />
      ))}
    </div>
  );
}

// ─── Create key dialog ────────────────────────────────────────────────────────

interface CreateDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: (key: ApiKeyCreateResponse) => void;
}

function CreateKeyDialog({ open, onClose, onCreated }: CreateDialogProps) {
  const [name, setName] = useState('');
  const [scopes, setScopes] = useState<Set<ApiKeyScope>>(new Set(['read']));
  const [submitting, setSubmitting] = useState(false);

  const toggleScope = (scope: ApiKeyScope) => {
    setScopes(prev => {
      const next = new Set(prev);
      if (next.has(scope)) {
        next.delete(scope);
      } else {
        next.add(scope);
      }
      return next;
    });
  };

  const handleSubmit = async () => {
    if (!name.trim()) {
      toast.error('Key name is required');
      return;
    }
    if (scopes.size === 0) {
      toast.error('Select at least one scope');
      return;
    }
    setSubmitting(true);
    try {
      const result = await apiKeysAPI.create({
        name: name.trim(),
        scopes: Array.from(scopes),
      });
      onCreated(result);
      setName('');
      setScopes(new Set(['read']));
    } catch {
      toast.error('Failed to create API key');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Create API Key</DialogTitle>
          <DialogDescription>
            Give the key a descriptive name and choose the access scopes. The full
            key will be shown exactly once — copy it immediately.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="key-name">Name</Label>
            <Input
              id="key-name"
              placeholder="e.g. CI pipeline, Zapier integration"
              value={name}
              onChange={e => setName(e.target.value)}
              disabled={submitting}
            />
          </div>

          <div className="space-y-2">
            <Label>Scopes</Label>
            {(['read', 'ingest'] as const).map(scope => (
              <div key={scope} className="flex items-start gap-2">
                <Checkbox
                  id={`scope-${scope}`}
                  checked={scopes.has(scope)}
                  onCheckedChange={() => toggleScope(scope)}
                  disabled={submitting}
                />
                <div className="grid gap-0.5 leading-none">
                  <label
                    htmlFor={`scope-${scope}`}
                    className="text-sm font-medium leading-none cursor-pointer"
                  >
                    {scope}
                  </label>
                  <p className="text-xs text-muted-foreground">
                    {scope === 'read'
                      ? 'Read feedback, customers, and analytics via the public API'
                      : 'Submit new feedback and enqueue it for AI analysis'}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Create Key
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Key reveal dialog (shown once after creation) ────────────────────────────

interface RevealDialogProps {
  apiKey: ApiKeyCreateResponse | null;
  onClose: () => void;
}

function RevealDialog({ apiKey, onClose }: RevealDialogProps) {
  const [copied, setCopied] = useState(false);
  const [visible, setVisible] = useState(false);

  const handleCopy = async () => {
    if (!apiKey) return;
    await navigator.clipboard.writeText(apiKey.key);
    setCopied(true);
    toast.success('Key copied to clipboard');
    setTimeout(() => setCopied(false), 2000);
  };

  if (!apiKey) return null;

  return (
    <Dialog open={!!apiKey} onOpenChange={v => !v && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>API Key Created</DialogTitle>
          <DialogDescription className="text-amber-600 dark:text-amber-400 font-medium">
            This is the only time the full key will be shown. Copy it now and store it
            securely — it cannot be recovered.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <div className="p-3 bg-muted rounded-lg font-mono text-sm break-all relative">
            <span className="select-all">
              {visible ? apiKey.key : `${apiKey.key_prefix}${'*'.repeat(32)}`}
            </span>
          </div>

          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setVisible(v => !v)}
              className="flex items-center gap-1"
            >
              {visible ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              {visible ? 'Hide' : 'Show'}
            </Button>
            <Button
              size="sm"
              onClick={handleCopy}
              className="flex items-center gap-1"
            >
              {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              {copied ? 'Copied!' : 'Copy Key'}
            </Button>
          </div>

          <div className="text-xs text-muted-foreground space-y-1">
            <p>Scopes: <ScopeList scopes={apiKey.scopes} /></p>
            <p>
              Public API docs:{' '}
              <a
                href="/api/public/v1/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="underline underline-offset-2 hover:text-foreground inline-flex items-center gap-1"
              >
                /api/public/v1/docs <ExternalLink className="w-3 h-3" />
              </a>
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button onClick={onClose}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ApiKeysPage() {
  const { user } = useAuth();
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [keys, setKeys] = useState<ApiKeyListItem[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newKey, setNewKey] = useState<ApiKeyCreateResponse | null>(null);
  const [revokingId, setRevokingId] = useState<number | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<ApiKeyListItem | null>(null);

  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';

  useEffect(() => {
    if (user && !isAdminOrOwner) {
      router.replace('/settings/preferences');
    }
  }, [user, isAdminOrOwner, router]);

  useEffect(() => {
    if (!isAdminOrOwner) return;
    async function load() {
      try {
        const data = await apiKeysAPI.list();
        setKeys(data);
      } catch {
        toast.error('Failed to load API keys');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [isAdminOrOwner]);

  const handleCreated = useCallback((key: ApiKeyCreateResponse) => {
    setShowCreate(false);
    setNewKey(key);
    // Add the key to the list (without the raw key field)
    setKeys(prev => [key as unknown as ApiKeyListItem, ...prev]);
  }, []);

  const handleRevoke = useCallback(async (key: ApiKeyListItem) => {
    setRevokingId(key.id);
    try {
      await apiKeysAPI.revoke(key.id);
      setKeys(prev =>
        prev.map(k =>
          k.id === key.id ? { ...k, revoked_at: new Date().toISOString() } : k
        )
      );
      toast.success(`Key "${key.name}" revoked`);
    } catch {
      toast.error('Failed to revoke key');
    } finally {
      setRevokingId(null);
      setConfirmRevoke(null);
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
          <p className="text-muted-foreground font-medium">Loading API keys...</p>
        </div>
      </div>
    );
  }

  const activeKeys = keys.filter(k => !k.revoked_at);
  const revokedKeys = keys.filter(k => k.revoked_at);

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">

        {/* Header */}
        <div className="animate-fade-in">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center space-x-3">
              <div className="p-3 bg-secondary rounded-xl">
                <Key className="w-8 h-8 text-primary" />
              </div>
              <div>
                <h1 className="text-4xl font-bold text-foreground">API Keys</h1>
                <p className="text-muted-foreground text-lg">
                  Authenticate programmatic access to the Rereflect public API
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <a
                href="/api/public/v1/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-muted-foreground hover:text-foreground underline underline-offset-2 inline-flex items-center gap-1"
              >
                API Docs <ExternalLink className="w-3 h-3" />
              </a>
              <Button
                onClick={() => setShowCreate(true)}
                className="flex items-center gap-2"
              >
                <Plus className="w-4 h-4" />
                New Key
              </Button>
            </div>
          </div>
        </div>

        {/* Active keys */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Active Keys
              {activeKeys.length > 0 && (
                <Badge variant="secondary" className="ml-2">
                  {activeKeys.length}
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {activeKeys.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">
                No active keys. Create one to get started.
              </p>
            ) : (
              <div className="divide-y divide-border">
                {activeKeys.map(key => (
                  <div key={key.id} className="py-3 flex items-center gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm truncate">{key.name}</span>
                        <Badge variant="outline" className="font-mono text-xs shrink-0">
                          {key.key_prefix}…
                        </Badge>
                      </div>
                      <div className="flex items-center gap-3 mt-1">
                        <ScopeList scopes={key.scopes} />
                        <span className="text-xs text-muted-foreground">
                          Last used: {formatDate(key.last_used_at)}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          Created: {formatDate(key.created_at)}
                        </span>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setConfirmRevoke(key)}
                      disabled={revokingId === key.id}
                      className="text-destructive hover:text-destructive hover:bg-destructive/10 shrink-0"
                    >
                      {revokingId === key.id ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Trash2 className="w-4 h-4" />
                      )}
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Revoked keys (collapsed by default) */}
        {revokedKeys.length > 0 && (
          <Card className="opacity-70">
            <CardHeader>
              <CardTitle className="text-base text-muted-foreground">
                Revoked Keys
                <Badge variant="outline" className="ml-2">
                  {revokedKeys.length}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="divide-y divide-border">
                {revokedKeys.map(key => (
                  <div key={key.id} className="py-3 flex items-center gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm text-muted-foreground line-through truncate">
                          {key.name}
                        </span>
                        <Badge variant="outline" className="font-mono text-xs shrink-0 text-muted-foreground">
                          {key.key_prefix}…
                        </Badge>
                      </div>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="text-xs text-muted-foreground">
                          Revoked: {formatDate(key.revoked_at)}
                        </span>
                      </div>
                    </div>
                    <Badge variant="destructive" className="shrink-0 text-xs">Revoked</Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Usage notes */}
        <Card className="bg-muted/40">
          <CardContent className="pt-4 pb-4">
            <h3 className="text-sm font-semibold mb-2">How to use your API key</h3>
            <div className="space-y-1.5 text-xs text-muted-foreground">
              <p>Include the key in every request:</p>
              <pre className="bg-background border rounded p-2 font-mono text-xs overflow-auto">
                {`# Authorization header (recommended)\ncurl -H "Authorization: Bearer rrf_..." /api/public/v1/feedback\n\n# X-API-Key header\ncurl -H "X-API-Key: rrf_..." /api/public/v1/feedback`}
              </pre>
              <p className="pt-1">
                Full interactive docs:{' '}
                <a
                  href="/api/public/v1/docs"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline underline-offset-2 hover:text-foreground"
                >
                  /api/public/v1/docs
                </a>
              </p>
            </div>
          </CardContent>
        </Card>
      </main>

      {/* Dialogs */}
      <CreateKeyDialog
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={handleCreated}
      />

      <RevealDialog
        apiKey={newKey}
        onClose={() => setNewKey(null)}
      />

      {/* Revoke confirm dialog */}
      <Dialog
        open={!!confirmRevoke}
        onOpenChange={v => !v && setConfirmRevoke(null)}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Revoke API Key</DialogTitle>
            <DialogDescription>
              Revoke &quot;{confirmRevoke?.name}&quot;? Any application using this key will
              immediately lose access. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmRevoke(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => confirmRevoke && handleRevoke(confirmRevoke)}
              disabled={revokingId !== null}
            >
              {revokingId !== null && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Revoke Key
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
