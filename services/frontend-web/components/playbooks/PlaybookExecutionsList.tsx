'use client';

import React, { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ChevronDown, ChevronRight } from 'lucide-react';
import {
  ACTION_TYPE_LABELS,
  type PlaybookExecution,
  type PlaybookActionLogEntry,
} from '@/lib/api/playbooks';

const STATUS_STYLES: Record<string, { label: string; color: string }> = {
  queued: { label: 'Queued', color: 'var(--chart-2)' },
  running: { label: 'Running', color: 'var(--chart-1)' },
  done: { label: 'Done', color: 'var(--chart-5)' },
  failed: { label: 'Failed', color: 'var(--destructive)' },
  cancelled: { label: 'Cancelled', color: 'var(--muted-foreground)' },
};

function formatTs(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

/** Safe one-line summary of an action_log result (legacy rows may carry non-object results). */
function summarizeResult(result: unknown): string | null {
  if (result === undefined || result === null) return null;
  if (typeof result === 'object') return JSON.stringify(result);
  return String(result);
}

function ActionLogEntryView({ entry }: { entry: PlaybookActionLogEntry }) {
  const summary = summarizeResult(entry.result);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="font-medium text-xs min-w-[8rem]">
        {ACTION_TYPE_LABELS[entry.type] ?? entry.type}
      </span>
      <Badge variant={entry.ok ? 'secondary' : 'destructive'} className="text-xs">
        {entry.ok ? 'OK' : 'Error'}
      </Badge>
      {entry.error && (
        <span className="text-xs text-destructive">{entry.error}</span>
      )}
      {summary && (
        <code className="text-xs text-muted-foreground break-all">{summary}</code>
      )}
    </div>
  );
}

interface PlaybookExecutionsListProps {
  executions: PlaybookExecution[];
}

export function PlaybookExecutionsList({ executions }: PlaybookExecutionsListProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  if (executions.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-6">
        No executions yet.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-muted-foreground text-left">
            <th className="pb-2 font-medium">Customer</th>
            <th className="pb-2 font-medium">Status</th>
            <th className="pb-2 font-medium">Triggered By</th>
            <th className="pb-2 font-medium">Started</th>
            <th className="pb-2 font-medium">Completed</th>
            <th className="pb-2 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {executions.map((ex) => {
            const style = STATUS_STYLES[ex.status] ?? { label: ex.status, color: 'var(--muted-foreground)' };
            const expanded = expandedId === ex.id;
            const logEntries = ex.action_log ?? [];
            return (
              <React.Fragment key={ex.id}>
                <tr className="hover:bg-muted/30 transition-colors">
                  <td className="py-2 font-mono text-xs">{ex.customer_email}</td>
                  <td className="py-2">
                    <Badge
                      variant="outline"
                      className="text-xs font-normal"
                      style={{
                        color: style.color,
                        borderColor: `color-mix(in oklch, ${style.color} 30%, transparent)`,
                        backgroundColor: `color-mix(in oklch, ${style.color} 10%, transparent)`,
                      }}
                    >
                      {style.label}
                    </Badge>
                  </td>
                  <td className="py-2 text-muted-foreground capitalize">{ex.triggered_by.replace('_', ' ')}</td>
                  <td className="py-2 text-xs text-muted-foreground">{formatTs(ex.started_at)}</td>
                  <td className="py-2 text-xs text-muted-foreground">{formatTs(ex.completed_at)}</td>
                  <td className="py-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 text-xs text-muted-foreground"
                      aria-label="View actions"
                      onClick={() => setExpandedId(expanded ? null : ex.id)}
                    >
                      {expanded ? (
                        <ChevronDown className="w-3.5 h-3.5 mr-1" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5 mr-1" />
                      )}
                      View actions
                    </Button>
                  </td>
                </tr>
                {expanded && (
                  <tr data-testid={`execution-actions-${ex.id}`} className="bg-muted/20">
                    <td colSpan={6} className="px-4 py-3 space-y-2">
                      {logEntries.length === 0 ? (
                        <p className="text-xs text-muted-foreground">No actions recorded</p>
                      ) : (
                        logEntries.map((entry, i) => (
                          <ActionLogEntryView key={i} entry={entry} />
                        ))
                      )}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}