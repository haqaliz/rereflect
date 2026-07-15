'use client';

import { useCallback, useMemo, useState } from 'react';
import Link from 'next/link';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, ChevronDown, Inbox, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/contexts/AuthContext';
import {
  listChurnSuggestions,
  rejectChurnSuggestion,
  type ChurnSuggestion,
} from '@/lib/api/churn-suggestions';
import { ConfirmSuggestionDialog } from '@/components/customers/ConfirmSuggestionDialog';
import { BulkReviewSuggestionsDialog } from '@/components/customers/BulkReviewSuggestionsDialog';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

function EvidenceCell({ evidence }: { evidence: ChurnSuggestion['evidence'] }) {
  if (!evidence || Object.keys(evidence).length === 0) {
    return <span className="text-sm text-muted-foreground italic">No CRM detail captured</span>;
  }
  const dealName = (evidence.deal_name as string) ?? (evidence.opportunity_name as string);
  const amount = evidence.amount as number | undefined;
  const stage = (evidence.stage as string) ?? (evidence.type as string);
  return (
    <div className="text-sm">
      {dealName && <p className="font-medium text-foreground">{dealName}</p>}
      <p className="text-xs text-muted-foreground">
        {[
          amount != null ? `$${amount.toLocaleString()}` : null,
          stage ?? null,
        ]
          .filter(Boolean)
          .join(' · ')}
      </p>
    </div>
  );
}

export default function ChurnSuggestionsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';

  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [confirmTarget, setConfirmTarget] = useState<ChurnSuggestion | null>(null);
  const [bulkAction, setBulkAction] = useState<'confirm' | 'reject' | null>(null);
  const [rejectingId, setRejectingId] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['churn-suggestions', 'pending'],
    queryFn: () => listChurnSuggestions({ status: 'pending', page_size: 100 }),
  });

  const items = useMemo(() => data?.items ?? [], [data]);

  const toggleRow = useCallback((id: number, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(
    (checked: boolean) => {
      setSelectedIds(checked ? new Set(items.map((i) => i.id)) : new Set());
    },
    [items]
  );

  const selectedEmails = useMemo(
    () =>
      items
        .filter((i) => selectedIds.has(i.id))
        .map((i) => i.customer_email),
    [items, selectedIds]
  );

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['churn-suggestions'] });
    queryClient.invalidateQueries({ queryKey: ['churn-suggestions-pending-count'] });
    setSelectedIds(new Set());
  }, [queryClient]);

  const handleReject = useCallback(
    async (id: number) => {
      setRejectingId(id);
      try {
        await rejectChurnSuggestion(id, {});
        toast.success('Suggestion rejected.');
        invalidate();
      } catch {
        toast.error('Failed to reject this suggestion. Please try again.');
      } finally {
        setRejectingId(null);
      }
    },
    [invalidate]
  );

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/customers">
          <Button variant="ghost" size="sm" className="flex items-center gap-1.5">
            <ArrowLeft className="w-4 h-4" />
            Back to customers
          </Button>
        </Link>
      </div>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-foreground flex items-center gap-2">
            <Inbox className="w-6 h-6" style={{ color: 'var(--chart-3)' }} />
            CRM churn suggestions
          </h1>
          <p className="text-muted-foreground mt-1">
            Review CRM-sourced closed-lost deals. Confirming writes a real churn label — nothing
            here trains the model until a human confirms it.
          </p>
        </div>

        {isAdminOrOwner && selectedIds.size > 0 && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="flex items-center gap-2">
                Bulk Actions ({selectedIds.size})
                <ChevronDown className="w-3.5 h-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setBulkAction('confirm')}>
                Confirm selected
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setBulkAction('reject')}>
                Reject selected
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>

      <Card className="p-0 overflow-hidden">
        {isLoading ? (
          <div className="p-8 flex justify-center">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : items.length === 0 ? (
          <div className="p-16 flex flex-col items-center justify-center text-center">
            <Inbox className="w-12 h-12 text-muted-foreground opacity-20 mb-3" />
            <p className="text-muted-foreground">No pending CRM churn suggestions.</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/30">
              <tr>
                <th className="w-10 px-4 py-3 text-left">
                  <Checkbox
                    checked={items.length > 0 && selectedIds.size === items.length}
                    onCheckedChange={(v) => toggleAll(!!v)}
                    aria-label="Select all"
                  />
                </th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Customer</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Provider</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Evidence</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                  Close date
                </th>
                <th className="px-4 py-3 text-right font-medium text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((suggestion) => (
                <tr key={suggestion.id} className="border-b border-border last:border-b-0">
                  <td className="px-4 py-3">
                    <Checkbox
                      checked={selectedIds.has(suggestion.id)}
                      onCheckedChange={(v) => toggleRow(suggestion.id, !!v)}
                      aria-label="Select row"
                    />
                  </td>
                  <td className="px-4 py-3 font-medium text-foreground">
                    {suggestion.customer_email}
                  </td>
                  <td className="px-4 py-3">
                    <Badge
                      variant="outline"
                      style={{
                        backgroundColor: 'var(--secondary)',
                        color: 'var(--muted-foreground)',
                      }}
                    >
                      {suggestion.provider}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <EvidenceCell evidence={suggestion.evidence} />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(suggestion.suggested_churned_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right space-x-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleReject(suggestion.id)}
                      disabled={rejectingId === suggestion.id}
                    >
                      Reject
                    </Button>
                    <Button size="sm" onClick={() => setConfirmTarget(suggestion)}>
                      Confirm
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {confirmTarget && (
        <ConfirmSuggestionDialog
          open={!!confirmTarget}
          onOpenChange={(open) => !open && setConfirmTarget(null)}
          suggestion={confirmTarget}
          onSuccess={() => {
            setConfirmTarget(null);
            invalidate();
          }}
        />
      )}

      {bulkAction && (
        <BulkReviewSuggestionsDialog
          open={!!bulkAction}
          onOpenChange={(open) => !open && setBulkAction(null)}
          action={bulkAction}
          cohort={{ emails: selectedEmails }}
          cohortCount={selectedEmails.length}
          onSuccess={() => {
            setBulkAction(null);
            invalidate();
          }}
        />
      )}
    </div>
  );
}
