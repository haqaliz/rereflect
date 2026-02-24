'use client';

import { useState } from 'react';
import { Copy, Check, RefreshCw, Square } from 'lucide-react';
import { toast } from 'sonner';

// ─── Stop button (during streaming) ──────────────────────────────────────────

interface StopButtonProps {
  onStop: () => void;
}

export function StopButton({ onStop }: StopButtonProps) {
  return (
    <button
      data-testid="stop-generating-btn"
      onClick={onStop}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
    >
      <Square className="w-3 h-3 fill-current" />
      Stop generating
    </button>
  );
}

// ─── Message action buttons (after completion) ────────────────────────────────

interface MessageActionsProps {
  messageId: number | string;
  content: string;
  onRegenerate?: (messageId: number | string) => void;
}

export function MessageActions({ messageId, content, onRegenerate }: MessageActionsProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Failed to copy');
    }
  };

  return (
    <div className="flex items-center gap-1 mt-2">
      {/* Copy */}
      <button
        data-testid={`copy-btn-${messageId}`}
        onClick={handleCopy}
        title="Copy response"
        className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
      >
        {copied ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
      </button>

      {/* Regenerate */}
      {onRegenerate && (
        <button
          data-testid={`regenerate-btn-${messageId}`}
          onClick={() => onRegenerate(messageId)}
          title="Regenerate response"
          className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}
