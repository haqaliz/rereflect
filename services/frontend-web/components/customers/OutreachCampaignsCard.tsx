'use client';

import { useState } from 'react';
import { RotateCcw, Send } from 'lucide-react';
import { toast } from 'sonner';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { listCampaigns, retryCampaign, type OutreachCampaign } from '@/lib/api/outreach';
import { getRelativeTime } from '@/lib/utils/relative-time';

const STATUS_LABELS: Record<OutreachCampaign['status'], string> = {
  queued: 'Queued',
  in_progress: 'In progress',
  done: 'Done',
  failed: 'Failed',
};

function statusBadgeVariant(status: OutreachCampaign['status']) {
  switch (status) {
    case 'done':
      return 'default';
    case 'failed':
      return 'destructive';
    default:
      return 'outline';
  }
}

export function OutreachCampaignsCard() {
  const queryClient = useQueryClient();
  const [retryingId, setRetryingId] = useState<number | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['outreach-campaigns'],
    queryFn: () => listCampaigns({ page: 1, page_size: 5 }),
    staleTime: 60 * 1000,
  });

  const handleRetry = async (campaign: OutreachCampaign) => {
    if (retryingId !== null) return;
    setRetryingId(campaign.id);
    try {
      const result = await retryCampaign(campaign.id);
      toast.success(
        `Re-queued ${result.queued} email${result.queued === 1 ? '' : 's'} for "${campaign.subject}".`
      );
      queryClient.invalidateQueries({ queryKey: ['outreach-campaigns'] });
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail;
      toast.error(detail || 'Failed to retry the campaign. Please try again.');
    } finally {
      setRetryingId(null);
    }
  };

  return (
    <Card className="p-6 animate-slide-up stagger-4">
      <CardHeader className="px-0 pt-0">
        <CardTitle className="flex items-center gap-2 text-lg">
          <Send className="w-4 h-4 text-primary" />
          Outreach campaigns
        </CardTitle>
      </CardHeader>
      <CardContent className="px-0 pb-0 space-y-2">
        {isLoading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-10 bg-muted rounded animate-pulse" />
            ))}
          </div>
        ) : isError ? (
          <p className="text-sm text-destructive">Failed to load outreach campaigns</p>
        ) : !data || data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No outreach campaigns yet</p>
        ) : (
          data.items.map((campaign) => (
            <div
              key={campaign.id}
              className="flex items-center justify-between gap-3 rounded-md border border-border bg-muted/30 px-3 py-2"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-foreground truncate">
                    {campaign.subject}
                  </p>
                  <Badge variant={statusBadgeVariant(campaign.status)}>
                    {STATUS_LABELS[campaign.status]}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {getRelativeTime(campaign.created_at)} · {campaign.counts.sent} sent ·{' '}
                  {campaign.counts.failed} failed · {campaign.counts.skipped} skipped ·{' '}
                  {campaign.counts.queued} queued
                </p>
              </div>
              {campaign.counts.queued > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleRetry(campaign)}
                  disabled={retryingId !== null}
                  className="shrink-0"
                >
                  <RotateCcw
                    className={`w-3.5 h-3.5 mr-1.5 ${retryingId === campaign.id ? 'animate-spin' : ''}`}
                  />
                  Retry queued
                </Button>
              )}
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}
