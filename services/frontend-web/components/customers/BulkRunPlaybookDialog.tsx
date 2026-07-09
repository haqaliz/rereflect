'use client';

import { useEffect, useState } from 'react';
import { AlertTriangle, Loader2, PlaySquare } from 'lucide-react';
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
import type { Cohort } from '@/lib/api/customers';
import {
  listPlaybooks,
  runPlaybookBatch,
  cohortToRunBatchFilters,
  formatProbabilityRange,
  type Playbook,
} from '@/lib/api/playbooks';

const RUN_BATCH_MAX_CUSTOMERS = 500;

interface BulkRunPlaybookDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cohort: Cohort | null;
  onSuccess?: () => void;
}

export function BulkRunPlaybookDialog({
  open,
  onOpenChange,
  cohort,
  onSuccess,
}: BulkRunPlaybookDialogProps) {
  const queryClient = useQueryClient();
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [loadingPlaybooks, setLoadingPlaybooks] = useState(false);
  const [selectedId, setSelectedId] = useState<string>('');
  const [matched, setMatched] = useState<number | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [running, setRunning] = useState(false);

  const runBatchFilters = cohort ? cohortToRunBatchFilters(cohort) : null;
  const unsupportedFilter = cohort !== null && runBatchFilters === null;

  useEffect(() => {
    if (!open) return;
    setLoadingPlaybooks(true);
    listPlaybooks()
      .then((all) => setPlaybooks(all.filter((p) => !p.is_template && p.is_active)))
      .catch(() => {
        // silently ignore; picker just stays empty
      })
      .finally(() => setLoadingPlaybooks(false));
  }, [open]);

  // Affected-count preview: re-fetch whenever the selected playbook (or the
  // cohort itself) changes. count_only=true never queues anything and is
  // never subject to the 500 cap or the daily limit — pure preview.
  useEffect(() => {
    if (!open || !selectedId || !runBatchFilters) {
      setMatched(null);
      return;
    }
    let cancelled = false;
    setPreviewLoading(true);
    runPlaybookBatch(Number(selectedId), runBatchFilters, { countOnly: true })
      .then((res) => {
        if (!cancelled) setMatched(res.matched);
      })
      .catch(() => {
        if (!cancelled) setMatched(null);
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, selectedId, JSON.stringify(runBatchFilters)]);

  const reset = () => {
    setSelectedId('');
    setMatched(null);
  };

  const overCap = matched !== null && matched > RUN_BATCH_MAX_CUSTOMERS;

  const handleRun = async () => {
    if (!selectedId || !runBatchFilters || overCap) return;
    setRunning(true);
    try {
      const result = await runPlaybookBatch(Number(selectedId), runBatchFilters);
      toast.success(`Queued ${result.queued} playbook run${result.queued === 1 ? '' : 's'}.`);
      queryClient.invalidateQueries({ queryKey: ['customers'] });
      onSuccess?.();
      onOpenChange(false);
      reset();
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || 'Failed to run playbook. Please try again.');
    } finally {
      setRunning(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Run Playbook</DialogTitle>
          <DialogDescription>
            Queue a playbook run across the customers matching this cohort.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {unsupportedFilter ? (
            <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2">
              <AlertTriangle className="w-4 h-4 text-destructive mt-0.5 shrink-0" />
              <p className="text-sm text-destructive">
                Run playbook only supports a segment- or explicit-selection cohort. Narrow your
                filter to a single segment, or select customers individually.
              </p>
            </div>
          ) : (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="bulk-run-playbook">Playbook</Label>
                <Select value={selectedId} onValueChange={setSelectedId}>
                  <SelectTrigger id="bulk-run-playbook">
                    <SelectValue
                      placeholder={loadingPlaybooks ? 'Loading playbooks...' : 'Select a playbook'}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {playbooks.map((pb) => (
                      <SelectItem key={pb.id} value={String(pb.id)}>
                        {pb.name} ({formatProbabilityRange(pb.probability_min, pb.probability_max)})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {selectedId && (
                <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
                  {previewLoading ? (
                    <span className="flex items-center gap-2 text-muted-foreground">
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      Calculating affected customers...
                    </span>
                  ) : matched !== null ? (
                    <span className={overCap ? 'text-destructive font-medium' : 'text-foreground'}>
                      {matched} customer{matched === 1 ? '' : 's'} will be affected.
                    </span>
                  ) : null}
                </div>
              )}

              {overCap && (
                <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2">
                  <AlertTriangle className="w-4 h-4 text-destructive mt-0.5 shrink-0" />
                  <p className="text-sm text-destructive">
                    Cohort of {matched} exceeds the batch cap of {RUN_BATCH_MAX_CUSTOMERS}. Narrow
                    your filter and try again.
                  </p>
                </div>
              )}
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={running}>
            Cancel
          </Button>
          <Button
            onClick={handleRun}
            disabled={running || !selectedId || unsupportedFilter || overCap || previewLoading}
          >
            {running ? (
              <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />
            ) : (
              <PlaySquare className="w-3.5 h-3.5 mr-2" />
            )}
            Run playbook
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
