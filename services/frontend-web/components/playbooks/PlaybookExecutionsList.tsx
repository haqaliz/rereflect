'use client';

import React from 'react';
import { Badge } from '@/components/ui/badge';
import { type PlaybookExecution } from '@/lib/api/playbooks';

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

interface PlaybookExecutionsListProps {
  executions: PlaybookExecution[];
}

export function PlaybookExecutionsList({ executions }: PlaybookExecutionsListProps) {
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
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {executions.map((ex) => {
            const style = STATUS_STYLES[ex.status] ?? { label: ex.status, color: 'var(--muted-foreground)' };
            return (
              <tr key={ex.id} className="hover:bg-muted/30 transition-colors">
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
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
