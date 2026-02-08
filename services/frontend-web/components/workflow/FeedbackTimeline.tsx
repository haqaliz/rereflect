'use client';

import { useState, useEffect } from 'react';
import { workflowAPI, TimelineEvent } from '@/lib/api/workflow';
import {
  formatRelativeTime,
  getStatusColor,
  getStatusLabel,
} from '@/lib/workflow-utils';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

interface FeedbackTimelineProps {
  feedbackId: number;
}

function getEventLabel(type: string): string {
  switch (type) {
    case 'status_changed': return 'Status Change';
    case 'assigned': return 'Assigned';
    case 'unassigned': return 'Unassigned';
    case 'note_added': return 'Note Added';
    case 'note_edited': return 'Note Edited';
    case 'note_deleted': return 'Note Deleted';
    default: return 'Activity';
  }
}

function getEventBadgeColor(type: string): string {
  switch (type) {
    case 'status_changed': return 'oklch(0.72 0.14 65)';
    case 'assigned':
    case 'unassigned': return 'oklch(0.65 0.16 250)';
    case 'note_added':
    case 'note_edited':
    case 'note_deleted': return 'oklch(0.65 0.18 145)';
    default: return 'oklch(0.60 0.02 250)';
  }
}

export function FeedbackTimeline({ feedbackId }: FeedbackTimelineProps) {
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchTimeline = async () => {
      try {
        const events = await workflowAPI.getTimeline(feedbackId);
        setTimeline(events);
      } catch (error) {
        console.error('Failed to fetch timeline:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchTimeline();
  }, [feedbackId]);

  if (isLoading) {
    return <div className="text-sm text-muted-foreground">Loading activity...</div>;
  }

  if (timeline.length === 0) {
    return <div className="text-sm text-muted-foreground">No activity yet.</div>;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[140px]">Type</TableHead>
          <TableHead>Activity</TableHead>
          <TableHead className="w-[100px]">From</TableHead>
          <TableHead className="w-[100px]">To</TableHead>
          <TableHead className="w-[80px] text-right">Time</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {timeline.map((event) => {
          const actor = event.actor_email.split('@')[0];
          const isStatusChange = event.event_type === 'status_changed';
          const isAssignment = event.event_type === 'assigned' || event.event_type === 'unassigned';
          const resolutionNote = event.metadata?.resolution_note;
          const badgeColor = getEventBadgeColor(event.event_type);

          return (
            <TableRow key={event.id}>
              <TableCell>
                <Badge
                  variant="outline"
                  className="text-xs whitespace-nowrap"
                  style={{ borderColor: badgeColor, color: badgeColor }}
                >
                  {getEventLabel(event.event_type)}
                </Badge>
              </TableCell>
              <TableCell>
                <div className="space-y-1">
                  <p className="text-sm">
                    <span className="font-medium">{actor}</span>
                    {isStatusChange && (
                      <span className="text-muted-foreground"> changed status</span>
                    )}
                    {event.event_type === 'assigned' && (
                      <span className="text-muted-foreground"> assigned feedback</span>
                    )}
                    {event.event_type === 'unassigned' && (
                      <span className="text-muted-foreground"> unassigned feedback</span>
                    )}
                    {event.event_type === 'note_added' && (
                      <span className="text-muted-foreground"> added a note</span>
                    )}
                    {event.event_type === 'note_edited' && (
                      <span className="text-muted-foreground"> edited a note</span>
                    )}
                    {event.event_type === 'note_deleted' && (
                      <span className="text-muted-foreground"> deleted a note</span>
                    )}
                  </p>
                  {resolutionNote && (
                    <p className="text-xs text-muted-foreground bg-muted/50 border border-border rounded px-2 py-1">
                      {resolutionNote}
                    </p>
                  )}
                </div>
              </TableCell>
              <TableCell>
                {isStatusChange && event.old_value ? (
                  <Badge
                    variant="outline"
                    className="text-xs"
                    style={{ borderColor: getStatusColor(event.old_value), color: getStatusColor(event.old_value) }}
                  >
                    {getStatusLabel(event.old_value)}
                  </Badge>
                ) : isAssignment && event.old_value ? (
                  <span className="text-xs text-muted-foreground">{event.old_value.split('@')[0]}</span>
                ) : (
                  <span className="text-xs text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell>
                {isStatusChange && event.new_value ? (
                  <Badge
                    variant="outline"
                    className="text-xs"
                    style={{ borderColor: getStatusColor(event.new_value), color: getStatusColor(event.new_value) }}
                  >
                    {getStatusLabel(event.new_value)}
                  </Badge>
                ) : isAssignment && event.new_value ? (
                  <span className="text-xs text-muted-foreground">{event.new_value.split('@')[0]}</span>
                ) : (
                  <span className="text-xs text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell className="text-right">
                <span className="text-xs text-muted-foreground whitespace-nowrap">
                  {formatRelativeTime(event.created_at)}
                </span>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
