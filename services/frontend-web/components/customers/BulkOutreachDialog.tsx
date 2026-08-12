'use client';

import { useEffect, useState } from 'react';
import { AlertTriangle, Loader2, Mail, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { Cohort } from '@/lib/api/customers';
import { createCampaign, draftCampaign, OutreachDraftApiError } from '@/lib/api/outreach';
import { aiSettingsAPI } from '@/lib/api/ai-settings';
import { TONE_OPTIONS, type ToneOption } from '@/lib/api/responses';

const LOCAL_LLM_PROVIDERS = new Set(['ollama', 'openai_compatible']);
const OUTREACH_MAX_CUSTOMERS = 500;
const SUBJECT_MAX = 200;
const BODY_MAX = 20000;

interface BulkOutreachDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cohort: Cohort | null;
  /** Size of the resolved cohort — same value shown in the "Bulk Actions (N)" trigger. */
  cohortCount: number;
  onSuccess?: () => void;
}

interface PreviewResult {
  matched: number;
  skipped: number;
}

export function BulkOutreachDialog({
  open,
  onOpenChange,
  cohort,
  onSuccess,
}: BulkOutreachDialogProps) {
  const queryClient = useQueryClient();
  const [step, setStep] = useState<'compose' | 'confirm'>('compose');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [tone, setTone] = useState<ToneOption>('professional');
  const [aiConfigured, setAiConfigured] = useState(false);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  const hasContent = subject.trim() !== '' && body.trim() !== '';

  // LLM-config probe — hides "Draft with AI" entirely for keyless orgs
  // (create-issue/page.tsx:241-256 pattern): local providers count as
  // configured via base_url; cloud providers need a stored BYOK key for
  // the default_provider. Any failure → not configured.
  useEffect(() => {
    if (!open) return;
    setAiConfigured(false);
    aiSettingsAPI
      .get()
      .then(async (settings) => {
        if (LOCAL_LLM_PROVIDERS.has(settings.default_provider)) {
          setAiConfigured(Boolean(settings.base_url));
          return;
        }
        try {
          const keys = await aiSettingsAPI.listKeys();
          setAiConfigured(keys.some((k) => k.provider === settings.default_provider));
        } catch {
          setAiConfigured(false);
        }
      })
      .catch(() => setAiConfigured(false));
  }, [open]);

  // Count-only preview. The preview is cohort-only (subject/body content is
  // irrelevant to the count) but the endpoint requires non-empty fields, so
  // it only runs once both are filled. Keyed on the raw fields with a 500ms
  // trailing debounce: continuous typing never fires, the fetch happens once
  // the user pauses — always with complete content. A cancelled flag keeps a
  // rapid cohort switch from landing a stale count (BulkRunPlaybookDialog
  // pattern).
  useEffect(() => {
    if (!open || !cohort || !hasContent) {
      setPreview(null);
      setPreviewLoading(false);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      setPreviewLoading(true);
      createCampaign({ cohort, subject: subject.trim(), body: body.trim() }, { countOnly: true })
        .then((res) => {
          if (!cancelled) setPreview({ matched: res.matched, skipped: res.skipped });
        })
        .catch(() => {
          if (!cancelled) setPreview(null);
        })
        .finally(() => {
          if (!cancelled) setPreviewLoading(false);
        });
    }, 500);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [open, cohort, subject, body, hasContent]);

  const reset = () => {
    setStep('compose');
    setSubject('');
    setBody('');
    setTone('professional');
    setPreview(null);
    setPreviewLoading(false);
    setSendError(null);
  };

  const overCap = preview !== null && preview.matched > OUTREACH_MAX_CUSTOMERS;

  const handleDraft = async () => {
    if (!cohort || drafting) return;
    setDrafting(true);
    try {
      const draft = await draftCampaign({ cohort, tone });
      const edited = subject.trim() !== '' || body.trim() !== '';
      if (edited && !window.confirm('Replace your text with the AI draft?')) {
        return;
      }
      setSubject(draft.subject);
      setBody(draft.body);
    } catch (err) {
      const message =
        err instanceof OutreachDraftApiError
          ? err.message
          : (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
            'Failed to draft the message. Please try again.';
      toast.error(message);
    } finally {
      setDrafting(false);
    }
  };

  const handleSend = async () => {
    if (!cohort || !preview || overCap || sending) return;
    setSending(true);
    setSendError(null);
    try {
      const result = await createCampaign({ cohort, subject: subject.trim(), body: body.trim() });
      toast.success(
        `Queued ${result.queued} outreach email${result.queued === 1 ? '' : 's'} to ${result.matched} recipient${result.matched === 1 ? '' : 's'}.`
      );
      queryClient.invalidateQueries({ queryKey: ['customers'] });
      queryClient.invalidateQueries({ queryKey: ['outreach-campaigns'] });
      onSuccess?.();
      onOpenChange(false);
      reset();
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      if (status === 422) {
        setStep('compose');
        setSendError(detail || 'The message failed validation. Please review and try again.');
      } else {
        toast.error(detail || 'Failed to queue the campaign. Please try again.');
      }
    } finally {
      setSending(false);
    }
  };

  const sendDisabled =
    !hasContent || previewLoading || preview === null || overCap || step === 'confirm';

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Trigger Outreach Campaign</DialogTitle>
          <DialogDescription>
            Send a one-off email to the customers in this cohort. Nothing sends until you confirm.
          </DialogDescription>
        </DialogHeader>

        {step === 'compose' ? (
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="outreach-subject">Subject</Label>
                <span className="text-xs text-muted-foreground">
                  {subject.length}/{SUBJECT_MAX}
                </span>
              </div>
              <Input
                id="outreach-subject"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                maxLength={SUBJECT_MAX}
                placeholder="Subject line"
              />
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="outreach-body">Message</Label>
                <span className="text-xs text-muted-foreground">
                  {body.length}/{BODY_MAX}
                </span>
              </div>
              <Textarea
                id="outreach-body"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                maxLength={BODY_MAX}
                rows={6}
                placeholder="Your message to these customers…"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="outreach-tone">Tone</Label>
              <Select value={tone} onValueChange={(v) => setTone(v as ToneOption)}>
                <SelectTrigger id="outreach-tone">
                  <SelectValue placeholder="Select a tone" />
                </SelectTrigger>
                <SelectContent>
                  {TONE_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {aiConfigured && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleDraft}
                disabled={drafting || !cohort}
                className="w-full"
              >
                {drafting ? (
                  <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />
                ) : (
                  <Sparkles className="w-3.5 h-3.5 mr-2" />
                )}
                ✨ Draft with AI
              </Button>
            )}

            {preview && !overCap && (
              <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
                {previewLoading ? (
                  <span className="flex items-center gap-2 text-muted-foreground">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Counting recipients…
                  </span>
                ) : (
                  <span className="text-foreground">
                    {preview.matched} will be emailed, {preview.skipped} skipped (opted out or no
                    email)
                  </span>
                )}
              </div>
            )}

            {overCap && (
              <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2">
                <AlertTriangle className="w-4 h-4 text-destructive mt-0.5 shrink-0" />
                <p className="text-sm text-destructive">
                  Cohort of {preview?.matched} exceeds the batch cap of {OUTREACH_MAX_CUSTOMERS}.
                  Narrow your filter and try again.
                </p>
              </div>
            )}

            {sendError && (
              <Alert variant="destructive">
                <AlertTitle>Could not queue the campaign</AlertTitle>
                <AlertDescription>{sendError}</AlertDescription>
              </Alert>
            )}
          </div>
        ) : (
          <div className="space-y-4 py-2">
            <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm space-y-1">
              <p className="font-medium text-foreground">{subject}</p>
              <p className="text-muted-foreground whitespace-pre-wrap">{body}</p>
            </div>
            {preview && (
              <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
                <span className="text-foreground">
                  {preview.matched} will be emailed, {preview.skipped} skipped (opted out or no
                  email)
                </span>
              </div>
            )}
            {preview?.matched === 0 && (
              <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2">
                <AlertTriangle className="w-4 h-4 text-destructive mt-0.5 shrink-0" />
                <p className="text-sm text-destructive">No recipients to email.</p>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={sending || drafting}
          >
            {step === 'confirm' ? 'Back' : 'Cancel'}
          </Button>
          {step === 'compose' ? (
            <Button onClick={() => setStep('confirm')} disabled={sendDisabled}>
              <Mail className="w-3.5 h-3.5 mr-2" />
              Send
            </Button>
          ) : (
            <Button onClick={handleSend} disabled={sending || preview?.matched === 0}>
              {sending && <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />}
              {preview ? `Confirm & send to ${preview.matched}` : 'Confirm & send'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
