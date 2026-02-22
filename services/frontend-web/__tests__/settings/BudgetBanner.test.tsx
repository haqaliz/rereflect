import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

// Mock the AI settings API
vi.mock('@/lib/api/ai-settings', () => ({
  aiSettingsAPI: {
    getBudget: vi.fn(),
  },
}));

import { aiSettingsAPI } from '@/lib/api/ai-settings';
import { BudgetBanner } from '@/components/shared/BudgetBanner';

const mockBudgetExceeded = {
  monthly_limit_cents: 1000,
  used_cents: 1000,
  resets_at: '2026-03-01T00:00:00Z',
  is_exceeded: true,
};

const mockBudgetNotExceeded = {
  monthly_limit_cents: 1000,
  used_cents: 500,
  resets_at: '2026-03-01T00:00:00Z',
  is_exceeded: false,
};

describe('BudgetBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPush.mockClear();
  });

  it('shows banner when budget is exceeded', () => {
    render(<BudgetBanner budget={mockBudgetExceeded} />);
    expect(screen.getByText(/AI budget exceeded/i)).toBeInTheDocument();
  });

  it('is hidden when budget is not exceeded', () => {
    const { container } = render(<BudgetBanner budget={mockBudgetNotExceeded} />);
    expect(container.firstChild).toBeNull();
  });

  it('is hidden when budget is null', () => {
    const { container } = render(<BudgetBanner budget={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows correct used and limit amounts', () => {
    render(<BudgetBanner budget={mockBudgetExceeded} />);
    // $10.00 / $10.00 (cents to dollars)
    expect(screen.getByText(/\$10\.00/)).toBeInTheDocument();
  });

  it('shows the budget reset date', () => {
    render(<BudgetBanner budget={mockBudgetExceeded} />);
    // Should show "Mar 1" or "March 1"
    expect(screen.getByText(/Mar/i)).toBeInTheDocument();
  });

  it('has Upgrade Plan button', () => {
    render(<BudgetBanner budget={mockBudgetExceeded} />);
    expect(screen.getByRole('button', { name: /upgrade/i })).toBeInTheDocument();
  });

  it('has Add Your Own API Key button', () => {
    render(<BudgetBanner budget={mockBudgetExceeded} />);
    expect(screen.getByRole('button', { name: /api key/i })).toBeInTheDocument();
  });

  it('Upgrade button navigates to billing', () => {
    render(<BudgetBanner budget={mockBudgetExceeded} />);
    const upgradeBtn = screen.getByRole('button', { name: /upgrade/i });
    upgradeBtn.click();
    expect(mockPush).toHaveBeenCalledWith('/settings/billing');
  });

  it('API Key button navigates to AI settings providers tab', () => {
    render(<BudgetBanner budget={mockBudgetExceeded} />);
    const keyBtn = screen.getByRole('button', { name: /api key/i });
    keyBtn.click();
    expect(mockPush).toHaveBeenCalledWith('/settings/ai?tab=providers');
  });
});
