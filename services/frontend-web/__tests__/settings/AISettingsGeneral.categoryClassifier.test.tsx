import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock AI settings API
vi.mock('@/lib/api/ai-settings', () => ({
  aiSettingsAPI: {
    get: vi.fn(),
    update: vi.fn(),
    getSentimentStatus: vi.fn(),
  },
}));

import { aiSettingsAPI } from '@/lib/api/ai-settings';
import { AISettingsGeneral } from '@/components/settings/AISettingsGeneral';

const adminUser = {
  id: 1,
  email: 'admin@test.com',
  role: 'admin',
  plan: 'pro',
  organization_id: 1,
  is_system_admin: false,
};

const mockSettings = {
  ai_analysis_enabled: true,
  has_custom_key: false,
  default_provider: 'openai',
  base_url: null,
  model_embeddings: null,
  sentiment_provider: 'vader',
  classifier_mode: 'off',
  category_classifier_mode: 'off',
  models: {
    categorization: 'gpt-4o-mini',
    analysis: 'gpt-4o-mini',
    insights: 'gpt-4o-mini',
  },
};

describe('AISettingsGeneral — category classifier mode toggle (M5.2 category classifier)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({
      user: adminUser,
      isLoading: false,
      isAuthenticated: true,
    });
    vi.mocked(aiSettingsAPI.getSentimentStatus).mockResolvedValue({
      provider: 'vader',
      available: true,
      model: null,
    });
  });

  it('renders a second control distinguishable by "Category classifier mode" aria-label, current mode selected', () => {
    render(<AISettingsGeneral settings={mockSettings} onUpdate={vi.fn()} />);
    expect(screen.getByText(/self-improving category classifier/i)).toBeInTheDocument();
    const trigger = screen.getByLabelText(/category classifier mode/i);
    expect(trigger).toHaveTextContent('Off');
  });

  it('the sentiment control and category control are distinct elements', () => {
    render(<AISettingsGeneral settings={mockSettings} onUpdate={vi.fn()} />);
    const sentimentTrigger = screen.getByLabelText('Classifier mode');
    const categoryTrigger = screen.getByLabelText('Category classifier mode');
    expect(sentimentTrigger).not.toBe(categoryTrigger);
  });

  it('selecting "Shadow" on the category control calls update with ONLY category_classifier_mode (does not touch classifier_mode)', async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn();
    const updated = { ...mockSettings, category_classifier_mode: 'shadow' };
    vi.mocked(aiSettingsAPI.update).mockResolvedValue(updated);

    render(<AISettingsGeneral settings={mockSettings} onUpdate={onUpdate} />);

    const trigger = screen.getByLabelText(/category classifier mode/i);
    await user.click(trigger);
    const shadowOption = await screen.findByRole('option', { name: 'Shadow' });
    await user.click(shadowOption);

    await waitFor(() => {
      expect(aiSettingsAPI.update).toHaveBeenCalledWith({ category_classifier_mode: 'shadow' });
      expect(onUpdate).toHaveBeenCalledWith(updated);
    });
    // Exact single-key payload — the sentiment field must never be present in this call.
    const callArgs = vi.mocked(aiSettingsAPI.update).mock.calls[0][0];
    expect(callArgs).not.toHaveProperty('classifier_mode');
  });

  it('selecting a value on the sentiment control still calls update with ONLY classifier_mode (independence, reverse direction)', async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn();
    const updated = { ...mockSettings, classifier_mode: 'shadow' };
    vi.mocked(aiSettingsAPI.update).mockResolvedValue(updated);

    render(<AISettingsGeneral settings={mockSettings} onUpdate={onUpdate} />);

    const trigger = screen.getByLabelText('Classifier mode');
    await user.click(trigger);
    const shadowOption = await screen.findByRole('option', { name: 'Shadow' });
    await user.click(shadowOption);

    await waitFor(() => {
      expect(aiSettingsAPI.update).toHaveBeenCalledWith({ classifier_mode: 'shadow' });
    });
    const callArgs = vi.mocked(aiSettingsAPI.update).mock.calls[0][0];
    expect(callArgs).not.toHaveProperty('category_classifier_mode');
  });

  it('surfaces a 422 error under the category control specifically, not shared with the sentiment error state', async () => {
    const user = userEvent.setup();
    vi.mocked(aiSettingsAPI.update).mockRejectedValue({
      response: { data: { detail: "category_classifier_mode 'auto' requires scikit-learn to be installed." } },
    });

    render(<AISettingsGeneral settings={mockSettings} onUpdate={vi.fn()} />);

    const trigger = screen.getByLabelText(/category classifier mode/i);
    await user.click(trigger);
    const autoOption = await screen.findByRole('option', { name: 'Auto' });
    await user.click(autoOption);

    await waitFor(() => {
      expect(screen.getByText(/requires scikit-learn/i)).toBeInTheDocument();
    });
  });

  it('guards against a missing category_classifier_mode from a stale/un-migrated backend mock (defaults to off)', () => {
    const staleSettings = { ...mockSettings } as any;
    delete staleSettings.category_classifier_mode;

    render(<AISettingsGeneral settings={staleSettings} onUpdate={vi.fn()} />);

    const trigger = screen.getByLabelText(/category classifier mode/i);
    expect(trigger).toHaveTextContent('Off');
  });
});
