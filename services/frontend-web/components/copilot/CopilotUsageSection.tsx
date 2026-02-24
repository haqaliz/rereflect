'use client';

import { MessageSquare, Zap } from 'lucide-react';
import type { CopilotUsageResponse } from '@/lib/api/conversations';

function formatNumber(n: number): string {
  return n.toLocaleString();
}

interface CopilotUsageSectionProps {
  usage: CopilotUsageResponse;
}

export function CopilotUsageSection({ usage }: CopilotUsageSectionProps) {
  const hasTokenBudget =
    usage.tokens_used_month !== undefined &&
    usage.tokens_budget_month != null;

  const tokenPct = hasTokenBudget
    ? Math.min(100, Math.round((usage.tokens_used_month! / usage.tokens_budget_month!) * 100))
    : 0;

  const isFree = usage.daily_limit !== null;

  return (
    <div className="space-y-4" data-testid="copilot-usage-section">
      <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
        <Zap className="w-4 h-4 text-primary" />
        AI Copilot Usage
      </h3>

      {/* Token usage bar (only when budget is set) */}
      {hasTokenBudget && (
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>Tokens this month</span>
            <span data-testid="copilot-tokens-text">
              {formatNumber(usage.tokens_used_month!)} / {formatNumber(usage.tokens_budget_month!)}
            </span>
          </div>
          <div
            data-testid="copilot-token-bar"
            className="h-2 bg-muted rounded-full overflow-hidden"
          >
            <div
              className={`h-full rounded-full transition-all ${
                tokenPct >= 90 ? 'bg-destructive' : tokenPct >= 70 ? 'bg-amber-500' : 'bg-primary'
              }`}
              style={{ width: `${tokenPct}%` }}
            />
          </div>
          <p className="text-xs text-muted-foreground text-right">{tokenPct}% used</p>
        </div>
      )}

      {/* Queries today */}
      <div className="flex items-center gap-3">
        <div className="p-2 bg-secondary rounded-lg">
          <MessageSquare className="w-4 h-4 text-primary" />
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Queries today</p>
          <p className="text-sm font-medium text-foreground" data-testid="copilot-queries-today">
            {isFree
              ? `${usage.queries_today}/${usage.daily_limit}`
              : String(usage.queries_today)}
          </p>
        </div>
      </div>
    </div>
  );
}
