import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/analytics/churn-cohorts',
}));

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock churn-analytics API — keep real helpers, stub the fetch function
vi.mock('@/lib/api/churn-analytics', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/churn-analytics')>();
  return {
    ...actual,
    getChurnCohorts: vi.fn(),
  };
});

import { getChurnCohorts } from '@/lib/api/churn-analytics';
import ChurnCohortsPage from '../../app/(dashboard)/analytics/churn-cohorts/page';

const mockResponse = {
  dimension: 'source' as const,
  range: '30d' as const,
  cohorts: [
    {
      label: 'Direct',
      total_customers: 200,
      churned_customers: 30,
      churn_rate: 0.15,
      avg_probability: 0.42,
      top_reason_codes: [{ code: 'price', count: 15 }, { code: 'competitor', count: 10 }],
    },
    {
      label: 'Organic',
      total_customers: 150,
      churned_customers: 12,
      churn_rate: 0.08,
      avg_probability: 0.22,
      top_reason_codes: [{ code: 'no_longer_needed', count: 7 }],
    },
  ],
  grid: [
    { cohort_label: 'Direct', time_bucket: '2026-01', churn_rate: 0.15, churned_count: 30 },
    { cohort_label: 'Organic', time_bucket: '2026-01', churn_rate: 0.08, churned_count: 12 },
  ],
  overall_churn_rate: 0.12,
  total_customers: 350,
  total_churned: 42,
};

const emptyResponse = {
  ...mockResponse,
  cohorts: [],
  grid: [],
  overall_churn_rate: 0,
  total_customers: 0,
  total_churned: 0,
};

function makeAuth(plan: string) {
  return {
    user: { id: 1, email: 'test@test.com', role: 'owner', plan, organization_id: 1, is_system_admin: false },
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  };
}

describe('ChurnCohortsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue(makeAuth('business'));
    (getChurnCohorts as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);
  });

  it('renders heading and description', async () => {
    render(<ChurnCohortsPage />);
    expect(screen.getByRole('heading', { name: /churn cohorts/i })).toBeInTheDocument();
    expect(screen.getByTestId('page-description')).toBeInTheDocument();
  });

  it('shows upgrade banner for Free plan', async () => {
    mockUseAuth.mockReturnValue(makeAuth('free'));
    render(<ChurnCohortsPage />);
    expect(screen.getByTestId('upgrade-banner')).toBeInTheDocument();
  });

  it('shows upgrade banner for Pro plan', async () => {
    mockUseAuth.mockReturnValue(makeAuth('pro'));
    render(<ChurnCohortsPage />);
    expect(screen.getByTestId('upgrade-banner')).toBeInTheDocument();
  });

  it('fetches cohorts on mount with default filters (dimension=source, range=30d)', async () => {
    render(<ChurnCohortsPage />);
    await waitFor(() => {
      expect(getChurnCohorts).toHaveBeenCalledWith({ dimension: 'source', range: '30d' });
    });
  });

  it('calls API with new dimension when dropdown changes', async () => {
    const user = userEvent.setup();
    render(<ChurnCohortsPage />);
    await waitFor(() => expect(getChurnCohorts).toHaveBeenCalledTimes(1));

    await user.click(screen.getByTestId('dimension-select'));
    await user.click(await screen.findByRole('option', { name: 'Acquisition Month' }));

    await waitFor(() => {
      expect(getChurnCohorts).toHaveBeenCalledWith({ dimension: 'month', range: '30d' });
    });
  });

  it('calls API with new range when range dropdown changes', async () => {
    const user = userEvent.setup();
    render(<ChurnCohortsPage />);
    await waitFor(() => expect(getChurnCohorts).toHaveBeenCalledTimes(1));

    await user.click(screen.getByTestId('range-select'));
    await user.click(await screen.findByRole('option', { name: '90 days' }));

    await waitFor(() => {
      expect(getChurnCohorts).toHaveBeenCalledWith({ dimension: 'source', range: '90d' });
    });
  });

  it('renders overall churn rate as percentage', async () => {
    render(<ChurnCohortsPage />);
    await waitFor(() => {
      expect(screen.getByTestId('stat-overall-churn-rate')).toHaveTextContent('12%');
    });
  });

  it('renders cohort bar chart', async () => {
    render(<ChurnCohortsPage />);
    await waitFor(() => {
      expect(screen.getByTestId('cohort-bar-chart')).toBeInTheDocument();
    });
  });

  it('renders cohort heatmap', async () => {
    render(<ChurnCohortsPage />);
    await waitFor(() => {
      expect(screen.getByTestId('cohort-heatmap')).toBeInTheDocument();
    });
  });

  it('renders reason code breakdown', async () => {
    render(<ChurnCohortsPage />);
    await waitFor(() => {
      expect(screen.getByTestId('reason-code-breakdown')).toBeInTheDocument();
    });
  });

  it('shows empty state when cohorts array is empty', async () => {
    (getChurnCohorts as ReturnType<typeof vi.fn>).mockResolvedValue(emptyResponse);
    render(<ChurnCohortsPage />);
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });

  it('shows error state on API failure', async () => {
    (getChurnCohorts as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Network error'));
    render(<ChurnCohortsPage />);
    await waitFor(() => {
      expect(screen.getByTestId('error-state')).toBeInTheDocument();
    });
  });
});
