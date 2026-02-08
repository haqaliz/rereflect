'use client';

import { useRouter } from 'next/navigation';
import { WorkflowFeedbackItem } from '@/lib/api/workflow';
import { formatRelativeTime, getStatusColor } from '@/lib/workflow-utils';
import { Card } from '@/components/ui/card';

interface KanbanCardProps {
  item: WorkflowFeedbackItem;
}

export function KanbanCard({ item }: KanbanCardProps) {
  const router = useRouter();

  const getSentimentColor = (sentiment: string | null) => {
    switch (sentiment?.toLowerCase()) {
      case 'positive':
        return 'oklch(0.65 0.18 145)'; // green
      case 'negative':
        return 'oklch(0.55 0.22 25)'; // red
      case 'neutral':
        return 'oklch(0.72 0.14 65)'; // amber
      default:
        return 'oklch(0.60 0.02 250)'; // gray
    }
  };

  const handleCardClick = () => {
    router.push(`/feedbacks/${item.id}`);
  };

  return (
    <Card
      className="p-3 cursor-pointer hover:shadow-md transition-shadow"
      onClick={handleCardClick}
    >
      <div className="space-y-2">
        <p className="text-sm line-clamp-2">{item.text}</p>

        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5">
            <div
              className="w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: getSentimentColor(item.sentiment_label) }}
            />
            <span className="text-muted-foreground">
              {item.sentiment_label || 'Unknown'}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">
              {formatRelativeTime(item.created_at)}
            </span>
            {item.assigned_to_email && (
              <div
                className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium text-white"
                style={{ backgroundColor: getStatusColor(item.workflow_status) }}
                title={item.assigned_to_email}
              >
                {item.assigned_to_email[0].toUpperCase()}
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
