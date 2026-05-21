'use client';

import { useState, useEffect } from 'react';
import { RotateCcw, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { RecoverCustomerDialog } from '@/components/customers/RecoverCustomerDialog';
import type { ChurnEvent } from '@/lib/api/churn-events';

interface PotentialWinbackBannerProps {
  has_potential_winback: boolean;
  customerEmail: string;
  onRecovered?: (event: ChurnEvent) => void;
}

export function PotentialWinbackBanner({
  has_potential_winback,
  customerEmail,
  onRecovered,
}: PotentialWinbackBannerProps) {
  const [dismissed, setDismissed] = useState(false);
  const [recoverDialogOpen, setRecoverDialogOpen] = useState(false);

  // Re-show banner when the prop flips back to true (e.g. parent re-fetches).
  useEffect(() => {
    if (has_potential_winback) {
      setDismissed(false);
    }
  }, [has_potential_winback]);

  if (!has_potential_winback || dismissed) {
    return null;
  }

  return (
    <>
      <div
        role="alert"
        className="flex items-center justify-between gap-3 rounded-lg border px-4 py-3"
        style={{
          backgroundColor: 'color-mix(in oklch, var(--chart-2) 10%, transparent)',
          borderColor: 'color-mix(in oklch, var(--chart-2) 30%, transparent)',
        }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <RotateCcw
            className="w-4 h-4 shrink-0"
            style={{ color: 'var(--chart-2)' }}
          />
          <p className="text-sm text-foreground">
            <strong>{customerEmail}</strong> sent new feedback after churning — potential winback
            opportunity.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button
            size="sm"
            onClick={() => setRecoverDialogOpen(true)}
            style={{
              backgroundColor: 'var(--chart-2)',
              color: 'var(--background)',
            }}
          >
            Confirm recovery
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setDismissed(true)}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="w-4 h-4 mr-1" />
            Dismiss for now
          </Button>
        </div>
      </div>

      <RecoverCustomerDialog
        open={recoverDialogOpen}
        onOpenChange={setRecoverDialogOpen}
        customerEmail={customerEmail}
        onSuccess={(event) => {
          setRecoverDialogOpen(false);
          onRecovered?.(event);
        }}
      />
    </>
  );
}
