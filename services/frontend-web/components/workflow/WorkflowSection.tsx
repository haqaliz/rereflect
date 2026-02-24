'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { workflowAPI } from '@/lib/api/workflow';
import { getStatusColor, getStatusLabel, WORKFLOW_STATUSES } from '@/lib/workflow-utils';
import apiClient from '@/lib/api-client';
import { NotesList } from './NotesList';
import { MarkdownEditor } from './MarkdownEditor';

interface TeamMember {
  id: number;
  email: string;
  role: string;
}

interface WorkflowSectionProps {
  feedbackId: number;
  workflowStatus: string;
  assignedTo: number | null;
  assignedToEmail: string | null;
  onStatusChange: (status: string) => void;
  onAssigneeChange: (userId: number | null) => void;
  currentUserId: number;
}

export function WorkflowSection({
  feedbackId,
  workflowStatus,
  assignedTo,
  assignedToEmail,
  onStatusChange,
  onAssigneeChange,
  currentUserId,
}: WorkflowSectionProps) {
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);
  const [isLoadingMembers, setIsLoadingMembers] = useState(true);
  const [showResolutionNote, setShowResolutionNote] = useState(false);
  const [resolutionNote, setResolutionNote] = useState('');
  const [isChangingStatus, setIsChangingStatus] = useState(false);
  const [pendingStatus, setPendingStatus] = useState<string | null>(null);

  // Fetch team members on mount
  useEffect(() => {
    const fetchTeamMembers = async () => {
      try {
        const response = await apiClient.get('/api/v1/team/members');
        setTeamMembers(response.data.members || []);
      } catch (error) {
        console.error('Failed to fetch team members:', error);
      } finally {
        setIsLoadingMembers(false);
      }
    };

    fetchTeamMembers();
  }, []);

  const handleStatusChange = async (newStatus: string) => {
    // If changing to "resolved", show resolution note input
    if (newStatus === 'resolved') {
      setPendingStatus(newStatus);
      setShowResolutionNote(true);
      return;
    }

    // Clear any pending resolution note if user picks a different status
    if (showResolutionNote) {
      setShowResolutionNote(false);
      setResolutionNote('');
      setPendingStatus(null);
    }

    // Otherwise, change status immediately
    try {
      setIsChangingStatus(true);
      await workflowAPI.changeStatus([feedbackId], newStatus);
      onStatusChange(newStatus);
    } catch (error) {
      console.error('Failed to change status:', error);
    } finally {
      setIsChangingStatus(false);
    }
  };

  const handleResolveWithNote = async () => {
    if (!pendingStatus) return;

    try {
      setIsChangingStatus(true);
      await workflowAPI.changeStatus(
        [feedbackId],
        pendingStatus,
        resolutionNote.trim() || undefined
      );
      onStatusChange(pendingStatus);
      setShowResolutionNote(false);
      setResolutionNote('');
      setPendingStatus(null);
    } catch (error) {
      console.error('Failed to resolve with note:', error);
    } finally {
      setIsChangingStatus(false);
    }
  };

  const handleCancelResolve = () => {
    setShowResolutionNote(false);
    setResolutionNote('');
    setPendingStatus(null);
  };

  const handleAssigneeChange = async (value: string) => {
    const userId = value === 'unassigned' ? null : parseInt(value, 10);

    try {
      await workflowAPI.assign([feedbackId], userId);
      onAssigneeChange(userId);
    } catch (error) {
      console.error('Failed to assign feedback:', error);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Workflow</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Status + Assignee Row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Status Selector */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Status</label>
            <Select
              value={pendingStatus || workflowStatus}
              onValueChange={handleStatusChange}
              disabled={isChangingStatus}
            >
              <SelectTrigger>
                <SelectValue>
                  <div className="flex items-center gap-2">
                    <div
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: getStatusColor(pendingStatus || workflowStatus) }}
                    />
                    {getStatusLabel(pendingStatus || workflowStatus)}
                  </div>
                </SelectValue>
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

          {/* Assignee Selector */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Assigned To</label>
            <Select
              value={assignedTo?.toString() || 'unassigned'}
              onValueChange={handleAssigneeChange}
              disabled={isLoadingMembers}
            >
              <SelectTrigger>
                <SelectValue>
                  {assignedToEmail || 'Unassigned'}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="unassigned">Unassigned</SelectItem>
                {teamMembers.map((member) => (
                  <SelectItem key={member.id} value={member.id.toString()}>
                    {member.email}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Resolution Note Input */}
        {showResolutionNote && (
          <div className="space-y-2 p-4 border border-border rounded-lg bg-muted/30">
            <label className="text-sm font-medium">
              Resolution Note (optional)
            </label>
            <MarkdownEditor
              value={resolutionNote}
              onChange={setResolutionNote}
              placeholder="Describe how this was resolved..."
              rows={3}
            />
            <div className="flex gap-2">
              <Button
                onClick={handleResolveWithNote}
                disabled={isChangingStatus}
                size="sm"
              >
                {isChangingStatus ? 'Resolving...' : 'Resolve'}
              </Button>
              <Button
                onClick={handleCancelResolve}
                variant="outline"
                size="sm"
                disabled={isChangingStatus}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}

        {/* Notes Section */}
        <div className="space-y-2">
          <h3 className="text-sm font-medium">Notes</h3>
          <NotesList feedbackId={feedbackId} currentUserId={currentUserId} />
        </div>
      </CardContent>
    </Card>
  );
}
