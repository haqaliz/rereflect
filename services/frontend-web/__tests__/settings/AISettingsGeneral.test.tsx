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
    getBudget: vi.fn(),
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
  models: {
    categorization: 'gpt-4o-mini',
    analysis: 'gpt-4o-mini',
    insights: 'gpt-4o-mini',
  },
  budget: {
    monthly_limit_cents: 1000,
    used_cents: 720,
    resets_at: '2026-03-01T00:00:00Z',
    is_exceeded: false,
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

  it('shows budget progress bar', () => {
    render(<AISettingsGeneral settings={mockSettings} onUpdate={vi.fn()} />);
    // Should show budget section
    expect(screen.getAllByText(/budget/i).length).toBeGreaterThanOrEqual(1);
  });

  it('shows budget used and limit amounts', () => {
    render(<AISettingsGeneral settings={mockSettings} onUpdate={vi.fn()} />);
    // $7.20 used, $10.00 limit
    expect(screen.getByText(/\$7\.20/)).toBeInTheDocument();
    expect(screen.getByText(/\$10\.00/)).toBeInTheDocument();
  });

  it('shows budget reset date', () => {
    render(<AISettingsGeneral settings={mockSettings} onUpdate={vi.fn()} />);
    expect(screen.getByText(/Mar/i)).toBeInTheDocument();
  });

  it('shows exceeded warning when budget is exceeded', () => {
    const exceededSettings = {
      ...mockSettings,
      budget: { ...mockSettings.budget, is_exceeded: true, used_cents: 1000 },
    };
    render(<AISettingsGeneral settings={exceededSettings} onUpdate={vi.fn()} />);
    expect(screen.getByText(/budget.*exceeded|exceeded.*budget/i)).toBeInTheDocument();
  });

  it('does not show exceeded warning when budget is within limit', () => {
    render(<AISettingsGeneral settings={mockSettings} onUpdate={vi.fn()} />);
    expect(screen.queryByText(/budget.*exceeded|exceeded.*budget/i)).not.toBeInTheDocument();
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
