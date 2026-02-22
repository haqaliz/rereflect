'use client';

import { useState, useEffect } from 'react';
import { aiSettingsAPI, type AIBudget } from '@/lib/api/ai-settings';
import { BudgetBanner } from './BudgetBanner';

export function BudgetBannerWrapper() {
  const [budget, setBudget] = useState<AIBudget | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) return;

    aiSettingsAPI.getBudget()
      .then(setBudget)
      .catch(() => {
        // Silently fail — budget banner is non-critical
      });
  }, []);

  return <BudgetBanner budget={budget} />;
}
