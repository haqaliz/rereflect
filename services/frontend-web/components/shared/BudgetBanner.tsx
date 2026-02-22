'use client';

import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { AlertTriangle } from 'lucide-react';
import type { AIBudget } from '@/lib/api/ai-settings';

interface BudgetBannerProps {
  budget: AIBudget | null;
}

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function formatResetDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export function BudgetBanner({ budget }: BudgetBannerProps) {
  const router = useRouter();

  if (!budget || !budget.is_exceeded) {
    return null;
  }

  const usedFormatted = formatCents(budget.used_cents);
  const limitFormatted = formatCents(budget.monthly_limit_cents);
  const resetDate = formatResetDate(budget.resets_at);

  return (
    <div className="relative overflow-hidden bg-gradient-to-r from-amber-500/10 to-amber-500/5 border border-amber-500/30 rounded-lg px-4 py-3">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-amber-500/20 rounded-lg">
            <AlertTriangle className="w-5 h-5 text-amber-600" />
          </div>
          <div>
            <p className="font-medium text-foreground">
              AI budget exceeded ({usedFormatted} / {limitFormatted})
            </p>
            <p className="text-sm text-muted-foreground">
              New feedback won&apos;t be analyzed until {resetDate}.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button
            size="sm"
            onClick={() => router.push('/settings/billing')}
          >
            Upgrade Plan
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => router.push('/settings/ai?tab=providers')}
          >
            Add Your Own API Key
          </Button>
        </div>
      </div>
    </div>
  );
}
