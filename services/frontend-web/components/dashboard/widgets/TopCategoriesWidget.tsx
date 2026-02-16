'use client';

import Link from 'next/link';
import { Tag } from 'lucide-react';
import { TopCategory } from '@/lib/api/dashboard';

interface TopCategoriesWidgetProps {
  categories: TopCategory[];
}

const chartColors = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
  'var(--chart-6)',
  'var(--chart-7)',
  'var(--chart-8)',
  'var(--chart-9)',
  'var(--chart-10)',
];

const displayNames: Record<string, string> = {
  bug: 'Bug',
  performance: 'Performance',
  'ui-ux': 'UI/UX',
  'feature-request': 'Feature Request',
  mobile: 'Mobile',
  web: 'Web',
  security: 'Security',
  pricing: 'Pricing',
  support: 'Support',
  documentation: 'Documentation',
  integration: 'Integration',
  data: 'Data',
  notification: 'Notification',
  search: 'Search',
  accessibility: 'Accessibility',
};

function getDisplayName(tag: string): string {
  return displayNames[tag] || tag;
}

export function TopCategoriesWidget({ categories }: TopCategoriesWidgetProps) {
  return categories.length > 0 ? (
    <div
      className="grid gap-3"
      style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))' }}
    >
            {categories.map((category, index) => {
              const color = chartColors[index % chartColors.length];

              return (
                <Link
                  key={category.tag}
                  href={`/categories/${category.tag}`}
                  className="group relative p-4 rounded-2xl surface-raised border-2 border-border hover:shadow-md hover:scale-[1.02] transition-all duration-200 cursor-pointer block overflow-hidden"
                  style={{ '--category-color': color } as React.CSSProperties}
                >
                  <div
                    className="absolute inset-0 opacity-0 group-hover:opacity-10 transition-opacity"
                    style={{ backgroundColor: color }}
                  />
                  <div
                    className="absolute top-0 left-0 right-0 h-1 rounded-t-2xl"
                    style={{ backgroundColor: color }}
                  />
                  <div className="relative">
                    <div
                      className="text-3xl font-bold mb-1 font-mono"
                      style={{ color }}
                    >
                      {category.count}
                    </div>
                    <div className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                      {getDisplayName(category.tag)}
                    </div>
                  </div>
                </Link>
              );
            })}
    </div>
  ) : (
    <div className="text-center py-12 text-muted-foreground">
      <Tag className="w-12 h-12 mx-auto mb-3 opacity-20" />
      <p className="text-sm">No categories found yet</p>
    </div>
  );
}
