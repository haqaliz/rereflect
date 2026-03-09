'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Sparkles,
  Loader2,
  Copy,
  Send,
  ChevronDown,
  ClipboardList,
  Zap,
  ArrowRight,
} from 'lucide-react';
import Link from 'next/link';
import {
  responsesAPI,
  TONE_OPTIONS,
  type ResponseTemplate,
  type ResponseUsage,
  type ToneOption,
} from '@/lib/api/responses';

// Defined locally so it's not affected by module mocks in tests
const MODAL_RESPONSE_VARIABLES = [
  { name: 'customer_name', description: 'Customer name from feedback metadata' },
  { name: 'customer_email', description: 'Customer email address' },
  { name: 'company_name', description: 'Customer company or org name' },
  { name: 'feedback_excerpt', description: 'First 200 characters of feedback text' },
  { name: 'category', description: 'AI-assigned category' },
  { name: 'sentiment', description: 'Sentiment label (Positive/Negative/Neutral)' },
  { name: 'source', description: 'Feedback source name' },
  { name: 'product_name', description: 'Product name from org settings' },
  { name: 'agent_name', description: "Current user's name" },
  { name: 'support_email', description: 'Support email from org settings' },
];
import { useAuth } from '@/contexts/AuthContext';
import { toast } from 'sonner';
import { TemplateBrowser } from './TemplateBrowser';

// ─── Types ────────────────────────────────────────────────────────────────────

interface FeedbackForModal {
  id: number;
  text: string;
  sentiment_label?: string | null;
  pain_point_category?: string | null;
  customer_email?: string | null;
  source?: string | null;
  source_metadata?: Record<string, any> | null;
}

export interface ResponseModalProps {
  open: boolean;
  onClose: () => void;
  feedback: FeedbackForModal;
  connectedChannels: Array<'slack' | 'intercom' | 'linear' | 'email'>;
  defaultTone?: ToneOption;
}

type ModalView = 'main' | 'browse';

// ─── Channel Labels ────────────────────────────────────────────────────────────

const CHANNEL_LABELS: Record<string, string> = {
  slack: 'Slack',
  intercom: 'Intercom',
  linear: 'Linear',
  email: 'Email',
};

// ─── Component ────────────────────────────────────────────────────────────────

export function ResponseModal({
  open,
  onClose,
  feedback,
  connectedChannels,
  defaultTone = 'professional',
}: ResponseModalProps) {
  const { user } = useAuth();

  const isFree = user?.plan === 'free';

  // ── State ──────────────────────────────────────────────────────────────────
  const [view, setView] = useState<ModalView>('main');
  const [suggestedTemplate, setSuggestedTemplate] = useState<ResponseTemplate | null>(null);
  const [tone, setTone] = useState<ToneOption>(defaultTone);
  const [responseText, setResponseText] = useState('');
  const [generating, setGenerating] = useState(false);
  const [sending, setSending] = useState(false);
  const [usage, setUsage] = useState<ResponseUsage | null>(null);
  const [showUsageCounter, setShowUsageCounter] = useState(false);
  const [currentUsed, setCurrentUsed] = useState<number | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // ── Effects ────────────────────────────────────────────────────────────────

  // Reset when modal opens
  useEffect(() => {
    if (open) {
      setView('main');
      setResponseText('');
      setSuggestedTemplate(null);
      setShowUsageCounter(false);
      setCurrentUsed(null);
      setTone(defaultTone);

      if (!isFree) {
        // Load template suggestion and usage in parallel
        responsesAPI.suggestTemplate(feedback.id)
          .then(result => {
            if (result.template && result.score >= 10) {
              setSuggestedTemplate(result.template);
            }
          })
          .catch(() => {});

        responsesAPI.getResponseUsage()
          .then(setUsage)
          .catch(() => {});
      }
    }
  }, [open, feedback.id, isFree, defaultTone]);

  // ── Handlers ──────────────────────────────────────────────────────────────

  const handleUseTemplate = useCallback((template: ResponseTemplate) => {
    setResponseText(template.body);
    setView('main');
  }, []);

  const handleGenerateAI = useCallback(async () => {
    setGenerating(true);
    try {
      const result = await responsesAPI.generateResponse(feedback.id, tone);
      setResponseText(result.response_text);

      // Update usage counter
      const newUsed = (usage?.ai_responses_generated ?? 0) + 1;
      setCurrentUsed(newUsed);
      setShowUsageCounter(true);

      if (usage) {
        setUsage({ ...usage, ai_responses_generated: newUsed });
      }
    } catch {
      toast.error('Failed to generate AI response. Please try again.');
    } finally {
      setGenerating(false);
    }
  }, [feedback.id, tone, usage]);

  const handleCopyToClipboard = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(responseText);

      // Save to timeline
      await responsesAPI.sendResponse(feedback.id, {
        response_text: responseText,
        channel: 'clipboard',
        source: 'manual',
        template_id: null,
        tone: null,
      });

      toast.success('Copied to clipboard');
      onClose();
    } catch {
      toast.error('Failed to copy to clipboard');
    }
  }, [responseText, feedback.id, onClose]);

  const handleSendVia = useCallback(async (channel: 'slack' | 'intercom' | 'linear' | 'email') => {
    setSending(true);
    try {
      const result = await responsesAPI.sendResponse(feedback.id, {
        response_text: responseText,
        channel,
        source: 'manual',
        template_id: null,
        tone: null,
      });

      if (result.success) {
        toast.success(`Sent via ${CHANNEL_LABELS[channel]}`);
        onClose();
      } else {
        toast.error(result.error ?? `Failed to send via ${CHANNEL_LABELS[channel]}`);
      }
    } catch {
      toast.error(`Failed to send via ${CHANNEL_LABELS[channel]}`);
    } finally {
      setSending(false);
    }
  }, [responseText, feedback.id, onClose]);

  const insertVariable = useCallback((varName: string) => {
    const el = textareaRef.current;
    if (!el) return;

    const start = el.selectionStart;
    const end = el.selectionEnd;
    const before = responseText.slice(0, start);
    const after = responseText.slice(end);
    const insertion = `{{${varName}}}`;
    const newText = before + insertion + after;

    setResponseText(newText);

    // Restore cursor position after React re-render
    requestAnimationFrame(() => {
      el.selectionStart = start + insertion.length;
      el.selectionEnd = start + insertion.length;
      el.focus();
    });
  }, [responseText]);

  // ── Monthly limit display ──────────────────────────────────────────────────

  const monthlyLimit = usage?.monthly_limit ?? 50;
  const usedCount = currentUsed ?? usage?.ai_responses_generated ?? 0;

  // ── Render ────────────────────────────────────────────────────────────────

  if (!open) return null;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Respond to Feedback</DialogTitle>
        </DialogHeader>

        {/* ── Free plan upgrade CTA ── */}
        {isFree ? (
          <div data-testid="upgrade-cta" className="space-y-4 py-4">
            <div className="p-6 rounded-xl border border-border bg-secondary/30 text-center space-y-3">
              <div className="p-3 bg-primary/10 rounded-full w-fit mx-auto">
                <Zap className="w-6 h-6 text-primary" />
              </div>
              <h3 className="text-lg font-semibold">
                Response Suggestions is available on Pro and above
              </h3>
              <p className="text-sm text-muted-foreground">
                Use AI-powered templates to respond to customer feedback faster and more consistently.
              </p>
              <Button asChild>
                <Link href="/settings/billing">Upgrade to Pro</Link>
              </Button>
            </div>
          </div>
        ) : view === 'browse' ? (
          /* ── Template Browser sub-view ── */
          <TemplateBrowser
            onSelect={handleUseTemplate}
            onBack={() => setView('main')}
          />
        ) : (
          /* ── Main modal view ── */
          <div className="space-y-4 pt-2">

            {/* Template Suggestion */}
            {suggestedTemplate && (
              <div className="p-4 rounded-xl border border-border bg-secondary/20 space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                  <ClipboardList className="w-4 h-4" />
                  Suggested Template
                </div>
                <p className="font-semibold text-sm">{suggestedTemplate.name}</p>
                <p className="text-sm text-muted-foreground line-clamp-2">
                  {suggestedTemplate.body}
                </p>
                <div className="flex justify-end">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleUseTemplate(suggestedTemplate)}
                  >
                    Use this
                  </Button>
                </div>
              </div>
            )}

            {/* Actions row */}
            <div className="flex items-center gap-3">
              <button
                onClick={() => setView('browse')}
                className="text-sm text-primary hover:underline"
              >
                Browse all templates
              </button>
              <div className="flex-1" />
              <Button
                variant="outline"
                size="sm"
                onClick={handleGenerateAI}
                disabled={generating}
              >
                {generating ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Generating…</>
                ) : (
                  <><Sparkles className="w-4 h-4 mr-2" />Generate with AI</>
                )}
              </Button>
            </div>

            {/* Separator */}
            <div className="border-t border-border" />

            {/* Tone selector */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium shrink-0">Tone:</label>
              <Select
                value={tone}
                onValueChange={(v) => setTone(v as ToneOption)}
              >
                <SelectTrigger
                  data-testid="tone-select"
                  className="w-40"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TONE_OPTIONS.map(opt => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Editor */}
            <div className="space-y-2">
              <Textarea
                ref={textareaRef}
                aria-label="Response"
                value={responseText}
                onChange={(e) => setResponseText(e.target.value)}
                placeholder="Write your response here…"
                className="min-h-[160px] resize-y font-mono text-sm"
                rows={8}
              />

              {/* Variable pills */}
              <div className="flex flex-wrap gap-1.5">
                {MODAL_RESPONSE_VARIABLES.map(v => (
                  <button
                    key={v.name}
                    onClick={() => insertVariable(v.name)}
                    title={v.description}
                    className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono border border-border bg-secondary hover:border-primary/50 hover:bg-primary/5 transition-colors"
                  >
                    {`{{${v.name}}}`}
                  </button>
                ))}
              </div>
            </div>

            {/* Usage counter */}
            {showUsageCounter && (
              <p
                data-testid="usage-counter"
                className="text-xs text-muted-foreground"
              >
                {usedCount}/{monthlyLimit} AI responses used this month
              </p>
            )}

            {/* Footer actions */}
            <div className="flex items-center justify-between pt-2 border-t border-border">
              <Button
                variant="outline"
                size="sm"
                onClick={handleCopyToClipboard}
                disabled={!responseText.trim()}
              >
                <Copy className="w-4 h-4 mr-2" />
                Copy to clipboard
              </Button>

              {connectedChannels.length > 0 && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      data-testid="send-via-button"
                      variant="default"
                      size="sm"
                      disabled={sending || !responseText.trim()}
                    >
                      <Send className="w-4 h-4 mr-2" />
                      Send via
                      <ChevronDown className="w-4 h-4 ml-2" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {connectedChannels.map(channel => (
                      <DropdownMenuItem
                        key={channel}
                        onClick={() => handleSendVia(channel)}
                      >
                        <Send className="w-4 h-4 mr-2" />
                        Send via {CHANNEL_LABELS[channel]}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
