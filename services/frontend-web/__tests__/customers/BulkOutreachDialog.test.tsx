import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

vi.mock('@/lib/api/outreach', () => ({
  createCampaign: vi.fn(),
  draftCampaign: vi.fn(),
  listCampaigns: vi.fn(),
  retryCampaign: vi.fn(),
  unsubscribe: vi.fn(),
  OutreachDraftApiError: class OutreachDraftApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.name = 'OutreachDraftApiError';
      this.status = status;
    }
  },
}));

vi.mock('@/lib/api/ai-settings', () => ({
  aiSettingsAPI: {
    get: vi.fn(),
    listKeys: vi.fn(),
  },
}));

vi.mock('@/lib/api/responses', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/responses')>('@/lib/api/responses');
  return { ...actual };
});

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { createCampaign, draftCampaign } from '@/lib/api/outreach';
import { aiSettingsAPI } from '@/lib/api/ai-settings';
import { toast } from 'sonner';
import { BulkOutreachDialog } from '@/components/customers/BulkOutreachDialog';
import type { Cohort } from '@/lib/api/customers';

const mockCreateCampaign = createCampaign as ReturnType<typeof vi.fn>;
const mockDraftCampaign = draftCampaign as ReturnType<typeof vi.fn>;
const mockAiGet = aiSettingsAPI.get as ReturnType<typeof vi.fn>;
const mockListKeys = aiSettingsAPI.listKeys as ReturnType<typeof vi.fn>;

const COHORT: Cohort = { emails: ['alice@example.com', 'bob@example.com'] };

function renderDialog(props?: Partial<React.ComponentProps<typeof BulkOutreachDialog>>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
  const defaultProps: React.ComponentProps<typeof BulkOutreachDialog> = {
    open: true,
    onOpenChange: vi.fn(),
    cohort: COHORT,
    cohortCount: 2,
    onSuccess: vi.fn(),
    ...props,
  };
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <BulkOutreachDialog {...defaultProps} />
    </QueryClientProvider>
  );
  return { ...utils, invalidateSpy, queryClient };
}

async function fillComposeForm(user: ReturnType<typeof userEvent.setup>, subject = 'We miss you', body = 'Tell us what happened?') {
  await user.type(screen.getByLabelText(/subject/i), subject);
  await user.type(screen.getByLabelText(/message/i), body);
}

describe('BulkOutreachDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAiGet.mockResolvedValue({
      ai_analysis_enabled: true,
      has_custom_key: true,
      default_provider: 'openai',
      base_url: null,
      model_embeddings: null,
      sentiment_provider: 'openai',
      classifier_mode: 'auto',
      category_classifier_mode: 'auto',
      urgency_classifier_mode: 'auto',
      usage_churn_labels_mode: 'auto',
      usage_churn_label_config: null,
      models: { categorization: 'x', analysis: 'y', insights: 'z' },
    });
    mockListKeys.mockResolvedValue([{ provider: 'openai', key_hint: 'sk-…', is_valid: true, created_at: '' }]);
    mockCreateCampaign.mockResolvedValue({ matched: 2, queued: 2, skipped: 0, errors: [] });
    mockDraftCampaign.mockResolvedValue({
      subject: 'A note from Acme',
      body: 'We noticed you went quiet — want to tell us what happened?',
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders subject/body with length counters, the tone selector and a disabled Send until filled', async () => {
    renderDialog();

    const subject = screen.getByLabelText(/subject/i);
    const body = screen.getByLabelText(/message/i);
    expect(subject).toHaveAttribute('maxlength', '200');
    expect(body).toHaveAttribute('maxlength', '20000');
    expect(screen.getByText('0/200')).toBeInTheDocument();
    expect(screen.getByText('0/20000')).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole('combobox'));
    expect(await screen.findByText('Friendly')).toBeInTheDocument();
    expect(screen.getByText('Concise')).toBeInTheDocument();
    expect(screen.getByText('Technical')).toBeInTheDocument();
    await user.keyboard('{Escape}');

    const send = screen.getByRole('button', { name: /send/i });
    expect(send).toBeDisabled();

    await fillComposeForm(user);
    expect(screen.getByText('11/200')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /send/i })).toBeEnabled();
    });
  });

  it('hides "Draft with AI" when the LLM-config probe fails (no LLM configured)', async () => {
    mockAiGet.mockRejectedValue(new Error('network'));
    renderDialog();

    await waitFor(() => expect(mockAiGet).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: /draft with ai/i })).not.toBeInTheDocument();
  });

  it('shows "Draft with AI" when a cloud provider key exists, and drafts the fields', async () => {
    const user = userEvent.setup();
    renderDialog();

    const draftButton = await screen.findByRole('button', { name: /draft with ai/i });
    await user.click(draftButton);

    await waitFor(() => {
      expect(mockDraftCampaign).toHaveBeenCalledWith({ cohort: COHORT, tone: 'professional' });
    });
    await waitFor(() => {
      expect(screen.getByLabelText(/subject/i)).toHaveValue('A note from Acme');
    });
    expect(screen.getByLabelText(/message/i)).toHaveValue(
      'We noticed you went quiet — want to tell us what happened?'
    );
  });

  it('asks window.confirm before overwriting edited fields with the AI draft', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const user = userEvent.setup();
    renderDialog();

    await user.type(screen.getByLabelText(/subject/i), 'my hand-written subject');
    await user.click(await screen.findByRole('button', { name: /draft with ai/i }));

    await waitFor(() => {
      expect(confirmSpy).toHaveBeenCalledWith('Replace your text with the AI draft?');
    });
    expect(screen.getByLabelText(/subject/i)).toHaveValue('A note from Acme');
  });

  it('leaves fields untouched when the confirm is cancelled', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const user = userEvent.setup();
    renderDialog();

    await user.type(screen.getByLabelText(/subject/i), 'my hand-written subject');
    await user.click(await screen.findByRole('button', { name: /draft with ai/i }));

    await waitFor(() => expect(confirmSpy).toHaveBeenCalled());
    expect(screen.getByLabelText(/subject/i)).toHaveValue('my hand-written subject');
  });

  it('surfaces a raced 409 draft failure (no LLM) via toast with the backend detail', async () => {
    mockDraftCampaign.mockRejectedValue({
      status: 409,
      response: { status: 409, data: { detail: 'No AI model configured.' } },
    });
    const user = userEvent.setup();
    renderDialog();

    await user.click(await screen.findByRole('button', { name: /draft with ai/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('No AI model configured.');
    });
  });

  it('shows the count-only preview (matched will be emailed, skipped loudly)', async () => {
    mockCreateCampaign.mockResolvedValue({ matched: 3, queued: 0, skipped: 1, errors: [] });
    const user = userEvent.setup();
    renderDialog();

    await fillComposeForm(user);
    await waitFor(() => {
      expect(mockCreateCampaign).toHaveBeenCalledWith(
        { cohort: COHORT, subject: 'We miss you', body: 'Tell us what happened?' },
        { countOnly: true }
      );
    });
    expect(
      await screen.findByText(/3 will be emailed, 1 skipped \(opted out or no email\)/i)
    ).toBeInTheDocument();
  });

  it('blocks Send with a destructive guard when the cohort exceeds the 500 cap', async () => {
    mockCreateCampaign.mockResolvedValue({ matched: 900, queued: 0, skipped: 3, errors: [] });
    const user = userEvent.setup();
    renderDialog();

    await fillComposeForm(user);
    expect(await screen.findByText(/exceeds the batch cap of 500/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send/i })).toBeDisabled();
  });

  it('confirm step: explicit second click sends without count_only, toasts, invalidates both keys and calls onSuccess', async () => {
    mockCreateCampaign.mockResolvedValue({ matched: 3, queued: 3, skipped: 0, errors: [] });
    const user = userEvent.setup();
    const onSuccess = vi.fn();
    const onOpenChange = vi.fn();
    const { invalidateSpy } = renderDialog({ onSuccess, onOpenChange });

    await fillComposeForm(user);
    await waitFor(() => expect(mockCreateCampaign).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole('button', { name: /^send$/i }));
    expect(
      screen.getByRole('button', { name: /confirm & send to 3/i })
    ).toBeInTheDocument();
    expect(mockCreateCampaign).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: /confirm & send to 3/i }));

    await waitFor(() => {
      expect(mockCreateCampaign).toHaveBeenLastCalledWith(
        { cohort: COHORT, subject: 'We miss you', body: 'Tell us what happened?' }
      );
    });
    expect(toast.success).toHaveBeenCalled();
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['customers'] });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['outreach-campaigns'] });
    });
    expect(onSuccess).toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('disables the confirm step when matched is 0 ("No recipients to email")', async () => {
    mockCreateCampaign.mockResolvedValue({ matched: 0, queued: 0, skipped: 0, errors: [] });
    const user = userEvent.setup();
    renderDialog();

    await fillComposeForm(user);
    await waitFor(() => expect(mockCreateCampaign).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole('button', { name: /^send$/i }));

    expect(await screen.findByText(/no recipients to email/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /confirm & send to 0/i })).toBeDisabled();
  });

  it('renders a server 422 detail inline as a destructive alert (never a silent failure)', async () => {
    mockCreateCampaign
      .mockResolvedValueOnce({ matched: 3, queued: 0, skipped: 0, errors: [] })
      .mockRejectedValueOnce({
        response: { status: 422, data: { detail: 'subject must be 1-200 characters' } },
      });
    const user = userEvent.setup();
    renderDialog();

    await fillComposeForm(user);
    await waitFor(() => expect(mockCreateCampaign).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole('button', { name: /^send$/i }));
    await user.click(screen.getByRole('button', { name: /confirm & send to 3/i }));

    expect(
      await screen.findByText(/subject must be 1-200 characters/i)
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /confirm & send to 3/i })).not.toBeInTheDocument();
  });
});
