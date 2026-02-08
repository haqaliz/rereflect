'use client';

import { useState, useEffect, useCallback } from 'react';
import { sharedLinksAPI, type SharedLink } from '@/lib/api/analytics';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Share2, Copy, Check, Eye, Trash2, Link as LinkIcon } from 'lucide-react';

interface ShareAnalyticsDialogProps {
  disabled?: boolean;
  disabledReason?: string;
}

export function ShareAnalyticsDialog({ disabled, disabledReason }: ShareAnalyticsDialogProps) {
  const [open, setOpen] = useState(false);
  const [links, setLinks] = useState<SharedLink[]>([]);
  const [creating, setCreating] = useState(false);
  const [expiration, setExpiration] = useState('7d');
  const [password, setPassword] = useState('');
  const [newLink, setNewLink] = useState<SharedLink | null>(null);
  const [copied, setCopied] = useState(false);

  const fetchLinks = useCallback(async () => {
    try {
      const data = await sharedLinksAPI.list();
      setLinks(data);
    } catch {
      // silently fail
    }
  }, []);

  useEffect(() => {
    if (open) {
      fetchLinks();
      setNewLink(null);
      setPassword('');
      setExpiration('7d');
    }
  }, [open, fetchLinks]);

  const handleCreate = async () => {
    setCreating(true);
    try {
      const link = await sharedLinksAPI.create({
        expiration,
        password: password || undefined,
      });
      setNewLink(link);
      fetchLinks();
    } catch {
      // handle error
    } finally {
      setCreating(false);
    }
  };

  const handleDeactivate = async (id: number) => {
    try {
      await sharedLinksAPI.deactivate(id);
      fetchLinks();
    } catch {
      // handle error
    }
  };

  const getShareUrl = (token: string) => {
    if (typeof window !== 'undefined') {
      return `${window.location.origin}/shared/${token}`;
    }
    return `/shared/${token}`;
  };

  const handleCopy = async (token: string) => {
    await navigator.clipboard.writeText(getShareUrl(token));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formatExpiry = (expiresAt: string | null) => {
    if (!expiresAt) return 'Never';
    const date = new Date(expiresAt);
    const now = new Date();
    if (date < now) return 'Expired';
    return date.toLocaleDateString();
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled}
          title={disabledReason || 'Share analytics dashboard'}
        >
          <Share2 className="w-4 h-4 mr-1.5" />
          Share
          {disabled && (
            <span className="ml-1 text-xs opacity-50">(Pro)</span>
          )}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>Share Analytics</DialogTitle>
        </DialogHeader>

        <div className="space-y-5">
          {/* Create new link */}
          {!newLink ? (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label className="text-sm">Link expiration</Label>
                <Select value={expiration} onValueChange={setExpiration}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="24h">24 hours</SelectItem>
                    <SelectItem value="7d">7 days</SelectItem>
                    <SelectItem value="30d">30 days</SelectItem>
                    <SelectItem value="never">Never expires</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-sm">Password (optional)</Label>
                <Input
                  type="password"
                  placeholder="Leave empty for no password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>

              <Button onClick={handleCreate} disabled={creating} className="w-full">
                <LinkIcon className="w-4 h-4 mr-1.5" />
                {creating ? 'Creating...' : 'Create Link'}
              </Button>
            </div>
          ) : (
            /* Show newly created link */
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Your link is ready. Anyone with this link can view your analytics dashboard.
              </p>
              <div className="flex items-center gap-2">
                <Input
                  readOnly
                  value={getShareUrl(newLink.token)}
                  className="text-xs font-mono"
                />
                <Button
                  variant="outline"
                  size="sm"
                  className="shrink-0"
                  onClick={() => handleCopy(newLink.token)}
                >
                  {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                </Button>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="w-full"
                onClick={() => setNewLink(null)}
              >
                Create another link
              </Button>
            </div>
          )}

          {/* Existing links */}
          {links.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Active Links
              </h4>
              <div className="space-y-2 max-h-[200px] overflow-y-auto">
                {links.map((link) => (
                  <div
                    key={link.id}
                    className="flex items-center justify-between py-2 px-3 rounded-md border text-sm"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="font-mono text-xs truncate max-w-[140px]">
                        ...{link.token.slice(-8)}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {formatExpiry(link.expires_at)}
                      </span>
                      {link.has_password && (
                        <span className="text-xs text-muted-foreground">Protected</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-xs text-muted-foreground flex items-center gap-1">
                        <Eye className="w-3 h-3" /> {link.view_count}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0"
                        onClick={() => handleCopy(link.token)}
                      >
                        <Copy className="w-3 h-3" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0 text-destructive hover:text-destructive"
                        onClick={() => handleDeactivate(link.id)}
                      >
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
