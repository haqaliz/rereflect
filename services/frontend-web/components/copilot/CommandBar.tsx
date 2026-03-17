'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Sparkles, Wand2, Loader2, FileBarChart, HeartPulse, Lightbulb, UserMinus } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { copilotAPI, CopilotUsage } from '@/lib/api/copilot';

interface CommandBarProps {
  open: boolean;
  onClose: () => void;
}

const STATIC_TEMPLATES = [
  "This week's feedback summary",
  'Top pain points this month',
  'Most requested features',
  'Urgent feedback that needs attention',
  'Top churn risks right now',
  'Healthiest customers',
  'Customers with declining health scores',
  'Sentiment trends over the last 30 days',
];

const REPORT_TEMPLATES = [
  { label: 'Executive summary this month', icon: FileBarChart },
  { label: 'Customer health report', icon: HeartPulse },
  { label: 'Feature request priorities', icon: Lightbulb },
  { label: 'Churn risk analysis', icon: UserMinus },
];

export function CommandBar({ open, onClose }: CommandBarProps) {
  const router = useRouter();
  const { user } = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState('');
  const [highlightedIndex, setHighlightedIndex] = useState<number>(-1);
  const [dynamicSuggestions, setDynamicSuggestions] = useState<string[]>([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [usage, setUsage] = useState<CopilotUsage | null>(null);

  // All chips: static templates + report templates + dynamic suggestions
  const reportTemplateLabels = REPORT_TEMPLATES.map((t) => t.label);
  const allChips = [...STATIC_TEMPLATES, ...reportTemplateLabels, ...dynamicSuggestions];

  const limitReached =
    usage !== null &&
    usage.daily_limit !== null &&
    usage.queries_today >= usage.daily_limit;

  const isFreePlan = user?.plan === 'free';
  const showRemainingCount =
    isFreePlan && usage !== null && usage.daily_limit !== null && !limitReached;

  // Navigate to conversations with the query
  const navigate = useCallback(
    (q: string) => {
      const trimmed = q.trim();
      if (!trimmed) return;
      onClose();
      router.push(`/conversations?new=true&q=${encodeURIComponent(trimmed)}`);
    },
    [router, onClose]
  );

  // Auto-focus input when modal opens
  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
      setQuery('');
      setHighlightedIndex(-1);
      setDynamicSuggestions([]);
    }
  }, [open]);

  // Fetch usage when modal opens (for plan gating display)
  useEffect(() => {
    if (!open) return;
    copilotAPI
      .getCopilotUsage()
      .then(setUsage)
      .catch(() => {}); // silent — gating is optional UI sugar
  }, [open]);

  // Global Escape key handler
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightedIndex((prev) => (prev + 1) % allChips.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightedIndex((prev) =>
        prev <= 0 ? allChips.length - 1 : prev - 1
      );
    } else if (e.key === 'Enter') {
      if (highlightedIndex >= 0 && highlightedIndex < allChips.length) {
        navigate(allChips[highlightedIndex]);
      } else {
        navigate(query);
      }
    }
  };

  const handleSuggestQueries = async () => {
    setLoadingSuggestions(true);
    try {
      const res = await copilotAPI.getSuggestions();
      setDynamicSuggestions(res.suggestions);
    } catch {
      // silently fail
    } finally {
      setLoadingSuggestions(false);
    }
  };

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    // Only close if click is directly on the backdrop (not bubbling from modal)
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  const handleModalClick = (e: React.MouseEvent<HTMLDivElement>) => {
    e.stopPropagation();
  };

  if (!open) return null;

  const remainingCount =
    usage?.daily_limit != null ? usage.daily_limit - usage.queries_today : 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      data-testid="command-bar-backdrop"
      onClick={handleBackdropClick}
    >
      <div
        className="relative w-full max-w-xl mx-4 bg-background border border-border rounded-2xl shadow-2xl overflow-hidden"
        data-testid="command-bar-modal"
        onClick={handleModalClick}
      >
        {/* Input area */}
        <div className="flex items-center gap-3 px-4 py-4 border-b border-border">
          <Sparkles className="w-5 h-5 text-primary shrink-0" />
          <input
            ref={inputRef}
            type="text"
            placeholder="Ask anything about your feedback..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleInputKeyDown}
            disabled={limitReached}
            className="flex-1 bg-transparent text-foreground placeholder:text-muted-foreground outline-none text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          />
        </div>

        {/* Plan gating: upgrade CTA when limit reached */}
        {limitReached && (
          <div
            data-testid="upgrade-cta"
            className="px-4 py-3 bg-destructive/10 border-b border-border"
          >
            <p className="text-sm text-destructive font-medium">
              You&apos;ve used your daily query allowance.{' '}
              <button
                onClick={() => router.push('/settings/billing')}
                className="underline hover:no-underline"
              >
                Upgrade to Pro
              </button>{' '}
              for unlimited queries.
            </p>
          </div>
        )}

        {/* Remaining count for free users under limit */}
        {showRemainingCount && (
          <div className="px-4 py-2 border-b border-border flex justify-end">
            <span data-testid="queries-remaining" className="text-xs text-muted-foreground">
              {remainingCount}/{usage!.daily_limit} remaining today
            </span>
          </div>
        )}

        {/* Template chips */}
        <div className="px-4 py-3 flex flex-col gap-1">
          {STATIC_TEMPLATES.map((template, index) => (
            <button
              key={template}
              data-testid={`template-chip-${index}`}
              data-highlighted={highlightedIndex === index ? 'true' : undefined}
              className={`text-left text-sm px-3 py-2 rounded-lg transition-colors ${
                highlightedIndex === index
                  ? 'bg-primary/10 text-primary highlighted'
                  : 'text-foreground hover:bg-muted'
              }`}
              onClick={() => navigate(template)}
            >
              {template}
            </button>
          ))}

          {/* Report template chips */}
          {REPORT_TEMPLATES.map((template, i) => {
            const index = STATIC_TEMPLATES.length + i;
            const Icon = template.icon;
            return (
              <button
                key={template.label}
                data-testid={`template-chip-${index}`}
                data-highlighted={highlightedIndex === index ? 'true' : undefined}
                className={`text-left text-sm px-3 py-2 rounded-lg transition-colors flex items-center gap-2 ${
                  highlightedIndex === index
                    ? 'bg-primary/10 text-primary highlighted'
                    : 'text-foreground hover:bg-muted'
                }`}
                onClick={() => navigate(template.label)}
              >
                <Icon className="w-3.5 h-3.5 shrink-0 text-muted-foreground" />
                {template.label}
              </button>
            );
          })}

          {/* Dynamic suggestions */}
          {dynamicSuggestions.map((suggestion, i) => {
            const index = STATIC_TEMPLATES.length + REPORT_TEMPLATES.length + i;
            return (
              <button
                key={suggestion}
                data-testid={`template-chip-${index}`}
                data-highlighted={highlightedIndex === index ? 'true' : undefined}
                className={`text-left text-sm px-3 py-2 rounded-lg transition-colors ${
                  highlightedIndex === index
                    ? 'bg-primary/10 text-primary highlighted'
                    : 'text-foreground hover:bg-muted'
                }`}
                onClick={() => navigate(suggestion)}
              >
                {suggestion}
              </button>
            );
          })}
        </div>

        {/* Footer: Suggest queries button */}
        <div className="px-4 pb-4 pt-1 border-t border-border">
          {loadingSuggestions ? (
            <div data-testid="suggestions-loading" className="flex items-center gap-2 text-sm text-muted-foreground py-1">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Generating suggestions...</span>
            </div>
          ) : (
            <button
              onClick={handleSuggestQueries}
              className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors py-1"
            >
              <Wand2 className="w-4 h-4" />
              <span>Suggest queries for me</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
