import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
  models: {
    categorization: 'gpt-4o-mini',
    analysis: 'gpt-4o-mini',
    insights: 'gpt-4o-mini',
  },
};

describe('AISettingsGeneral', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({
      user: adminUser,
      isLoading: false,
      isAuthenticated: true,
    });
    vi.mocked(aiSettingsAPI.update).mockResolvedValue({
      ...mockSettings,
      ai_analysis_enabled: false,
    });
  });

  it('renders the AI toggle', () => {
    render(<AISettingsGeneral settings={mockSettings} onUpdate={vi.fn()} />);
    expect(screen.getByRole('switch')).toBeInTheDocument();
  });

  it('shows toggle as checked when AI is enabled', () => {
    render(<AISettingsGeneral settings={mockSettings} onUpdate={vi.fn()} />);
    const toggle = screen.getByRole('switch');
    expect(toggle).toHaveAttribute('aria-checked', 'true');
  });

  it('shows toggle as unchecked when AI is disabled', () => {
    render(
      <AISettingsGeneral
        settings={{ ...mockSettings, ai_analysis_enabled: false }}
        onUpdate={vi.fn()}
      />
    );
    const toggle = screen.getByRole('switch');
    expect(toggle).toHaveAttribute('aria-checked', 'false');
  });

  it('calls onUpdate when toggle is clicked', async () => {
    const onUpdate = vi.fn();
    vi.mocked(aiSettingsAPI.update).mockResolvedValue({
      ...mockSettings,
      ai_analysis_enabled: false,
    });
    render(<AISettingsGeneral settings={mockSettings} onUpdate={onUpdate} />);
    const toggle = screen.getByRole('switch');
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(aiSettingsAPI.update).toHaveBeenCalledWith({ ai_analysis_enabled: false });
    });
  });
});
