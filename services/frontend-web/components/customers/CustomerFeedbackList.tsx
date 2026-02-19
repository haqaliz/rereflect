'use client';

import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { customersAPI, CustomerFeedbackItem } from '@/lib/api/customers';

interface CustomerFeedbackListProps {
  email: string;
}

const sentimentEmoji: Record<string, string> = {
  positive: '😊',
  neutral: '😐',
  negative: '😠',
};

function formatRelativeTime(timestamp: string): string {
  const diffMs = Date.now() - new Date(timestamp).getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);
  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

function formatStatus(status: string | null): string {
  if (!status) return '';
  return status.replace(/_/g, ' ');
}

function FeedbackRow({ item, onClick }: { item: CustomerFeedbackItem; onClick: () => void }) {
  const emoji = sentimentEmoji[item.sentiment_label ?? 'neutral'] ?? '😐';
  return (
    <div
      data-testid="feedback-row"
      className="px-4 py-3 hover:bg-muted/50 cursor-pointer transition-colors border-b border-border last:border-0"
      onClick={onClick}
    >
      <div className="flex items-center gap-2 flex-wrap text-xs text-muted-foreground mb-1">
        <span>
          {emoji} <span className="capitalize">{item.sentiment_label ?? 'unknown'}</span>
        </span>
        {item.churn_risk_score !== null && item.churn_risk_score > 0 && (
          <span className="text-destructive font-medium">Churn: {item.churn_risk_score}</span>
        )}
        {item.workflow_status && (
          <span className="px-1.5 py-0.5 rounded-sm bg-muted text-foreground capitalize">
            {formatStatus(item.workflow_status)}
          </span>
        )}
        <span className="ml-auto">{formatRelativeTime(item.created_at)}</span>
      </div>
      <p className="text-sm text-foreground line-clamp-2">{item.text_snippet}</p>
    </div>
  );
}

export function CustomerFeedbackList({ email }: CustomerFeedbackListProps) {
  const router = useRouter();

  const { data, isLoading } = useQuery({
    queryKey: ['customer-feedbacks', email],
    queryFn: () => customersAPI.getFeedbacks(email),
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className="space-y-2 p-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-14 bg-muted animate-pulse rounded" />
        ))}
      </div>
    );
  }

  const feedbacks = data?.feedbacks ?? [];
  const total = data?.total_count ?? 0;

  if (feedbacks.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-6">
        No feedbacks found for this customer.
      </p>
    );
  }

  return (
    <div>
      <div className="divide-y divide-border rounded-md border border-border overflow-hidden">
        {feedbacks.map((item) => (
          <FeedbackRow
            key={item.id}
            item={item}
            onClick={() => router.push(`/feedbacks/${item.id}`)}
          />
        ))}
      </div>
      <div className="flex items-center justify-between mt-3 px-1 text-sm text-muted-foreground">
        <span>Showing {feedbacks.length} of {total} feedbacks</span>
        <Link
          href={`/feedbacks?customer_email=${encodeURIComponent(email)}`}
          className="text-primary hover:underline font-medium"
        >
          View All →
        </Link>
      </div>
    </div>
  );
}
