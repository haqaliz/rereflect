'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { MessageSquarePlus, ArrowRightLeft, TrendingDown, Sparkles, CheckCircle2 } from 'lucide-react';
import { customersAPI, ActivityEvent } from '@/lib/api/customers';

interface ActivityTimelineProps {
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

interface EventIconConfig {
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  bg: string;
}

const eventIconMap: Record<ActivityEvent['type'], EventIconConfig> = {
  feedback_created: {
    icon: MessageSquarePlus,
    color: 'var(--chart-2)',
    bg: 'color-mix(in oklch, var(--chart-2) 10%, transparent)',
  },
  status_changed: {
    icon: ArrowRightLeft,
    color: 'var(--chart-5)',
    bg: 'color-mix(in oklch, var(--chart-5) 10%, transparent)',
  },
  health_score_changed: {
    icon: TrendingDown,
    color: 'var(--chart-1)',
    bg: 'color-mix(in oklch, var(--chart-1) 10%, transparent)',
  },
  llm_analysis_generated: {
    icon: Sparkles,
    color: 'var(--primary)',
    bg: 'color-mix(in oklch, var(--primary) 10%, transparent)',
  },
  action_completed: {
    icon: CheckCircle2,
    color: 'var(--chart-5)',
    bg: 'color-mix(in oklch, var(--chart-5) 10%, transparent)',
  },
};

function EventIcon({ type }: { type: ActivityEvent['type'] }) {
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

function EventItem({ event }: { event: ActivityEvent }) {
  const relTime = formatRelativeTime(event.timestamp);

  return (
    <div className="flex gap-3 items-start py-2">
      <EventIcon type={event.type} />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-foreground">
          {event.description}
          {event.feedback_id && (event.type === 'feedback_created' || event.type === 'status_changed') && (
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

export function ActivityTimeline({ email }: ActivityTimelineProps) {
  const { data, isLoading } = useQuery({
    queryKey: ['customer-activity', email],
    queryFn: () => customersAPI.getActivity(email),
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-10 bg-muted animate-pulse rounded" />
        ))}
      </div>
    );
  }

  const events = data?.events ?? [];

  if (events.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-4">
        No recent activity
      </p>
    );
  }

  return (
    <div className="divide-y divide-border">
      {events.map((event, idx) => (
        <EventItem key={idx} event={event} />
      ))}
    </div>
  );
}
