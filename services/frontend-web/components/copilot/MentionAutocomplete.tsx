'use client';

import { useEffect, useRef } from 'react';
import { AtSign } from 'lucide-react';
import { SCOPE_OPTIONS, type ContextScope } from './ContextScopeSelector';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface MentionMatch {
  prefix: string;   // e.g. '@customer:' or '@' for bare scope trigger
  query: string;    // text after the prefix
}

export interface MentionOption {
  label: string;
  value: string;
  /** If set, this option represents a scope chip rather than inline text */
  scope?: ContextScope;
  /** Color class for scope chips in the dropdown */
  color?: string;
}

// ─── Period presets ───────────────────────────────────────────────────────────

const PERIOD_PRESETS: MentionOption[] = [
  { label: 'last-7-days', value: '@period:last-7-days' },
  { label: 'last-30-days', value: '@period:last-30-days' },
  { label: 'this-month', value: '@period:this-month' },
  { label: 'this-quarter', value: '@period:this-quarter' },
];

// ─── Scope options (derived from SCOPE_OPTIONS) ─────────────────────────────

const SCOPE_MENTION_OPTIONS: MentionOption[] = SCOPE_OPTIONS.map((opt) => ({
  label: opt.label,
  value: `@scope:${opt.value}`,
  scope: opt.value,
  color: opt.color,
}));

// ─── Detector ────────────────────────────────────────────────────────────────

const MENTION_PATTERNS = [
  { pattern: /\@customer:(\S*)$/, prefix: '@customer:' },
  { pattern: /\@feedback:#?(\S*)$/, prefix: '@feedback:#' },
  { pattern: /\@tag:(\S*)$/, prefix: '@tag:' },
  { pattern: /\@period:(\S*)$/, prefix: '@period:' },
];

/** Bare `@` pattern — matches `@` at end of text (optionally followed by partial scope text) */
const BARE_AT_PATTERN = /(?:^|[\s])@(\S*)$/;

export function detectMention(text: string): MentionMatch | null {
  // Check specific mention patterns first (higher priority)
  for (const { pattern, prefix } of MENTION_PATTERNS) {
    const match = text.match(pattern);
    if (match) {
      return { prefix, query: match[1] ?? '' };
    }
  }
  // Then check for bare @ (scope trigger)
  const bareMatch = text.match(BARE_AT_PATTERN);
  if (bareMatch) {
    return { prefix: '@', query: bareMatch[1] ?? '' };
  }
  return null;
}

export function getMentionOptions(match: MentionMatch, selectedScopes?: ContextScope[]): MentionOption[] {
  // Bare @ — show scope options
  if (match.prefix === '@') {
    const selected = new Set(selectedScopes ?? []);
    return SCOPE_MENTION_OPTIONS
      .filter((opt) => !selected.has(opt.scope!))
      .filter((opt) => opt.label.toLowerCase().startsWith(match.query.toLowerCase()));
  }

  if (match.prefix === '@period:') {
    return PERIOD_PRESETS.filter((p) =>
      p.label.startsWith(match.query)
    );
  }
  // For @customer:, @feedback:, @tag: — return static placeholders
  // (in a real app these would be fetched from the API)
  if (match.prefix === '@customer:') {
    return [
      { label: 'acme@example.com', value: `@customer:acme@example.com` },
      { label: 'beta@example.com', value: `@customer:beta@example.com` },
    ].filter((o) => o.label.startsWith(match.query));
  }
  if (match.prefix === '@tag:') {
    return [
      { label: 'billing', value: '@tag:billing' },
      { label: 'onboarding', value: '@tag:onboarding' },
      { label: 'performance', value: '@tag:performance' },
    ].filter((o) => o.label.startsWith(match.query));
  }
  return [];
}

/** Check if a mention option is a scope chip (vs inline text mention) */
export function isScopeOption(value: string): boolean {
  return value.startsWith('@scope:');
}

/** Extract the ContextScope value from a scope option value */
export function extractScope(value: string): ContextScope | null {
  if (!value.startsWith('@scope:')) return null;
  return value.replace('@scope:', '') as ContextScope;
}

// ─── Component ────────────────────────────────────────────────────────────────

interface MentionAutocompleteProps {
  match: MentionMatch;
  onSelect: (value: string) => void;
  onClose: () => void;
  selectedScopes?: ContextScope[];
}

export function MentionAutocomplete({ match, onSelect, onClose, selectedScopes }: MentionAutocompleteProps) {
  const options = getMentionOptions(match, selectedScopes);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  if (options.length === 0) return null;

  const isScopeDropdown = match.prefix === '@';

  return (
    <div
      ref={containerRef}
      data-testid="mention-autocomplete"
      className="absolute bottom-full mb-1 left-0 w-64 bg-background border border-border rounded-xl shadow-xl py-1 z-30 overflow-hidden"
    >
      <div className="px-3 py-1.5 flex items-center gap-1.5 border-b border-border">
        <AtSign className="w-3 h-3 text-muted-foreground" />
        <span className="text-xs text-muted-foreground font-medium">
          {isScopeDropdown ? 'Add scope filter' : match.prefix}
        </span>
      </div>
      {options.map((opt) => (
        <button
          key={opt.value}
          data-testid={`mention-option-${opt.value}`}
          onClick={() => onSelect(opt.value)}
          className="w-full text-left px-3 py-2 text-sm hover:bg-muted transition-colors"
        >
          {opt.color ? (
            <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${opt.color}`}>
              {opt.label}
            </span>
          ) : (
            opt.label
          )}
        </button>
      ))}
    </div>
  );
}
