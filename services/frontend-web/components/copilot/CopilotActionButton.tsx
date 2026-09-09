'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { Check, Loader2, Tag } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useAuth } from '@/contexts/AuthContext';
import { executeCopilotAction, type BulkActionSummary } from '@/lib/api/copilot-actions';

interface CopilotActionButtonProps {
  /** Persisted conversation id the proposal lives in — the execute route
   *  resolves the proposal by conversation_id + proposal_id. Never the WS
   *  turn message id. Absent (e.g. MessageBubble standalone) → button
   *  disabled: there is no conversation to execute against. */
  conversationId?: number;
  proposalId: string;
  action: string;
  label: string;
  onExecuted?: () => void;
}

export function CopilotActionButton({
  conversationId,
  proposalId,
  action,
  label,
  onExecuted,
}: CopilotActionButtonProps) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [tag, setTag] = useState('');
  const [inFlight, setInFlight] = useState(false);
  const [result, setResult] = useState<BulkActionSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [executed, setExecuted] = useState(false);

  // Cosmetic only — the server enforces min_role at execute time.
  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';
  if (!isAdminOrOwner) return null;

  const handleOpen = () => {
    if (executed || inFlight || conversationId == null) return;
    setError(null);
    setOpen(true);
  };

  const handleConfirm = async () => {
    const trimmed = tag.trim();
    // Client-side guard: an empty tag would 422 server-side. No network call.
    if (!trimmed || inFlight || conversationId == null) return;
    setInFlight(true);
    setError(null);
    setResult(null);
    try {
      const res = await executeCopilotAction(conversationId, proposalId, action, { tag: trimmed });
      setResult(res);
      setExecuted(true);
      setOpen(false);
      toast.success(`Tag applied — ${res.updated} updated, ${res.skipped} skipped`);
      onExecuted?.();
    } catch (e) {
      const status = (e as { response?: { status?: number } })?.response?.status;
      const message =
        status === 403
          ? 'This action requires an admin or owner role.'
          : 'Failed to apply the tag. Please try again.';
      setError(message);
      setOpen(false);
      toast.error(message);
    } finally {
      setInFlight(false);
    }
  };

  return (
    <div className="flex flex-col items-start gap-1.5">
      <Button
        type="button"
        variant="outline"
        size="sm"
        data-testid={`copilot-action-${action}`}
        onClick={handleOpen}
        disabled={executed || inFlight || conversationId == null}
        className="flex items-center gap-1.5"
      >
        {executed ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Tag className="w-3.5 h-3.5" />}
        {label}
      </Button>

      {result && (
        <div
          data-testid="copilot-action-outcome"
          className="text-xs text-muted-foreground space-y-1"
        >
          <p>
            {result.matched} matched · {result.updated} updated · {result.skipped} skipped
          </p>
          {result.errors.length > 0 && (
            <ul className="list-disc pl-4 space-y-0.5">
              {result.errors.map((err) => (
                <li key={err}>{err}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {error && (
        <p data-testid="copilot-action-error" role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Apply tag</DialogTitle>
            <DialogDescription>
              Tag the customers this proposal matched. The tag value comes from you — nothing is
              sent until you confirm.
            </DialogDescription>
          </DialogHeader>
          <Input
            aria-label="Tag name"
            placeholder="e.g. vip-customers"
            value={tag}
            onChange={(e) => setTag(e.target.value)}
            disabled={inFlight}
            autoFocus
          />
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setOpen(false)} disabled={inFlight}>
              Cancel
            </Button>
            <Button
              size="sm"
              data-testid="copilot-action-confirm"
              onClick={handleConfirm}
              disabled={inFlight || !tag.trim()}
            >
              {inFlight && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />}
              {inFlight ? 'Applying…' : 'Apply tag'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}