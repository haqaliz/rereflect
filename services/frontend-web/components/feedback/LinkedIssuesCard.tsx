'use client';

import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ExternalLink } from 'lucide-react';
import { linearAPI, LinearIssue, LINEAR_PRIORITY_LABELS } from '@/lib/api/linear';

interface LinkedIssuesCardProps {
  feedbackId: number;
}

function getStatusColor(status: string | null): string {
  if (!status) return 'text-muted-foreground';
  const s = status.toLowerCase();
  if (s.includes('done') || s.includes('completed')) return 'text-green-600';
  if (s.includes('progress') || s.includes('started')) return 'text-blue-600';
  if (s.includes('cancel')) return 'text-muted-foreground line-through';
  return 'text-foreground';
}

function getPriorityIcon(priority: number | null): string {
  if (priority === null) return '';
  const icons: Record<number, string> = { 0: '—', 1: '🔴', 2: '🟠', 3: '🟡', 4: '🟢' };
  return icons[priority] ?? '—';
}

export function LinkedIssuesCard({ feedbackId }: LinkedIssuesCardProps) {
  const [issues, setIssues] = useState<LinearIssue[]>([]);
  const [loaded, setLoaded] = useState(false);

  const fetchIssues = useCallback(async () => {
    try {
      const data = await linearAPI.getLinkedIssues(feedbackId);
      setIssues(data);
    } catch {
      // ignore — silently skip if not connected
    } finally {
      setLoaded(true);
    }
  }, [feedbackId]);

  useEffect(() => {
    fetchIssues();
  }, [fetchIssues]);

  if (!loaded || issues.length === 0) return null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <ExternalLink className="w-4 h-4" />
          Linked Issues
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {issues.map(issue => (
          <div
            key={issue.id}
            className="flex items-start gap-3 p-3 rounded-lg border border-border bg-card/50"
          >
            {/* Priority icon */}
            {issue.linear_priority !== null && (
              <span className="text-sm mt-0.5" title={LINEAR_PRIORITY_LABELS[issue.linear_priority]}>
                {getPriorityIcon(issue.linear_priority)}
              </span>
            )}

            <div className="flex-1 min-w-0">
              {/* Identifier + Title */}
              <div className="flex items-center gap-2 flex-wrap">
                <a
                  href={issue.linear_issue_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-mono text-sm font-semibold text-primary hover:underline flex items-center gap-1"
                >
                  {issue.linear_issue_identifier}
                  <ExternalLink className="w-3 h-3" />
                </a>
                {issue.linear_status && (
                  <Badge variant="secondary" className={`text-xs ${getStatusColor(issue.linear_status)}`}>
                    {issue.linear_status}
                  </Badge>
                )}
                {issue.linear_priority !== null && (
                  <span className="text-xs text-muted-foreground">
                    {LINEAR_PRIORITY_LABELS[issue.linear_priority]}
                  </span>
                )}
              </div>

              {/* Title */}
              <p className="text-sm mt-0.5 truncate">{issue.linear_issue_title}</p>

              {/* Assignee */}
              {issue.linear_assignee && (
                <p className="text-xs text-muted-foreground mt-1">
                  Assigned to {issue.linear_assignee}
                </p>
              )}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
