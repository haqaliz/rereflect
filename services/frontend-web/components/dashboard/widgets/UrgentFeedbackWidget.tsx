'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  CircleAlert,
  AlertTriangle,
  ArrowRight,
  Siren,
  ShieldAlert,
  CreditCard,
  Database,
  Lock,
  Bug,
  Receipt,
  UserX,
  Shield,
  Star,
} from 'lucide-react';
import { CategoryCount } from '@/lib/api/dashboard';
import { getUrgentLabel } from '@/lib/category-utils';

interface UrgentFeedbackWidgetProps {
  categories: CategoryCount[];
}

const iconMap: Record<string, React.ReactNode> = {
  service_outage: <Siren className="w-3.5 h-3.5" />,
  data_breach: <ShieldAlert className="w-3.5 h-3.5" />,
  payment_failure: <CreditCard className="w-3.5 h-3.5" />,
  data_corruption: <Database className="w-3.5 h-3.5" />,
  account_locked: <Lock className="w-3.5 h-3.5" />,
  critical_bug: <Bug className="w-3.5 h-3.5" />,
  billing_dispute: <Receipt className="w-3.5 h-3.5" />,
  churn_risk: <UserX className="w-3.5 h-3.5" />,
  compliance: <Shield className="w-3.5 h-3.5" />,
  reputation_risk: <Star className="w-3.5 h-3.5" />,
};

function getCategoryIcon(category: string) {
  return iconMap[category] || <CircleAlert className="w-3.5 h-3.5" />;
}

export function UrgentFeedbackWidget({ categories }: UrgentFeedbackWidgetProps) {
  const router = useRouter();
  const chartColor = 'var(--destructive)';

  return (
    <div className="h-full flex flex-col">
      {categories.length > 0 && (
        <div className="flex justify-end mb-2">
          <Link
            href="/urgent-feedbacks"
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
                onClick={() => router.push('/urgent-feedbacks')}
              >
                <div className="flex items-center gap-3">
                  <span style={{ color: chartColor }}>
                    {getCategoryIcon(cat.category)}
                  </span>
                  <span className="text-foreground font-medium text-sm">
                    {getUrgentLabel(cat.category)}
                  </span>
                </div>
                <span
                  className="px-3 py-1.5 text-sm font-bold rounded-lg font-mono transition-colors ml-3 flex-shrink-0"
                  style={{
                    backgroundColor: 'color-mix(in oklch, var(--destructive) 20%, transparent)',
                    color: 'var(--destructive)',
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
            <p className="text-sm">No urgent feedback at the moment</p>
            <p className="text-xs mt-1">Great job keeping up!</p>
          </div>
      )}
    </div>
  );
}
