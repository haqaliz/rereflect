import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock AuthContext - Pro plan user
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      email: 'owner@test.com',
      role: 'owner',
      plan: 'pro',
      organization_id: 1,
      is_system_admin: false,
    },
    isLoading: false,
    isAuthenticated: true,
  }),
}));

// Mock customers API
vi.mock('@/lib/api/customers', () => ({
  customersAPI: {
    getChurnFactors: vi.fn(),
  },
}));

import { customersAPI } from '@/lib/api/customers';
import { ChurnRiskDrivers } from '@/components/customers/ChurnRiskDrivers';

const mockChurnFactors = {
  customer_email: 'john@acme.com',
  period_days: 30,
  feedback_count: 12,
  aggregated_factors: {
    sentiment: { avg_score: 12.5, max: 15, description: 'Consistently negative sentiment' },
    churn_keywords: { avg_score: 8.3, max: 15, description: 'Frequent churn language' },
    urgency: { avg_score: 7.0, max: 10, description: 'High urgency signals' },
    sentiment_trend: { avg_score: 6.0, max: 15, description: 'Declining trend' },
    frustration_keywords: { avg_score: 3.0, max: 10, description: 'Some frustration' },
    feedback_frequency: { avg_score: 2.0, max: 10, description: 'Normal frequency' },
    resolution_time: { avg_score: 1.5, max: 10, description: 'Resolved quickly' },
    pain_severity: { avg_score: 4.0, max: 10, description: 'Moderate pain' },
    feature_density: { avg_score: 0.5, max: 5, description: 'Low feature requests' },
  },
  top_risk_drivers: ['sentiment', 'churn_keywords', 'sentiment_trend'],
};

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('ChurnRiskDrivers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (customersAPI.getChurnFactors as ReturnType<typeof vi.fn>).mockResolvedValue(mockChurnFactors);
  });

  it('renders aggregated factors section with data', async () => {
    renderWithQueryClient(<ChurnRiskDrivers email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/churn risk drivers/i)).toBeInTheDocument();
    });
  });

  it('shows top 3 risk drivers as badges', async () => {
    renderWithQueryClient(<ChurnRiskDrivers email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByTestId('top-driver-sentiment')).toBeInTheDocument();
      expect(screen.getByTestId('top-driver-churn_keywords')).toBeInTheDocument();
      expect(screen.getByTestId('top-driver-sentiment_trend')).toBeInTheDocument();
    });
  });

  it('shows subtitle with feedback count', async () => {
    renderWithQueryClient(<ChurnRiskDrivers email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/based on 12 feedbacks/i)).toBeInTheDocument();
    });
  });
});
