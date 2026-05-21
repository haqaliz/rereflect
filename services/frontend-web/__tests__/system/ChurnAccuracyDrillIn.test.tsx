import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => ({ orgId: '10' }),
}));

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock churn-accuracy API — include formatMetricPercent so components can import it
vi.mock('@/lib/api/churn-accuracy', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/churn-accuracy')>();
  return {
    ...actual,
    getOrgAccuracyHistory: vi.fn(),
    getSystemAccuracy: vi.fn(),
    getAccuracyCard: vi.fn(),
  };
});

// Mock AccuracyTrendChart since it uses Recharts (complex to render in jsdom)
vi.mock('@/components/analytics/AccuracyTrendChart', () => ({
  AccuracyTrendChart: ({ runs }: { runs: unknown[] }) => (
    <div data-testid="accuracy-trend-chart" data-run-count={runs.length} />
  ),
}));

import { getOrgAccuracyHistory } from '@/lib/api/churn-accuracy';
import ChurnAccuracyDrillInPage from '@/app/(dashboard)/system/churn-accuracy/[orgId]/page';

const systemAdminUser = {
  id: 1,
  email: 'admin@system.com',
  role: 'owner',
  plan: 'enterprise',
  organization_id: 1,
  is_system_admin: true,
};

const regularUser = { ...systemAdminUser, is_system_admin: false };

const mockOrgHistory = {
  organization_id: 10,
  organization_name: 'Acme Corp',
  models: [
    {
      id: 5,
      is_active: true,
      label_count: 300,
      positive_count: 80,
      precision: 0.85,
      recall: 0.78,
      f1: 0.81,
      auc: 0.88,
      fit_at: '2026-05-12T07:45:00Z',
      threshold_bands: { low: 0.3, medium: 0.5, high: 0.7, critical: 0.85 },
    },
    {
      id: 3,
      is_active: false,
      label_count: 220,
      positive_count: 60,
      precision: 0.79,
      recall: 0.72,
      f1: 0.75,
      auc: 0.82,
      fit_at: '2026-04-07T07:45:00Z',
      threshold_bands: { low: 0.3, medium: 0.5, high: 0.7, critical: 0.85 },
    },
  ],
  backtest_runs: [
    {
      run_at: '2026-05-12T07:45:00Z',
      label_count: 300,
      precision: 0.85,
      recall: 0.78,
      f1: 0.81,
      auc: 0.88,
    },
    {
      run_at: '2026-04-07T07:45:00Z',
      label_count: 220,
      precision: 0.79,
      recall: 0.72,
      f1: 0.75,
      auc: 0.82,
    },
  ],
};

describe('ChurnAccuracyDrillInPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Test 18: redirects non-system-admin users
  it('redirects non-system-admin users to /dashboard', async () => {
    mockUseAuth.mockReturnValue({ user: regularUser });
    vi.mocked(getOrgAccuracyHistory).mockResolvedValue(mockOrgHistory);

    render(<ChurnAccuracyDrillInPage />);

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/dashboard');
    });
  });

  // Test 19: fetches and renders org history on mount
  it('fetches org history and renders org name on mount', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    vi.mocked(getOrgAccuracyHistory).mockResolvedValue(mockOrgHistory);

    render(<ChurnAccuracyDrillInPage />);

    await waitFor(() => {
      expect(getOrgAccuracyHistory).toHaveBeenCalledWith(10);
      expect(screen.getByText(/Acme Corp/)).toBeInTheDocument();
    });
  });

  // Test 20: renders AccuracyTrendChart with backtest_runs data
  it('renders AccuracyTrendChart with backtest_runs data', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    vi.mocked(getOrgAccuracyHistory).mockResolvedValue(mockOrgHistory);

    render(<ChurnAccuracyDrillInPage />);

    await waitFor(() => {
      const chart = screen.getByTestId('accuracy-trend-chart');
      expect(chart).toBeInTheDocument();
      expect(chart).toHaveAttribute('data-run-count', '2');
    });
  });

  // Test 21: renders model version history table
  it('renders model version history table with both models', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    vi.mocked(getOrgAccuracyHistory).mockResolvedValue(mockOrgHistory);

    render(<ChurnAccuracyDrillInPage />);

    await waitFor(() => {
      // Two model rows should be present — check by label count
      expect(screen.getByText('300')).toBeInTheDocument();
      expect(screen.getByText('220')).toBeInTheDocument();
    });
  });

  // Test 22: shows "active" badge on the active model
  it('shows an "Active" badge on the currently active model', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    vi.mocked(getOrgAccuracyHistory).mockResolvedValue(mockOrgHistory);

    render(<ChurnAccuracyDrillInPage />);

    await waitFor(() => {
      expect(screen.getByText(/^Active$/i)).toBeInTheDocument();
    });
  });

  // Test 23: error state on API failure
  it('shows error state when API call fails', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    vi.mocked(getOrgAccuracyHistory).mockRejectedValue(new Error('Not found'));

    render(<ChurnAccuracyDrillInPage />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    });
  });
});
