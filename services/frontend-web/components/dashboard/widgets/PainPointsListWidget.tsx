'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  AlertTriangle,
  ArrowRight,
  ShieldAlert,
  DatabaseZap,
  CreditCard,
  ServerCrash,
  KeyRound,
  CircleX,
  Gauge,
  MousePointerClick,
  Laptop,
  PackageX,
  FileQuestion,
  Paintbrush,
} from 'lucide-react';
import { CategoryCount } from '@/lib/api/dashboard';
import { getPainPointLabel } from '@/lib/category-utils';

interface PainPointsListWidgetProps {
  categories: CategoryCount[];
}

const iconMap: Record<string, React.ReactNode> = {
  security_breach: <ShieldAlert className="w-3.5 h-3.5" />,
  data_loss: <DatabaseZap className="w-3.5 h-3.5" />,
  payment_issue: <CreditCard className="w-3.5 h-3.5" />,
  system_crash: <ServerCrash className="w-3.5 h-3.5" />,
  authentication: <KeyRound className="w-3.5 h-3.5" />,
  functionality_broken: <CircleX className="w-3.5 h-3.5" />,
  performance: <Gauge className="w-3.5 h-3.5" />,
  usability: <MousePointerClick className="w-3.5 h-3.5" />,
  compatibility: <Laptop className="w-3.5 h-3.5" />,
  missing_feature: <PackageX className="w-3.5 h-3.5" />,
  documentation: <FileQuestion className="w-3.5 h-3.5" />,
  cosmetic: <Paintbrush className="w-3.5 h-3.5" />,
};

function getCategoryIcon(category: string) {
  return iconMap[category] || <AlertTriangle className="w-3.5 h-3.5" />;
}

export function PainPointsListWidget({ categories }: PainPointsListWidgetProps) {
  const router = useRouter();
  const chartColor = 'var(--chart-1)';

  return (
    <div className="h-full flex flex-col">
      {categories.length > 0 && (
        <div className="flex justify-end mb-2">
          <Link
            href="/pain-points"
            className="flex items-center space-x-1 text-sm text-primary hover:text-primary/80 font-medium transition-colors group"
          >
            <span>View All</span>
            <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
          </Link>
        </div>
      )}
      {categories.length > 0 ? (
          <ul className="space-y-3">
            {categories.slice(0, 5).map((cat, index) => (
              <li
                key={index}
                className="group flex justify-between items-center p-4 rounded-xl transition-all duration-200 cursor-pointer border hover:scale-[1.02] hover:shadow-md"
                style={{
                  backgroundColor: 'color-mix(in oklch, var(--muted) 50%, transparent)',
                  borderColor: 'var(--border)',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = `color-mix(in oklch, ${chartColor} 15%, var(--muted))`;
                  e.currentTarget.style.borderColor = chartColor;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'color-mix(in oklch, var(--muted) 50%, transparent)';
                  e.currentTarget.style.borderColor = 'var(--border)';
                }}
                onClick={() => router.push('/pain-points')}
              >
                <div className="flex items-center gap-3">
                  <span style={{ color: chartColor }}>
                    {getCategoryIcon(cat.category)}
                  </span>
                  <span className="text-foreground font-medium text-sm">
                    {getPainPointLabel(cat.category)}
                  </span>
                </div>
                <span
                  className="px-3 py-1.5 text-sm font-bold rounded-lg font-mono transition-colors ml-3 flex-shrink-0"
                  style={{
                    backgroundColor: 'color-mix(in oklch, var(--chart-1) 20%, transparent)',
                    color: 'var(--chart-1)',
                  }}
                >
                  {cat.count}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-center py-12 text-muted-foreground">
            <AlertTriangle className="w-12 h-12 mx-auto mb-3 opacity-20" />
            <p className="text-sm">No pain points identified yet</p>
          </div>
      )}
    </div>
  );
}
