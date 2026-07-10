/**
 * Tests for the "Sentiment engine" toggle in AI Settings → General
 * (M5.1 local-analyzer-sentiment-model, per-org-resolution aspect).
 *
 * Verifies that:
 * - The toggle renders, defaults to unchecked ("vader") when unset/explicit vader.
 * - Toggling on/off round-trips sentiment_provider through the PATCH flow.
 * - The status line (GET /sentiment/status) surfaces availability without crashing.
 * - A PATCH failure (e.g. deps not installed) shows an error and does not call onUpdate.
 *
 * TDD: RED first, then production code.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

vi.mock('@/lib/api/ai-settings', () => ({
  aiSettingsAPI: {
    get: vi.fn(),
    update: vi.fn(),
    getSentimentStatus: vi.fn(),
  },
}));

import { aiSettingsAPI } from '@/lib/api/ai-settings';
import { AISettingsGeneral } from '@/components/settings/AISettingsGeneral';

const mockSettings = {
  ai_analysis_enabled: true,
  has_custom_key: false,
  default_provider: 'openai',
  base_url: null,
  model_embeddings: null,
  sentiment_provider: 'vader',
  models: {
    categorization: 'gpt-4o-mini',
    analysis: 'gpt-4o-mini',
    insights: 'gpt-4o-mini',
  },
};

const vaderStatus = { provider: 'vader', available: true, model: null };
const transformerAvailableStatus = {
  provider: 'transformer',
  available: true,
  model: 'cardiffnlp/twitter-roberta-base-sentiment-latest',
};
const transformerUnavailableStatus = {
  provider: 'transformer',
  available: false,
  model: 'cardiffnlp/twitter-roberta-base-sentiment-latest',
};

describe('AISettingsGeneral — Sentiment engine toggle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(aiSettingsAPI.getSentimentStatus).mockResolvedValue(vaderStatus);
  });

  it('renders a Sentiment engine toggle', async () => {
    render(<AISettingsGeneral settings={mockSettings} onUpdate={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByLabelText(/sentiment engine/i)).toBeInTheDocument();
    });
  });

  it('is unchecked when sentiment_provider is "vader"', async () => {
    render(<AISettingsGeneral settings={mockSettings} onUpdate={vi.fn()} />);
    const toggle = await screen.findByLabelText(/sentiment engine/i);
    expect(toggle).toHaveAttribute('aria-checked', 'false');
  });

  it('is checked when sentiment_provider is "transformer"', async () => {
    vi.mocked(aiSettingsAPI.getSentimentStatus).mockResolvedValue(transformerAvailableStatus);
    render(
      <AISettingsGeneral
        settings={{ ...mockSettings, sentiment_provider: 'transformer' }}
        onUpdate={vi.fn()}
      />
    );
    const toggle = await screen.findByLabelText(/sentiment engine/i);
    expect(toggle).toHaveAttribute('aria-checked', 'true');
  });

  it('PATCHes sentiment_provider="transformer" and calls onUpdate when toggled on', async () => {
    vi.mocked(aiSettingsAPI.update).mockResolvedValue({
      ...mockSettings,
      sentiment_provider: 'transformer',
    });
    const onUpdate = vi.fn();
    render(<AISettingsGeneral settings={mockSettings} onUpdate={onUpdate} />);

    const toggle = await screen.findByLabelText(/sentiment engine/i);
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(aiSettingsAPI.update).toHaveBeenCalledWith({ sentiment_provider: 'transformer' });
      expect(onUpdate).toHaveBeenCalledWith(
        expect.objectContaining({ sentiment_provider: 'transformer' })
      );
    });
  });

  it('PATCHes sentiment_provider="vader" when toggled off', async () => {
    vi.mocked(aiSettingsAPI.getSentimentStatus).mockResolvedValue(transformerAvailableStatus);
    vi.mocked(aiSettingsAPI.update).mockResolvedValue({
      ...mockSettings,
      sentiment_provider: 'vader',
    });
    const onUpdate = vi.fn();
    render(
      <AISettingsGeneral
        settings={{ ...mockSettings, sentiment_provider: 'transformer' }}
        onUpdate={onUpdate}
      />
    );

    const toggle = await screen.findByLabelText(/sentiment engine/i);
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(aiSettingsAPI.update).toHaveBeenCalledWith({ sentiment_provider: 'vader' });
    });
  });

  it('shows an unavailable hint when transformer deps are not installed', async () => {
    vi.mocked(aiSettingsAPI.getSentimentStatus).mockResolvedValue(transformerUnavailableStatus);
    render(
      <AISettingsGeneral
        settings={{ ...mockSettings, sentiment_provider: 'transformer' }}
        onUpdate={vi.fn()}
      />
    );
    await waitFor(() => {
      expect(screen.getByText(/not available|not installed/i)).toBeInTheDocument();
    });
  });

  it('degrades gracefully without crashing when the status fetch fails', async () => {
    vi.mocked(aiSettingsAPI.getSentimentStatus).mockRejectedValue(new Error('network error'));
    render(<AISettingsGeneral settings={mockSettings} onUpdate={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByLabelText(/sentiment engine/i)).toBeInTheDocument();
    });
  });

  it('shows an error and does not call onUpdate when PATCH fails (e.g. deps missing)', async () => {
    vi.mocked(aiSettingsAPI.update).mockRejectedValue({
      response: { data: { detail: "sentiment_provider 'transformer' requires torch and transformers" } },
    });
    const onUpdate = vi.fn();
    render(<AISettingsGeneral settings={mockSettings} onUpdate={onUpdate} />);

    const toggle = await screen.findByLabelText(/sentiment engine/i);
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(screen.getByText(/requires torch and transformers/i)).toBeInTheDocument();
    });
    expect(onUpdate).not.toHaveBeenCalled();
  });
});
