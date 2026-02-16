'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  Lightbulb,
  ArrowRight,
  Boxes,
  Workflow,
  Plug,
  BarChart3,
  Settings2,
  Users,
  ArrowUpDown,
  Smartphone,
  Bell,
  Palette,
} from 'lucide-react';
import { CategoryCount } from '@/lib/api/dashboard';
import { getFeatureRequestLabel } from '@/lib/category-utils';

interface FeatureRequestsWidgetProps {
  categories: CategoryCount[];
}

const iconMap: Record<string, React.ReactNode> = {
  core_functionality: <Boxes className="w-3.5 h-3.5" />,
  automation: <Workflow className="w-3.5 h-3.5" />,
  integration: <Plug className="w-3.5 h-3.5" />,
  reporting: <BarChart3 className="w-3.5 h-3.5" />,
  customization: <Settings2 className="w-3.5 h-3.5" />,
  collaboration: <Users className="w-3.5 h-3.5" />,
  export_import: <ArrowUpDown className="w-3.5 h-3.5" />,
  mobile: <Smartphone className="w-3.5 h-3.5" />,
  notifications: <Bell className="w-3.5 h-3.5" />,
  ui_enhancement: <Palette className="w-3.5 h-3.5" />,
};

function getCategoryIcon(category: string) {
  return iconMap[category] || <Lightbulb className="w-3.5 h-3.5" />;
}

export function FeatureRequestsWidget({ categories }: FeatureRequestsWidgetProps) {
  const router = useRouter();
  const chartColor = 'var(--chart-2)';

  return (
    <div className="h-full flex flex-col">
      {categories.length > 0 && (
        <div className="flex justify-end mb-2">
          <Link
            href="/feature-requests"
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
                onClick={() => router.push('/feature-requests')}
              >
                <div className="flex items-center gap-3">
                  <span style={{ color: chartColor }}>
                    {getCategoryIcon(cat.category)}
                  </span>
                  <span className="text-foreground font-medium text-sm">
                    {getFeatureRequestLabel(cat.category)}
                  </span>
                </div>
                <span
                  className="px-3 py-1.5 text-sm font-bold rounded-lg font-mono transition-colors ml-3 flex-shrink-0"
                  style={{
                    backgroundColor: 'color-mix(in oklch, var(--chart-2) 20%, transparent)',
                    color: 'var(--chart-2)',
                  }}
                >
                  {cat.count}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-center py-12 text-muted-foreground">
            <Lightbulb className="w-12 h-12 mx-auto mb-3 opacity-20" />
            <p className="text-sm">No feature requests identified yet</p>
          </div>
      )}
    </div>
  );
}
