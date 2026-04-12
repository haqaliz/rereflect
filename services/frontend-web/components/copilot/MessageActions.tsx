'use client';

import { useState } from 'react';
import { Copy, Check, RefreshCw, Square, ThumbsUp, ThumbsDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import { aiCorrectionsAPI } from '@/lib/api/ai-corrections';

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

// ─── Thumbs rating + optional feedback (for AI messages) ─────────────────────

interface ThumbsRatingProps {
  messageId: number | string;
  content: string;
}

export function ThumbsRating({ messageId, content }: ThumbsRatingProps) {
  const [voted, setVoted] = useState<'up' | 'down' | null>(null);
  const [showInput, setShowInput] = useState(false);
  const [feedbackText, setFeedbackText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleThumbsUp = async () => {
    if (voted !== null) return;
    setVoted('up');
    try {
      await aiCorrectionsAPI.submit({
        correction_type: 'copilot_response',
        entity_type: 'conversation_message',
        entity_id: typeof messageId === 'number' ? messageId : null,
        signal: 'thumbs_up',
        original_value: content,
      });
    } catch {
      // silently ignore — UI already reflects the vote
    }
  };

  const handleThumbsDown = () => {
    if (voted !== null) return;
    setVoted('down');
    setShowInput(true);
  };

  const handleSubmitFeedback = async () => {
    setSubmitting(true);
    try {
      await aiCorrectionsAPI.submit({
        correction_type: 'copilot_response',
        entity_type: 'conversation_message',
        entity_id: typeof messageId === 'number' ? messageId : null,
        signal: 'thumbs_down',
        original_value: content,
        feedback_text: feedbackText || null,
      });
      setShowInput(false);
      toast.success('Feedback submitted');
    } catch {
      toast.error('Failed to submit feedback');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      {/* Thumbs up */}
      <button
        data-testid={`thumbs-up-btn-${messageId}`}
        onClick={handleThumbsUp}
        disabled={voted !== null}
        title="Good response"
        className={`p-1.5 rounded-lg transition-colors ${
          voted === 'up'
            ? 'text-green-500 bg-green-50 dark:bg-green-950/30'
            : 'text-muted-foreground hover:text-foreground hover:bg-muted'
        } disabled:cursor-not-allowed`}
      >
        <ThumbsUp className="w-3.5 h-3.5" />
      </button>

      {/* Thumbs down */}
      <button
        data-testid={`thumbs-down-btn-${messageId}`}
        onClick={handleThumbsDown}
        disabled={voted !== null}
        title="Bad response"
        className={`p-1.5 rounded-lg transition-colors ${
          voted === 'down'
            ? 'text-red-500 bg-red-50 dark:bg-red-950/30'
            : 'text-muted-foreground hover:text-foreground hover:bg-muted'
        } disabled:cursor-not-allowed`}
      >
        <ThumbsDown className="w-3.5 h-3.5" />
      </button>

      {/* Thumbs-down feedback dialog */}
      <Dialog open={showInput} onOpenChange={(open) => { if (!open) { setShowInput(false); handleSubmitFeedback(); } }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>What went wrong?</DialogTitle>
            <DialogDescription>
              Help us improve by describing what was wrong with this response. This is optional — you can also submit without a message.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            data-testid={`correction-feedback-input-${messageId}`}
            placeholder="e.g., The data was inaccurate, the tone was off, it missed the point..."
            value={feedbackText}
            onChange={(e) => setFeedbackText(e.target.value)}
            rows={3}
          />
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => { setShowInput(false); handleSubmitFeedback(); }}
              disabled={submitting}
            >
              Skip
            </Button>
            <Button
              size="sm"
              data-testid={`correction-submit-btn-${messageId}`}
              onClick={() => { setShowInput(false); handleSubmitFeedback(); }}
              disabled={submitting}
            >
              {submitting ? 'Submitting...' : 'Submit Feedback'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
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

      {/* Thumbs rating */}
      <ThumbsRating messageId={messageId} content={content} />
    </div>
  );
}
