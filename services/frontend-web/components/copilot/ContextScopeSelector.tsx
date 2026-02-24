'use client';

import { useState } from 'react';
import { ChevronDown } from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

export type ContextScope =
  | 'all_data'
  | 'feedbacks'
  | 'customers'
  | 'pain_points'
  | 'feature_requests'
  | 'dashboard';

export interface ScopeOption {
  value: ContextScope;
  label: string;
  color: string;
}

export const SCOPE_OPTIONS: ScopeOption[] = [
  { value: 'all_data', label: 'All Data', color: 'bg-primary/15 text-primary' },
  { value: 'feedbacks', label: 'Feedbacks', color: 'bg-blue-500/15 text-blue-600 dark:text-blue-400' },
  { value: 'customers', label: 'Customers', color: 'bg-purple-500/15 text-purple-600 dark:text-purple-400' },
  { value: 'pain_points', label: 'Pain Points', color: 'bg-orange-500/15 text-orange-600 dark:text-orange-400' },
  { value: 'feature_requests', label: 'Feature Requests', color: 'bg-green-500/15 text-green-600 dark:text-green-400' },
  { value: 'dashboard', label: 'Dashboard', color: 'bg-cyan-500/15 text-cyan-600 dark:text-cyan-400' },
];

// ─── Component ────────────────────────────────────────────────────────────────

interface ContextScopeSelectorProps {
  value: ContextScope;
  onChange: (scope: ContextScope) => void;
  /** Where the dropdown opens relative to the trigger. Default: 'below' */
  position?: 'below' | 'above';
}

export function ContextScopeSelector({ value, onChange, position = 'below' }: ContextScopeSelectorProps) {
  const [open, setOpen] = useState(false);
  const current = SCOPE_OPTIONS.find((o) => o.value === value) ?? SCOPE_OPTIONS[0];

  return (
    <div className="relative">
      <button
        data-testid="context-scope-selector"
        onClick={() => setOpen((o) => !o)}
        className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-colors ${current.color} hover:opacity-80`}
      >
        {current.label}
        <ChevronDown className="w-3 h-3" />
      </button>

      {open && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-10"
            onClick={() => setOpen(false)}
          />
          {/* Dropdown */}
          <div className={`absolute left-0 z-20 w-44 bg-background border border-border rounded-xl shadow-lg py-1 overflow-hidden ${position === 'above' ? 'bottom-8' : 'top-8'}`}>
            {SCOPE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                data-testid={`scope-option-${opt.value}`}
                onClick={() => {
                  onChange(opt.value);
                  setOpen(false);
                }}
                className={`w-full text-left px-3 py-2 text-xs font-medium transition-colors hover:bg-muted ${
                  opt.value === value ? 'opacity-100' : 'opacity-70'
                }`}
              >
                <span className={`inline-block px-2 py-0.5 rounded-full ${opt.color}`}>
                  {opt.label}
                </span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
