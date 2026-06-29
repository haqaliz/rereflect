'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { customersAPI, ActivityEvent } from '@/lib/api/customers';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { eventIconMap } from './ActivityTimeline';
import Link from 'next/link';

interface CustomerTimelineProps {
  email: string;
}

function formatRelativeTime(timestamp: string): string {
  const now = Date.now();
  const then = new Date(timestamp).getTime();
  const diffMs = now - then;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins} minute${diffMins === 1 ? '' : 's'} ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
  if (diffDays < 30) return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
  return new Date(timestamp).toLocaleDateString();
}

function TimelineEventIcon({ type }: { type: ActivityEvent['type'] }) {
  const config = eventIconMap[type];
  if (!config) {
    return <span className="w-7 h-7 flex-shrink-0 rounded-full bg-muted" />;
  }
  const Icon = config.icon;
  return (
    <span
      className="flex-shrink-0 flex items-center justify-center w-7 h-7 rounded-full p-1.5"
      style={{ backgroundColor: config.bg, color: config.color }}
      aria-hidden="true"
    >
      <Icon className="w-4 h-4 [color:inherit]" />
    </span>
  );
}

function TimelineEventItem({ event }: { event: ActivityEvent }) {
  const relTime = formatRelativeTime(event.timestamp);
  return (
    <div className="flex gap-3 items-start py-2">
      <TimelineEventIcon type={event.type} />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-foreground">
          {event.description}
          {event.feedback_id &&
            (event.type === 'feedback_created' || event.type === 'status_changed') && (
              <>
                {' '}
                <Link
                  href={`/feedbacks/${event.feedback_id}`}
                  className="text-primary hover:underline text-xs"
                >
                  #{event.feedback_id}
                </Link>
              </>
            )}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">{relTime}</p>
      </div>
    </div>
  );
}

function TimelineSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-5/6" />
      <Skeleton className="h-32 w-full" />
    </div>
  );
}

export function CustomerTimeline({ email }: CustomerTimelineProps) {
  // Cursor state: undefined = first page (no cursor param sent), string = next page
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  // All accumulated events across pages
  const [allEvents, setAllEvents] = useState<ActivityEvent[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  const { isLoading } = useQuery({
    queryKey: ['customer-timeline', email],
    queryFn: async () => {
      const result = await customersAPI.getTimeline(email, {});
      setAllEvents(result.events);
      setNextCursor(result.next_cursor);
      return result;
    },
    staleTime: 5 * 60 * 1000,
  });

  const handleLoadMore = async () => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const result = await customersAPI.getTimeline(email, { before: nextCursor });
      setAllEvents((prev) => [...prev, ...result.events]);
      setNextCursor(result.next_cursor);
    } finally {
      setLoadingMore(false);
    }
  };

  // Suppress unused variable warning — cursor kept for future use if needed
  void cursor;
  void setCursor;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Full Activity Timeline</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <TimelineSkeleton />
        ) : allEvents.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">No activity yet</p>
        ) : (
          <div className="divide-y divide-border">
            {allEvents.map((event, idx) => (
              <TimelineEventItem key={`${event.type}-${event.timestamp}-${idx}`} event={event} />
            ))}
          </div>
        )}

        {!isLoading && nextCursor !== null && (
          <div className="mt-3 flex justify-center">
            <Button
              variant="outline"
              size="sm"
              onClick={handleLoadMore}
              disabled={loadingMore}
            >
              {loadingMore ? 'Loading…' : 'Load more'}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
