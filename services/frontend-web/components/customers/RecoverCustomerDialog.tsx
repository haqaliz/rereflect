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
import { recoverCustomer } from '@/lib/api/churn-events';
import type { ChurnEvent } from '@/lib/api/churn-events';

interface RecoverCustomerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customerEmail: string;
  onSuccess?: (event: ChurnEvent) => void;
}

function getTodayDateString(): string {
  return new Date().toISOString().split('T')[0];
}

export function RecoverCustomerDialog({
  open,
  onOpenChange,
  customerEmail,
  onSuccess,
}: RecoverCustomerDialogProps) {
  const [recoveredAt, setRecoveredAt] = useState(getTodayDateString);
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const event = await recoverCustomer(customerEmail, {
        recovered_at: recoveredAt,
        note: note.trim() || undefined,
      });
      toast.success('Customer marked as recovered.');
      onSuccess?.(event);
      onOpenChange(false);
    } catch {
      toast.error('Failed to recover customer. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Confirm Recovery</DialogTitle>
          <DialogDescription>
            Mark <strong>{customerEmail}</strong> as recovered from churn.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="recovered-at">Recovery Date</Label>
            <Input
              id="recovered-at"
              type="date"
              value={recoveredAt}
              onChange={(e) => setRecoveredAt(e.target.value)}
              aria-label="Recovery date"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="recovery-note">Note (optional)</Label>
            <Textarea
              id="recovery-note"
              placeholder="Optional note about this recovery..."
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting && <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />}
            Confirm recovery
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
