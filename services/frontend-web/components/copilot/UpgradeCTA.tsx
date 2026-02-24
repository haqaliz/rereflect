'use client';

import { useRouter } from 'next/navigation';
import { Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';

export type UpgradeCTAVariant = 'inline' | 'banner' | 'modal';

interface UpgradeCTAProps {
  message: string;
  variant: UpgradeCTAVariant;
  onUpgrade?: () => void;
}

export function UpgradeCTA({ message, variant, onUpgrade }: UpgradeCTAProps) {
  const router = useRouter();

  const handleUpgrade = () => {
    if (onUpgrade) {
      onUpgrade();
    } else {
      router.push('/settings/billing');
    }
  };

  if (variant === 'banner') {
    return (
      <div
        data-testid="upgrade-cta-component"
        data-variant="banner"
        className="flex items-center justify-between px-4 py-2.5 bg-amber-500/10 border-b border-amber-500/20 text-amber-700 dark:text-amber-400"
      >
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 shrink-0" />
          <span className="text-sm font-medium">{message}</span>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={handleUpgrade}
          className="ml-4 border-amber-500/40 hover:bg-amber-500/10 text-amber-700 dark:text-amber-400 shrink-0"
        >
          Upgrade
        </Button>
      </div>
    );
  }

  if (variant === 'modal') {
    return (
      <div
        data-testid="upgrade-cta-component"
        data-variant="modal"
        className="flex flex-col items-center gap-3 py-6 px-4 text-center"
      >
        <div className="p-3 bg-primary/10 rounded-full">
          <Sparkles className="w-6 h-6 text-primary" />
        </div>
        <p className="text-sm text-muted-foreground">{message}</p>
        <Button onClick={handleUpgrade}>Upgrade</Button>
      </div>
    );
  }

  // inline (default)
  return (
    <div
      data-testid="upgrade-cta-component"
      data-variant="inline"
      className="flex items-center gap-2 text-sm text-muted-foreground"
    >
      <Sparkles className="w-3.5 h-3.5 text-primary shrink-0" />
      <span>{message}</span>
      <Button size="sm" variant="link" onClick={handleUpgrade} className="px-0 h-auto font-medium text-primary">
        Upgrade
      </Button>
    </div>
  );
}
