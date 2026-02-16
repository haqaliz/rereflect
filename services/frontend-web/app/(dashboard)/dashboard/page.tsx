'use client';

import { Suspense } from 'react';
import { Clock } from 'lucide-react';
import { DashboardGrid } from '@/components/dashboard/DashboardGrid';
import { DateRangeSelector } from '@/components/dashboard/DateRangeSelector';
import { useDateRange } from '@/components/dashboard/hooks/useDateRange';
import { DashboardSkeleton } from '@/components/shared/page-skeletons';

function DashboardContent() {
  const { days } = useDateRange();

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Page Title + Date Range */}
        <div className="animate-fade-in">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-3">
              <h2 className="text-4xl font-bold text-text-primary">Dashboard</h2>
              <div className="flex items-center space-x-2 text-text-tertiary text-sm font-mono">
                <Clock className="w-4 h-4" />
                <span>Last {days}d</span>
              </div>
            </div>
            <DateRangeSelector />
          </div>
          <p className="text-text-secondary text-lg">Real-time customer feedback analytics and insights</p>
        </div>

        {/* Dashboard Grid */}
        <DashboardGrid days={days} />
      </main>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<DashboardSkeleton />}>
      <DashboardContent />
    </Suspense>
  );
}
