'use client';

import { useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

export type DateRange = '7d' | '14d' | '30d' | '90d' | 'ytd';

const VALID_RANGES: DateRange[] = ['7d', '14d', '30d', '90d', 'ytd'];
const STORAGE_KEY = 'rr-dashboard-date-range';
const DEFAULT_RANGE: DateRange = '30d';

function isValidRange(value: string | null): value is DateRange {
  return value !== null && VALID_RANGES.includes(value as DateRange);
}

export function dateRangeToDays(range: DateRange): number {
  switch (range) {
    case '7d': return 7;
    case '14d': return 14;
    case '30d': return 30;
    case '90d': return 90;
    case 'ytd': {
      const now = new Date();
      const startOfYear = new Date(now.getFullYear(), 0, 1);
      return Math.ceil((now.getTime() - startOfYear.getTime()) / (1000 * 60 * 60 * 24));
    }
    default: return 30;
  }
}

export function useDateRange() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const dateRange: DateRange = useMemo(() => {
    const urlRange = searchParams.get('range');
    if (isValidRange(urlRange)) return urlRange;

    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (isValidRange(stored)) return stored;
    }

    return DEFAULT_RANGE;
  }, [searchParams]);

  const days = useMemo(() => dateRangeToDays(dateRange), [dateRange]);

  const setDateRange = useCallback(
    (range: DateRange) => {
      if (typeof window !== 'undefined') {
        localStorage.setItem(STORAGE_KEY, range);
      }
      const params = new URLSearchParams(searchParams.toString());
      params.set('range', range);
      router.replace(`?${params.toString()}`, { scroll: false });
    },
    [router, searchParams]
  );

  return { dateRange, setDateRange, days } as const;
}
