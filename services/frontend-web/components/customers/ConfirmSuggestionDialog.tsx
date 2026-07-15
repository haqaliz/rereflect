'use client';

import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { ReasonCodeSelect } from '@/components/customers/ReasonCodeSelect';
import { confirmChurnSuggestion } from '@/lib/api/churn-suggestions';
import type { ChurnReasonCode } from '@/lib/api/churn-events';

interface ConfirmSuggestionSummary {
  id: number;
  customer_email: string;
  provider: string;
  suggested_churned_at: string;
  evidence: Record<string, unknown> | null;
}

interface ConfirmSuggestionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  suggestion: ConfirmSuggestionSummary;
  onSuccess?: () => void;
}

function formatCloseDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

export function ConfirmSuggestionDialog({
  open,
  onOpenChange,
  suggestion,
  onSuccess,
}: ConfirmSuggestionDialogProps) {
  const [reasonCode, setReasonCode] = useState<ChurnReasonCode | ''>('');
  const [reasonText, setReasonText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!reasonCode) return;
    setSubmitting(true);
    try {
      const result = await confirmChurnSuggestion(suggestion.id, {
        reason_code: reasonCode,
        reason_text: reasonText.trim() || undefined,
      });
      if (result.status === 'skipped') {
        toast.success('Already marked as churned — suggestion resolved.');
      } else {
        toast.success('Customer marked as churned.');
      }
      onSuccess?.();
      onOpenChange(false);
    } catch {
      toast.error('Failed to confirm this suggestion. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Confirm churn suggestion</DialogTitle>
          <DialogDescription>
            Record a churn event for <strong>{suggestion.customer_email}</strong>.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label>CRM close date</Label>
            {/* Read-only — the CRM close date is stable, which keeps
                re-harvest idempotent (PRD M2). Not an editable date input. */}
            <p className="text-sm text-foreground rounded-md border border-border bg-muted/40 px-3 py-2">
              {formatCloseDate(suggestion.suggested_churned_at)}
            </p>
          </div>

          <ReasonCodeSelect
            value={reasonCode}
            onChange={setReasonCode}
            id="confirm-reason-code"
            label="Reason"
          />

          <div className="space-y-1.5">
            <Label htmlFor="confirm-reason-text">Note (optional)</Label>
            <Textarea
              id="confirm-reason-text"
              placeholder="Optional note about why this customer churned..."
              value={reasonText}
              onChange={(e) => setReasonText(e.target.value)}
              rows={3}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting || !reasonCode}>
            {submitting && <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />}
            Confirm
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
