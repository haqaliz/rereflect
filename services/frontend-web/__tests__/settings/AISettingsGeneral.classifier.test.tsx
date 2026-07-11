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

describe('AISettingsGeneral — classifier mode toggle (M5.2)', () => {
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

  it('renders the off/shadow/auto control with the current mode selected', () => {
    render(<AISettingsGeneral settings={mockSettings} onUpdate={vi.fn()} />);
    expect(screen.getByText(/self-improving classifier/i)).toBeInTheDocument();
    // Exact match — "Classifier mode" is a substring of the category card's
    // "Category classifier mode" aria-label (both now render), so a regex match would
    // be ambiguous now that the category card (M5.2 v2) is also on this tab.
    const trigger = screen.getByLabelText('Classifier mode');
    expect(trigger).toHaveTextContent('Off');
  });

  it('shows honest copy recommending shadow mode until n is substantial', () => {
    render(<AISettingsGeneral settings={mockSettings} onUpdate={vi.fn()} />);
    // Both the sentiment and category cards recommend shadow mode now — assert at least one.
    expect(screen.getAllByText(/shadow/i).length).toBeGreaterThan(0);
  });

  it('calls update({ classifier_mode: "shadow" }) and lifts state via onUpdate when shadow is selected', async () => {
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
      expect(onUpdate).toHaveBeenCalledWith(updated);
    });
  });

  it('surfaces the 422 error message when the PATCH fails', async () => {
    const user = userEvent.setup();
    vi.mocked(aiSettingsAPI.update).mockRejectedValue({
      response: { data: { detail: "classifier_mode 'auto' requires scikit-learn to be installed." } },
    });

    render(<AISettingsGeneral settings={mockSettings} onUpdate={vi.fn()} />);

    const trigger = screen.getByLabelText('Classifier mode');
    await user.click(trigger);
    const autoOption = await screen.findByRole('option', { name: 'Auto' });
    await user.click(autoOption);

    await waitFor(() => {
      expect(screen.getByText(/requires scikit-learn/i)).toBeInTheDocument();
    });
  });
});
