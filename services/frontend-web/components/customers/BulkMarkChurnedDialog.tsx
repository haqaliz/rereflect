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
import { Input } from '@/components/ui/input';
import { ReasonCodeSelect } from '@/components/customers/ReasonCodeSelect';
import { bulkMarkChurned } from '@/lib/api/churn-events';
import type { ChurnReasonCode, BulkCreateResult } from '@/lib/api/churn-events';

const PREVIEW_LIMIT = 5;

interface BulkMarkChurnedDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedEmails: string[];
  onSuccess?: (result: BulkCreateResult) => void;
}

function getTodayDateString(): string {
  return new Date().toISOString().split('T')[0];
}

export function BulkMarkChurnedDialog({
  open,
  onOpenChange,
  selectedEmails,
  onSuccess,
}: BulkMarkChurnedDialogProps) {
  const [reasonCode, setReasonCode] = useState<ChurnReasonCode | ''>('');
  const [churnedAt, setChurnedAt] = useState(getTodayDateString);
  const [submitting, setSubmitting] = useState(false);

  const previewEmails = selectedEmails.slice(0, PREVIEW_LIMIT);
  const extraCount = selectedEmails.length - PREVIEW_LIMIT;

  const handleSubmit = async () => {
    if (!reasonCode) return;
    setSubmitting(true);
    try {
      const result = await bulkMarkChurned({
        emails: selectedEmails,
        churned_at: churnedAt,
        reason_code: reasonCode,
      });
      const msg = `${result.created} marked as churned${result.skipped > 0 ? `, ${result.skipped} skipped` : ''}.`;
      toast.success(msg);
      onSuccess?.(result);
      onOpenChange(false);
    } catch {
      toast.error('Failed to bulk mark as churned. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Mark as Churned</DialogTitle>
          <DialogDescription>
            Apply a churn event to <strong>{selectedEmails.length} customers</strong>.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Email summary list */}
          <div className="rounded-md border border-border bg-muted/40 px-3 py-2 space-y-1">
            {previewEmails.map((email) => (
              <p key={email} className="text-sm text-foreground truncate">
                {email}
              </p>
            ))}
            {extraCount > 0 && (
              <p className="text-xs text-muted-foreground">+{extraCount} more</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="bulk-churned-at">Churned Date</Label>
            <Input
              id="bulk-churned-at"
              type="date"
              value={churnedAt}
              onChange={(e) => setChurnedAt(e.target.value)}
              aria-label="Churned date"
            />
          </div>

          <ReasonCodeSelect
            value={reasonCode}
            onChange={setReasonCode}
            id="bulk-reason-code"
            label="Reason"
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting || !reasonCode}>
            {submitting && <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />}
            Mark as churned
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
