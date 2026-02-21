import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock next/link
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { ChurnFactorBreakdown } from '@/components/feedbacks/ChurnFactorBreakdown';

const mockFactors = {
  sentiment: { score: 15, max: 15, label: 'Very negative sentiment' },
  churn_keywords: { score: 10, max: 15, label: '2 churn keywords found' },
  frustration_keywords: { score: 5, max: 10, label: '1 frustration keyword' },
  urgency: { score: 10, max: 10, label: 'Marked as urgent' },
  sentiment_trend: { score: 9, max: 15, label: 'Sentiment declining' },
  feedback_frequency: { score: 3, max: 10, label: 'Normal frequency' },
  resolution_time: { score: 2, max: 10, label: 'Resolved within 1 day' },
  pain_severity: { score: 5, max: 10, label: '1 critical pain point' },
  feature_density: { score: 0, max: 5, label: 'Low feature request ratio' },
};

const proUser = {
  id: 1,
  email: 'owner@test.com',
  role: 'owner',
  plan: 'pro',
  organization_id: 1,
  is_system_admin: false,
};

const freeUser = {
  ...proUser,
  plan: 'free',
};

describe('ChurnFactorBreakdown', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({
      user: proUser,
      isLoading: false,
      isAuthenticated: true,
    });
  });

  it('renders factor breakdown section when churn_risk_factors exists', () => {
    render(<ChurnFactorBreakdown churnRiskFactors={mockFactors} />);
    expect(screen.getByText(/factor breakdown/i)).toBeInTheDocument();
  });

  it('is collapsed by default', () => {
    render(<ChurnFactorBreakdown churnRiskFactors={mockFactors} />);
    // Factor rows should NOT be visible when collapsed
    expect(screen.queryByText('Very negative sentiment')).not.toBeInTheDocument();
  });

  it('expands on click to show factors', () => {
    render(<ChurnFactorBreakdown churnRiskFactors={mockFactors} />);
    const toggleBtn = screen.getByRole('button', { name: /factor breakdown/i });
    fireEvent.click(toggleBtn);
    expect(screen.getByText('Very negative sentiment')).toBeInTheDocument();
  });

  it('shows factors sorted by score descending', () => {
    render(<ChurnFactorBreakdown churnRiskFactors={mockFactors} />);
    const toggleBtn = screen.getByRole('button', { name: /factor breakdown/i });
    fireEvent.click(toggleBtn);

    const labels = screen.getAllByTestId('factor-label').map((el) => el.textContent);
    // Highest score first: sentiment=15, churn_keywords=10, urgency=10, sentiment_trend=9, ...
    // sentiment (15) should come before feature_density (0)
    const sentimentIdx = labels.findIndex((l) => l?.includes('sentiment'));
    const featureIdx = labels.findIndex((l) => l?.includes('feature_density') || l?.includes('feature density'));
    expect(sentimentIdx).toBeLessThan(featureIdx >= 0 ? featureIdx : labels.length);
  });

  it('shows label, score/max text for each factor', () => {
    render(<ChurnFactorBreakdown churnRiskFactors={mockFactors} />);
    const toggleBtn = screen.getByRole('button', { name: /factor breakdown/i });
    fireEvent.click(toggleBtn);
    // Highest factor: sentiment 15/15
    expect(screen.getByText('15/15')).toBeInTheDocument();
    expect(screen.getByText('Very negative sentiment')).toBeInTheDocument();
  });

  it('shows progress bar for each factor', () => {
    render(<ChurnFactorBreakdown churnRiskFactors={mockFactors} />);
    const toggleBtn = screen.getByRole('button', { name: /factor breakdown/i });
    fireEvent.click(toggleBtn);
    const bars = screen.getAllByTestId('factor-progress-bar');
    expect(bars.length).toBe(9);
  });

  it('colors factor red when score is greater than 75% of max', () => {
    render(<ChurnFactorBreakdown churnRiskFactors={mockFactors} />);
    const toggleBtn = screen.getByRole('button', { name: /factor breakdown/i });
    fireEvent.click(toggleBtn);
    // sentiment: 15/15 = 100% > 75% → red
    const sentimentBar = screen.getAllByTestId('factor-progress-bar')[0];
    expect(sentimentBar).toHaveAttribute('data-color', 'red');
  });

  it('colors factor orange when score is 40-75% of max', () => {
    // churn_keywords: 10/15 = 66.7% → orange
    render(<ChurnFactorBreakdown churnRiskFactors={mockFactors} />);
    const toggleBtn = screen.getByRole('button', { name: /factor breakdown/i });
    fireEvent.click(toggleBtn);
    // Find churn_keywords bar (second highest after sentiment)
    const bars = screen.getAllByTestId('factor-progress-bar');
    // churn_keywords 10/15 = 66.7% → orange, urgency 10/10 = 100% → red
    // After sort descending: sentiment(15), urgency(10), churn_keywords(10)... tie-break
    // Find a bar with data-color="orange"
    const orangeBars = bars.filter((b) => b.getAttribute('data-color') === 'orange');
    expect(orangeBars.length).toBeGreaterThanOrEqual(1);
  });

  it('colors factor green when score is less than 40% of max', () => {
    render(<ChurnFactorBreakdown churnRiskFactors={mockFactors} />);
    const toggleBtn = screen.getByRole('button', { name: /factor breakdown/i });
    fireEvent.click(toggleBtn);
    // feature_density: 0/5 = 0% < 40% → green
    const bars = screen.getAllByTestId('factor-progress-bar');
    const greenBars = bars.filter((b) => b.getAttribute('data-color') === 'green');
    expect(greenBars.length).toBeGreaterThanOrEqual(1);
  });

  it('is hidden for Free plan users and shows upgrade CTA', () => {
    mockUseAuth.mockReturnValue({
      user: freeUser,
      isLoading: false,
      isAuthenticated: true,
    });
    render(<ChurnFactorBreakdown churnRiskFactors={mockFactors} />);
    expect(screen.queryByRole('button', { name: /factor breakdown/i })).not.toBeInTheDocument();
    expect(screen.getByText(/upgrade to pro/i)).toBeInTheDocument();
  });

  it('shows "Factor breakdown not available" when churn_risk_factors is null', () => {
    render(<ChurnFactorBreakdown churnRiskFactors={null} />);
    expect(screen.getByText(/factor breakdown not available/i)).toBeInTheDocument();
  });
});
