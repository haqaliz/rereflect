import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/lib/api/ai-settings', () => ({
  aiSettingsAPI: {
    update: vi.fn(),
  },
}));

vi.mock('@/lib/api/churn-suggestions', () => ({
  listChurnSuggestions: vi.fn(),
}));

import { aiSettingsAPI } from '@/lib/api/ai-settings';
import { listChurnSuggestions } from '@/lib/api/churn-suggestions';
import { UsageChurnLabelsCard } from '@/components/settings/UsageChurnLabelsCard';

const baseSettings = {
  ai_analysis_enabled: true,
  has_custom_key: false,
  default_provider: 'openai',
  base_url: null,
  model_embeddings: null,
  sentiment_provider: 'vader',
  classifier_mode: 'off',
  category_classifier_mode: 'off',
  urgency_classifier_mode: 'off',
  usage_churn_labels_mode: 'off',
  usage_churn_label_config: { sustain_days: 14 },
  models: { categorization: 'gpt-4o-mini', analysis: 'gpt-4o-mini', insights: 'gpt-4o-mini' },
};

function mockCountsResponse(confirmed: number, rejected: number, pending: number) {
  vi.mocked(listChurnSuggestions).mockImplementation((params: any) => {
    const total =
      params?.status === 'confirmed' ? confirmed : params?.status === 'rejected' ? rejected : pending;
    return Promise.resolve({
      items: [],
      total,
      page: 1,
      page_size: 1,
    });
  });
}

describe('UsageChurnLabelsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCountsResponse(0, 0, 0);
  });

  it('renders the three modes with the current mode selected', () => {
    render(<UsageChurnLabelsCard settings={baseSettings as any} onUpdate={vi.fn()} />);
    const trigger = screen.getByLabelText(/usage churn labels mode/i);
    expect(trigger).toHaveTextContent('Off');
  });

  it('changing mode issues the expected PATCH via aiSettingsAPI.update', async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn();
    const updated = { ...baseSettings, usage_churn_labels_mode: 'shadow' };
    vi.mocked(aiSettingsAPI.update).mockResolvedValue(updated as any);

    render(<UsageChurnLabelsCard settings={baseSettings as any} onUpdate={onUpdate} />);

    const trigger = screen.getByLabelText(/usage churn labels mode/i);
    await user.click(trigger);
    const shadowOption = await screen.findByRole('option', { name: 'Shadow' });
    await user.click(shadowOption);

    await waitFor(() => {
      expect(aiSettingsAPI.update).toHaveBeenCalledWith({ usage_churn_labels_mode: 'shadow' });
      expect(onUpdate).toHaveBeenCalledWith(updated);
    });
  });

  it('blocks save and shows a client-side error for an out-of-range sustain_days value', async () => {
    const user = userEvent.setup();
    render(<UsageChurnLabelsCard settings={baseSettings as any} onUpdate={vi.fn()} />);

    const input = screen.getByLabelText(/sustain days/i);
    await user.clear(input);
    await user.type(input, '91');
    await user.tab();

    await waitFor(() => {
      expect(screen.getByText(/between 1 and 90/i)).toBeInTheDocument();
    });
    expect(aiSettingsAPI.update).not.toHaveBeenCalled();
  });

  it('surfaces the API 422 detail for sustain_days, does not swallow it', async () => {
    const user = userEvent.setup();
    vi.mocked(aiSettingsAPI.update).mockRejectedValue({
      response: { data: { detail: 'sustain_days must be between 1 and 90.' } },
    });

    render(<UsageChurnLabelsCard settings={baseSettings as any} onUpdate={vi.fn()} />);

    const input = screen.getByLabelText(/sustain days/i);
    await user.clear(input);
    await user.type(input, '30');
    await user.tab();

    await waitFor(() => {
      expect(screen.getByText(/sustain_days must be between 1 and 90/i)).toBeInTheDocument();
    });
  });

  it('renders confirmed/rejected/pending precision counts for provider=usage_decline', async () => {
    mockCountsResponse(4, 2, 6);
    render(<UsageChurnLabelsCard settings={baseSettings as any} onUpdate={vi.fn()} />);

    await waitFor(() => {
      expect(listChurnSuggestions).toHaveBeenCalledWith(
        expect.objectContaining({ provider: 'usage_decline', status: 'confirmed' })
      );
      expect(listChurnSuggestions).toHaveBeenCalledWith(
        expect.objectContaining({ provider: 'usage_decline', status: 'rejected' })
      );
      expect(listChurnSuggestions).toHaveBeenCalledWith(
        expect.objectContaining({ provider: 'usage_decline', status: 'pending' })
      );
    });

    await waitFor(() => {
      expect(screen.getByText('4')).toBeInTheDocument();
      expect(screen.getByText('2')).toBeInTheDocument();
      expect(screen.getByText('6')).toBeInTheDocument();
    });
  });

  it('shows a "no suggestions yet" affordance when all counts are zero', async () => {
    mockCountsResponse(0, 0, 0);
    render(<UsageChurnLabelsCard settings={baseSettings as any} onUpdate={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/no usage-decline suggestions yet/i)).toBeInTheDocument();
    });
  });

  it('states the ~12-16 day warm-up honest-limits copy', () => {
    const { container } = render(<UsageChurnLabelsCard settings={baseSettings as any} onUpdate={vi.fn()} />);
    expect(container.textContent).toMatch(/12.?(–|-|to)?.?16 day/i);
  });

  it('states the extra sustain_days window in the honest-limits copy', () => {
    const { container } = render(<UsageChurnLabelsCard settings={baseSettings as any} onUpdate={vi.fn()} />);
    expect(container.textContent).toMatch(/sustain days.*window|window.*sustain days/i);
  });

  it('states the >=5 active-day baseline floor can never produce a suggestion', () => {
    const { container } = render(<UsageChurnLabelsCard settings={baseSettings as any} onUpdate={vi.fn()} />);
    expect(container.textContent).toMatch(/5 active days/i);
    expect(container.textContent).toMatch(/never/i);
  });

  it('states that only recently-declining customers are visible (long-departed customers never appear)', () => {
    const { container } = render(<UsageChurnLabelsCard settings={baseSettings as any} onUpdate={vi.fn()} />);
    expect(container.textContent).toMatch(/never appear/i);
  });

  it('guards against a missing usage_churn_labels_mode from a stale settings object (defaults to off)', () => {
    const staleSettings = { ...baseSettings } as any;
    delete staleSettings.usage_churn_labels_mode;
    render(<UsageChurnLabelsCard settings={staleSettings} onUpdate={vi.fn()} />);
    const trigger = screen.getByLabelText(/usage churn labels mode/i);
    expect(trigger).toHaveTextContent('Off');
  });
});
