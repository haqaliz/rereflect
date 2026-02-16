'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  MessageSquare,
  CircleAlert,
  AlertTriangle,
  Users,
  Activity,
} from 'lucide-react';
import { ActivityFeedItem, ActivityFeedResponse, dashboardV2API } from '@/lib/api/dashboard-v2';

const POLL_INTERVAL = 30_000; // 30 seconds

const severityColors: Record<string, string> = {
  critical: 'var(--destructive)',
  warning: 'var(--chart-2)',
  info: 'var(--chart-3)',
  positive: 'var(--chart-5)',
};

const typeIcons: Record<string, React.ReactNode> = {
  feedback_received: <MessageSquare className="w-4 h-4" />,
  urgent_flagged: <CircleAlert className="w-4 h-4" />,
  anomaly_detected: <AlertTriangle className="w-4 h-4" />,
  team_action: <Users className="w-4 h-4" />,
};

function getRelativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffSec = Math.floor(diffMs / 1000);

  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

export function ActivityFeedWidget() {
  const [items, setItems] = useState<ActivityFeedItem[]>([]);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchFeed = useCallback(async () => {
    try {
      const data: ActivityFeedResponse = await dashboardV2API.getActivityFeed(20);
      setItems(data.items);
      setLastUpdated(data.last_updated);
    } catch {
      // silently fail - widget is supplementary
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFeed();
    const interval = setInterval(fetchFeed, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchFeed]);

  const timeSinceUpdate = lastUpdated
    ? getRelativeTime(lastUpdated)
    : null;

  return (
    <div className="h-full flex flex-col">
      {timeSinceUpdate && (
        <div className="flex justify-end mb-2">
          <span
            className="text-xs px-2 py-1 rounded-md font-mono"
            style={{
              backgroundColor: 'color-mix(in oklch, var(--chart-5) 10%, transparent)',
              color: 'var(--chart-5)',
            }}
          >
            Updated {timeSinceUpdate}
          </span>
        </div>
      )}
      {loading ? (
          <div className="flex items-center justify-center h-full min-h-[300px]">
            <div className="animate-pulse text-muted-foreground text-sm">Loading activity...</div>
          </div>
      ) : items.length > 0 ? (
        <div className="flex-1 overflow-y-auto">
            {items.map((item) => {
              const borderColor = severityColors[item.severity] || 'var(--chart-3)';
              const icon = typeIcons[item.type] || <Activity className="w-4 h-4" />;

              return (
                <div
                  key={item.id}
                  className="flex items-start gap-3 px-4 py-3 border-b last:border-b-0 transition-colors hover:bg-muted/30"
                  style={{ borderLeftWidth: '3px', borderLeftColor: borderColor, borderBottomColor: 'var(--border)' }}
                >
                  <div
                    className="flex-shrink-0 mt-0.5"
                    style={{ color: borderColor }}
                  >
                    {icon}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground leading-tight">{item.title}</p>
                    {item.subtitle && (
                      <p className="text-xs text-muted-foreground mt-0.5 truncate">{item.subtitle}</p>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground flex-shrink-0 font-mono whitespace-nowrap">
                    {getRelativeTime(item.created_at)}
                  </span>
                </div>
              );
            })}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center text-muted-foreground min-h-[300px]">
          <Activity className="w-12 h-12 mb-3 opacity-20" />
          <p className="text-sm">No recent activity</p>
        </div>
      )}
    </div>
  );
}
