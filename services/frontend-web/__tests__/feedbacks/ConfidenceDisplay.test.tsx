import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock next/navigation for page-level components
const mockPush = vi.fn();
const mockParams = { id: '42' };
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => mockParams,
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/feedbacks/42',
}));

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

const proUser = {
  id: 1,
  email: 'owner@test.com',
  role: 'owner',
  plan: 'pro',
  organization_id: 1,
  is_system_admin: false,
};

const freeUser = { ...proUser, plan: 'free' };

// ------- ConfidenceBadge unit tests -------

import { ConfidenceBadge } from '@/components/feedbacks/ConfidenceBadge';

describe('ConfidenceBadge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser, isLoading: false, isAuthenticated: true });
  });

  it('shows confidence score with badge', () => {
    render(<ConfidenceBadge confidenceScore={87} feedbackCount={20} lastFeedbackDaysAgo={3} uniqueCategories={5} />);
    expect(screen.getByText(/87% confidence/i)).toBeInTheDocument();
  });

  it('is red when confidence is less than 30', () => {
    render(<ConfidenceBadge confidenceScore={23} feedbackCount={1} lastFeedbackDaysAgo={90} uniqueCategories={1} />);
    const badge = screen.getByTestId('confidence-badge');
    expect(badge).toHaveAttribute('data-color', 'red');
  });

  it('is yellow when confidence is 30-60', () => {
    render(<ConfidenceBadge confidenceScore={45} feedbackCount={5} lastFeedbackDaysAgo={20} uniqueCategories={2} />);
    const badge = screen.getByTestId('confidence-badge');
    expect(badge).toHaveAttribute('data-color', 'yellow');
  });

  it('is green when confidence is greater than 60', () => {
    render(<ConfidenceBadge confidenceScore={87} feedbackCount={20} lastFeedbackDaysAgo={3} uniqueCategories={5} />);
    const badge = screen.getByTestId('confidence-badge');
    expect(badge).toHaveAttribute('data-color', 'green');
  });

  it('tooltip shows explanation with feedback count, days ago, and categories', () => {
    render(<ConfidenceBadge confidenceScore={87} feedbackCount={20} lastFeedbackDaysAgo={3} uniqueCategories={5} />);
    // Tooltip content is rendered in DOM for testing
    expect(screen.getByTestId('confidence-tooltip')).toHaveTextContent(/20 feedbacks/i);
    expect(screen.getByTestId('confidence-tooltip')).toHaveTextContent(/3 days ago/i);
    expect(screen.getByTestId('confidence-tooltip')).toHaveTextContent(/5 topic categor/i);
  });

  it('is hidden for Free plan users', () => {
    mockUseAuth.mockReturnValue({ user: freeUser, isLoading: false, isAuthenticated: true });
    render(<ConfidenceBadge confidenceScore={87} feedbackCount={20} lastFeedbackDaysAgo={3} uniqueCategories={5} />);
    expect(screen.queryByTestId('confidence-badge')).not.toBeInTheDocument();
  });
});

// ------- LowConfidenceWarning unit tests -------

import { LowConfidenceWarning } from '@/components/feedbacks/LowConfidenceWarning';

describe('LowConfidenceWarning', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser, isLoading: false, isAuthenticated: true });
  });

  it('shows warning icon when confidence is less than 30', () => {
    render(<LowConfidenceWarning confidenceScore={23} />);
    expect(screen.getByTestId('low-confidence-warning')).toBeInTheDocument();
  });

  it('does not show warning icon when confidence is 30 or more', () => {
    render(<LowConfidenceWarning confidenceScore={30} />);
    expect(screen.queryByTestId('low-confidence-warning')).not.toBeInTheDocument();
  });

  it('does not show warning when confidence is high', () => {
    render(<LowConfidenceWarning confidenceScore={85} />);
    expect(screen.queryByTestId('low-confidence-warning')).not.toBeInTheDocument();
  });

  it('tooltip says "Low confidence — limited data for this customer"', () => {
    render(<LowConfidenceWarning confidenceScore={20} />);
    expect(screen.getByTestId('low-confidence-tooltip')).toHaveTextContent(/low confidence/i);
    expect(screen.getByTestId('low-confidence-tooltip')).toHaveTextContent(/limited data/i);
  });

  it('confidence hidden for Free plan users', () => {
    mockUseAuth.mockReturnValue({ user: freeUser, isLoading: false, isAuthenticated: true });
    render(<LowConfidenceWarning confidenceScore={20} />);
    expect(screen.queryByTestId('low-confidence-warning')).not.toBeInTheDocument();
  });
});
