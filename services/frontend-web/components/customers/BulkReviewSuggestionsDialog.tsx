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
import { ReasonCodeSelect } from '@/components/customers/ReasonCodeSelect';
import { bulkReviewChurnSuggestions } from '@/lib/api/churn-suggestions';
import type { BulkReviewResult, SuggestionCohort } from '@/lib/api/churn-suggestions';
import type { ChurnReasonCode } from '@/lib/api/churn-events';

interface BulkReviewSuggestionsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  action: 'confirm' | 'reject';
  cohort: SuggestionCohort;
  cohortCount: number;
  onSuccess?: (result: BulkReviewResult) => void;
}

function buildResultToast(result: BulkReviewResult): string {
  let msg = `${result.confirmed} confirmed`;
  if (result.skipped > 0) {
    msg += `, ${result.skipped} skipped (already marked)`;
  }
  msg += '.';
  if (result.capped && result.cap != null) {
    const processed = result.confirmed + result.skipped;
    const notProcessed = result.matched - processed;
    msg += ` ${notProcessed} not processed (cap ${result.cap}).`;
  }
  return msg;
}

export function BulkReviewSuggestionsDialog({
  open,
  onOpenChange,
  action,
  cohort,
  cohortCount,
  onSuccess,
}: BulkReviewSuggestionsDialogProps) {
  const [reasonCode, setReasonCode] = useState<ChurnReasonCode | ''>('');
  const [submitting, setSubmitting] = useState(false);

  const requiresReason = action === 'confirm';
  const canSubmit = !requiresReason || !!reasonCode;

  const handleSubmit = async () => {
    if (requiresReason && !reasonCode) return;
    setSubmitting(true);
    try {
      const result = await bulkReviewChurnSuggestions({
        action,
        cohort,
        ...(requiresReason && reasonCode ? { reason_code: reasonCode } : {}),
      });
      toast.success(buildResultToast(result));
      onSuccess?.(result);
      onOpenChange(false);
    } catch {
      toast.error(`Failed to bulk ${action} suggestions. Please try again.`);
    } finally {
      setSubmitting(false);
    }
  };

  const label = action === 'confirm' ? 'Confirm' : 'Reject';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{label} churn suggestions</DialogTitle>
          <DialogDescription>
            Apply this action to <strong>{cohortCount} suggestions</strong>.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {requiresReason && (
            <ReasonCodeSelect
              value={reasonCode}
              onChange={setReasonCode}
              id="bulk-review-reason-code"
              label="Reason"
            />
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting || !canSubmit}>
            {submitting && <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />}
            {label}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
