'use client';

import { WORKFLOW_STATUSES, getStatusLabel, getStatusColor } from '@/lib/workflow-utils';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { X } from 'lucide-react';

interface BulkActionsBarProps {
  selectedCount: number;
  onStatusChange: (status: string) => void;
  onAssign: (userId: number | null) => void;
  onClear: () => void;
  teamMembers: { id: number; email: string }[];
}

export function BulkActionsBar({
  selectedCount,
  onStatusChange,
  onAssign,
  onClear,
  teamMembers,
}: BulkActionsBarProps) {
  if (selectedCount === 0) return null;

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-bottom-5">
      <div className="bg-background border border-border shadow-lg rounded-lg px-6 py-4 flex items-center gap-4">
        <span className="text-sm font-medium">
          {selectedCount} selected
        </span>

        <div className="h-6 w-px bg-border" />

        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Status:</span>
          <Select onValueChange={onStatusChange}>
            <SelectTrigger className="w-[140px] h-9">
              <SelectValue placeholder="Change status" />
            </SelectTrigger>
            <SelectContent>
              {WORKFLOW_STATUSES.map((status) => (
                <SelectItem key={status} value={status}>
                  <div className="flex items-center gap-2">
                    <div
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: getStatusColor(status) }}
                    />
                    {getStatusLabel(status)}
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Assign to:</span>
          <Select onValueChange={(value) => onAssign(value === 'unassigned' ? null : parseInt(value, 10))}>
            <SelectTrigger className="w-[180px] h-9">
              <SelectValue placeholder="Select assignee" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="unassigned">
                <span className="text-muted-foreground">Unassigned</span>
              </SelectItem>
              {teamMembers.map((member) => (
                <SelectItem key={member.id} value={member.id.toString()}>
                  {member.email}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="h-6 w-px bg-border" />

        <Button
          variant="ghost"
          size="icon"
          onClick={onClear}
          className="h-9 w-9"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
