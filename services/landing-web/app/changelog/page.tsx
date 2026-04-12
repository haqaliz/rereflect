'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { Logo } from '@rereflect/ui';
import { ArrowLeft, AlertTriangle, Loader2, Sparkles, Wrench, Settings, RefreshCw } from 'lucide-react';
import { Footer } from '@/components/landing/Footer';
import { getPublicChangelog, type ChangelogEntry } from '@/lib/changelog-api';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@rereflect/ui';

const ENTRY_TYPES = [
  { value: '', label: 'All' },
  { value: 'feature', label: 'Feature' },
  { value: 'fix', label: 'Fix' },
  { value: 'improvement', label: 'Improvement' },
  { value: 'breaking_change', label: 'Breaking Change' },
  { value: 'chore', label: 'Chore' },
] as const;

const DATE_RANGES = [
  { value: 0, label: 'All time' },
  { value: 7, label: 'Last 7 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 90, label: 'Last 90 days' },
] as const;

const BADGE_STYLES: Record<string, string> = {
  feature: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
  fix: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  improvement: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  breaking_change: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  chore: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300',
  refactor: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
};

const BADGE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  feature: Sparkles,
  fix: Wrench,
  improvement: RefreshCw,
  chore: Settings,
  refactor: RefreshCw,
};

const TYPE_LABELS: Record<string, string> = {
  feature: 'Feature',
  fix: 'Fix',
  improvement: 'Improvement',
  breaking_change: 'Breaking Change',
  chore: 'Chore',
  refactor: 'Refactor',
};

const PAGE_SIZE = 20;

export default function ChangelogPage() {
  const [entries, setEntries] = useState<ChangelogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [selectedType, setSelectedType] = useState('');
  const [selectedDays, setSelectedDays] = useState(0);

  const fetchEntries = useCallback(async (offset = 0, append = false) => {
    try {
      if (offset === 0) setIsLoading(true);
      else setIsLoadingMore(true);

      const data = await getPublicChangelog({
        entry_type: selectedType || undefined,
        days: selectedDays || undefined,
        offset,
        limit: PAGE_SIZE,
      });

      if (append) {
        setEntries(prev => [...prev, ...data.items]);
      } else {
        setEntries(data.items);
      }
      setTotal(data.total);
      setHasMore(data.has_more);
    } catch {
      // Silently handle errors for public page
    } finally {
      setIsLoading(false);
      setIsLoadingMore(false);
    }
  }, [selectedType, selectedDays]);

  useEffect(() => {
    fetchEntries(0, false);
  }, [fetchEntries]);

  const handleLoadMore = () => {
    fetchEntries(entries.length, true);
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  /** Strip conventional commit prefix (e.g. "feat: ", "fix: ") from a title string */
  const stripPrefix = (text: string) => {
    return text.replace(/^(feat|fix|chore|refactor|improvement|perf|docs|style|test|ci|build)(\(.+?\))?:\s*/i, '');
  };

  /** Filter out Co-Authored-By and empty lines from description */
  const parseDescription = (desc: string | null): string[] => {
    if (!desc) return [];
    return desc
      .split('\n')
      .filter(line => !line.trim().toLowerCase().startsWith('co-authored-by:'))
      .filter(line => line.trim().length > 0);
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Navigation */}
      <nav className="relative z-50 px-6 py-5 border-b border-border">
        <div className="max-w-4xl mx-auto flex justify-between items-center">
          <Link href="/" className="flex items-center gap-3 group">
            <Logo size="lg" className="relative" />
            <span className="text-xl font-bold tracking-tight">
              <span className="text-muted-foreground">Re</span>
              <span className="text-foreground">reflect</span>
            </span>
          </Link>
          <Link href="/" className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft className="w-4 h-4" />
            Back to Home
          </Link>
        </div>
      </nav>

      {/* Content */}
      <main className="max-w-4xl mx-auto px-6 py-16">
        <h1 className="text-4xl font-bold text-foreground mb-2">Changelog</h1>
        <p className="text-muted-foreground mb-8">All the latest updates, improvements, and fixes.</p>

        {/* Filters */}
        <div className="flex flex-col sm:flex-row gap-4 mb-8">
          {/* Type filter pills */}
          <div className="flex flex-wrap gap-2">
            {ENTRY_TYPES.map(type => (
              <button
                key={type.value}
                onClick={() => setSelectedType(type.value)}
                className={`px-3 py-1.5 text-sm rounded-full border transition-colors ${
                  selectedType === type.value
                    ? 'bg-foreground text-background border-foreground'
                    : 'bg-background text-muted-foreground border-border hover:border-foreground/50'
                }`}
              >
                {type.label}
              </button>
            ))}
          </div>

          {/* Date range dropdown */}
          <Select
            value={String(selectedDays)}
            onValueChange={(value) => setSelectedDays(Number(value))}
          >
            <SelectTrigger className="w-[140px] sm:ml-auto">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DATE_RANGES.map(range => (
                <SelectItem key={range.value} value={String(range.value)}>{range.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Entry list */}
        {isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : entries.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            No changelog entries found.
          </div>
        ) : (
          <div className="space-y-6">
            {entries.map(entry => {
              const BadgeIcon = BADGE_ICONS[entry.entry_type];
              const descriptionLines = parseDescription(entry.description);

              return (
                <div key={entry.id} className="border-b border-border pb-6 last:border-b-0">
                  <div className="flex items-center gap-3 mb-2">
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-medium rounded-full ${BADGE_STYLES[entry.entry_type] || BADGE_STYLES.chore}`}>
                      {entry.is_breaking ? (
                        <AlertTriangle className="w-3 h-3" />
                      ) : BadgeIcon ? (
                        <BadgeIcon className="w-3 h-3" />
                      ) : null}
                      {TYPE_LABELS[entry.entry_type] || entry.entry_type}
                    </span>
                    <span className="text-sm text-muted-foreground">
                      {formatDate(entry.committed_at)}
                    </span>
                  </div>
                  <h3 className="text-lg font-semibold text-foreground">{stripPrefix(entry.title)}</h3>
                  {descriptionLines.length > 0 && (
                    <div className="mt-2 space-y-1.5">
                      {(() => {
                        const elements: React.ReactNode[] = [];
                        let bulletBuffer: string[] = [];

                        const flushBullets = () => {
                          if (bulletBuffer.length > 0) {
                            elements.push(
                              <ul key={`ul-${elements.length}`} className="list-disc list-inside space-y-1 text-sm text-muted-foreground ml-1">
                                {bulletBuffer.map((item, j) => (
                                  <li key={j} className="leading-relaxed">{item}</li>
                                ))}
                              </ul>
                            );
                            bulletBuffer = [];
                          }
                        };

                        descriptionLines.forEach((line, i) => {
                          const bulletMatch = line.match(/^[-*]\s+(.+)/);
                          if (bulletMatch) {
                            bulletBuffer.push(bulletMatch[1]);
                          } else {
                            flushBullets();
                            elements.push(
                              <p key={`p-${i}`} className="text-sm text-muted-foreground leading-relaxed font-medium">{line}</p>
                            );
                          }
                        });
                        flushBullets();
                        return elements;
                      })()}
                    </div>
                  )}
                </div>
              );
            })}

            {/* Load more */}
            {hasMore && (
              <div className="flex justify-center pt-4">
                <button
                  onClick={handleLoadMore}
                  disabled={isLoadingMore}
                  className="px-6 py-2 text-sm font-medium rounded-md border border-border bg-background text-foreground hover:bg-muted transition-colors disabled:opacity-50"
                >
                  {isLoadingMore ? (
                    <span className="flex items-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Loading...
                    </span>
                  ) : (
                    `Load more (${total - entries.length} remaining)`
                  )}
                </button>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Footer */}
      <Footer />
    </div>
  );
}
