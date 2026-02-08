import {
  Circle,
  Search,
  CheckCircle2,
  XCircle,
  ArrowRightLeft,
  UserPlus,
  UserMinus,
  MessageSquare,
  Pencil,
  Trash2,
} from 'lucide-react';

export const WORKFLOW_STATUSES = ['new', 'in_review', 'resolved', 'closed'] as const;
export type WorkflowStatus = (typeof WORKFLOW_STATUSES)[number];

export function getStatusColor(status: string): string {
  switch (status) {
    case 'new': return 'oklch(0.65 0.18 250)'; // blue
    case 'in_review': return 'oklch(0.72 0.16 80)'; // amber
    case 'resolved': return 'oklch(0.65 0.18 145)'; // green
    case 'closed': return 'oklch(0.60 0.02 250)'; // gray
    default: return 'oklch(0.60 0.02 250)';
  }
}

export function getStatusLabel(status: string): string {
  switch (status) {
    case 'new': return 'New';
    case 'in_review': return 'In Review';
    case 'resolved': return 'Resolved';
    case 'closed': return 'Closed';
    default: return status;
  }
}

export function getStatusIcon(status: string) {
  switch (status) {
    case 'new': return Circle;
    case 'in_review': return Search;
    case 'resolved': return CheckCircle2;
    case 'closed': return XCircle;
    default: return Circle;
  }
}

export function getEventIcon(eventType: string) {
  switch (eventType) {
    case 'status_changed': return ArrowRightLeft;
    case 'assigned': return UserPlus;
    case 'unassigned': return UserMinus;
    case 'note_added': return MessageSquare;
    case 'note_edited': return Pencil;
    case 'note_deleted': return Trash2;
    default: return Circle;
  }
}

export function getEventDescription(event: {
  event_type: string;
  actor_email: string;
  old_value: string | null;
  new_value: string | null;
  metadata?: Record<string, any> | null;
}): string {
  const actor = event.actor_email.split('@')[0];
  switch (event.event_type) {
    case 'status_changed':
      return `${actor} changed status from ${getStatusLabel(event.old_value || '')} to ${getStatusLabel(event.new_value || '')}`;
    case 'assigned':
      return `${actor} assigned to ${event.new_value || 'someone'}`;
    case 'unassigned':
      return `${actor} unassigned ${event.old_value || 'someone'}`;
    case 'note_added':
      return `${actor} added a note`;
    case 'note_edited':
      return `${actor} edited a note`;
    case 'note_deleted':
      return `${actor} deleted a note`;
    default:
      return `${actor} performed an action`;
  }
}

export function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}
