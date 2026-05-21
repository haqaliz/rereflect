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
import { Input } from '@/components/ui/input';
import { ReasonCodeSelect } from '@/components/customers/ReasonCodeSelect';
import { markCustomerChurned } from '@/lib/api/churn-events';
import type { ChurnReasonCode, ChurnEvent } from '@/lib/api/churn-events';

interface MarkAsChurnedDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customerEmail: string;
  onSuccess?: (event: ChurnEvent) => void;
}

function getTodayDateString(): string {
  return new Date().toISOString().split('T')[0];
}

export function MarkAsChurnedDialog({
  open,
  onOpenChange,
  customerEmail,
  onSuccess,
}: MarkAsChurnedDialogProps) {
  const [reasonCode, setReasonCode] = useState<ChurnReasonCode | ''>('');
  const [reasonText, setReasonText] = useState('');
  const [churnedAt, setChurnedAt] = useState(getTodayDateString);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!reasonCode) return;
    setSubmitting(true);
    try {
      const event = await markCustomerChurned(customerEmail, {
        churned_at: churnedAt,
        reason_code: reasonCode,
        reason_text: reasonText.trim() || undefined,
      });
      toast.success('Customer marked as churned.');
      onSuccess?.(event);
      onOpenChange(false);
    } catch {
      toast.error('Failed to mark customer as churned. Please try again.');
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
            Record a churn event for <strong>{customerEmail}</strong>.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="churned-at">Churned Date</Label>
            <Input
              id="churned-at"
              type="date"
              value={churnedAt}
              onChange={(e) => setChurnedAt(e.target.value)}
              aria-label="Churned date"
            />
          </div>

          <ReasonCodeSelect
            value={reasonCode}
            onChange={setReasonCode}
            id="reason-code"
            label="Reason"
          />

          <div className="space-y-1.5">
            <Label htmlFor="reason-text">Note (optional)</Label>
            <Textarea
              id="reason-text"
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
          <Button
            onClick={handleSubmit}
            disabled={submitting || !reasonCode}
          >
            {submitting && <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />}
            Mark as churned
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
