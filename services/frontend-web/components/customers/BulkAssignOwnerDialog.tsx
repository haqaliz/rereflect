'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { customersAPI } from '@/lib/api/customers';
import type { Cohort } from '@/lib/api/customers';
import { teamAPI, type TeamMember } from '@/lib/api/team';

const UNASSIGN_VALUE = '__unassign__';

interface BulkAssignOwnerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cohort: Cohort | null;
  /** Size of the resolved cohort — same value shown in the "Bulk Actions (N)" trigger. */
  cohortCount: number;
  onSuccess?: () => void;
}

export function BulkAssignOwnerDialog({
  open,
  onOpenChange,
  cohort,
  cohortCount,
  onSuccess,
}: BulkAssignOwnerDialogProps) {
  const queryClient = useQueryClient();
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [selectedValue, setSelectedValue] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoadingMembers(true);
    teamAPI
      .getTeam()
      .then((res) => setMembers(res.members))
      .catch(() => {
        // silently ignore; picker just stays empty
      })
      .finally(() => setLoadingMembers(false));
  }, [open]);

  const handleSubmit = async () => {
    if (!cohort || !selectedValue) return;
    const userId = selectedValue === UNASSIGN_VALUE ? null : Number(selectedValue);
    setSubmitting(true);
    try {
      const result = await customersAPI.bulkAssignOwner(cohort, userId);
      const verb = userId === null ? 'unassigned' : 'reassigned';
      toast.success(
        `${result.updated} customer${result.updated === 1 ? '' : 's'} ${verb}${
          result.skipped > 0 ? `, ${result.skipped} skipped` : ''
        }.`
      );
      queryClient.invalidateQueries({ queryKey: ['customers'] });
      onSuccess?.();
      onOpenChange(false);
      setSelectedValue('');
    } catch {
      toast.error('Failed to assign owner. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setSelectedValue('');
        onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Assign CS Owner</DialogTitle>
          <DialogDescription>
            Set (or clear) the CS owner across <strong>{cohortCount} customers</strong>.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="bulk-assign-owner">Owner</Label>
            <Select value={selectedValue} onValueChange={setSelectedValue}>
              <SelectTrigger id="bulk-assign-owner">
                <SelectValue
                  placeholder={loadingMembers ? 'Loading team members...' : 'Select an owner'}
                />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={UNASSIGN_VALUE}>Unassign</SelectItem>
                {members.map((m) => (
                  <SelectItem key={m.id} value={String(m.id)}>
                    {m.email}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting || !selectedValue || !cohort}>
            {submitting && <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />}
            {selectedValue === UNASSIGN_VALUE ? 'Unassign' : 'Assign owner'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
