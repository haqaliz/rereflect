'use client';

import { Sparkles } from 'lucide-react';
import { useCommandBar } from './CommandBarContext';

export function CopilotHeaderButton() {
  const { setOpen } = useCommandBar();

  return (
    <button
      onClick={() => setOpen(true)}
      title="AI Copilot (Cmd+K)"
      aria-label="Open AI Copilot"
      className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors border border-border"
    >
      <Sparkles className="w-4 h-4" />
      <span className="hidden sm:inline">Ask AI</span>
      <kbd className="hidden sm:inline text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground border border-border font-mono">
        ⌘K
      </kbd>
    </button>
  );
}
