import {
  AlertTriangle,
  TrendingDown,
  UserX,
  BarChart3,
} from 'lucide-react';

export const TYPE_ICONS: Record<string, typeof AlertTriangle> = {
  urgent_feedback: AlertTriangle,
  sentiment_spike: TrendingDown,
  churn_risk: UserX,
  volume_spike: BarChart3,
};

export const TYPE_COLORS: Record<string, string> = {
  urgent_feedback: 'text-destructive',
  sentiment_spike: 'text-orange-500',
  churn_risk: 'text-yellow-500',
  volume_spike: 'text-blue-500',
};

export function timeAgo(dateString: string): string {
  const now = new Date();
  const date = new Date(dateString);
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
  return date.toLocaleDateString();
}
