import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => ({}),
}));

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock churn-accuracy API — include formatMetricPercent so the component can import it
vi.mock('@/lib/api/churn-accuracy', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/churn-accuracy')>();
  return {
    ...actual,
    getAccuracyCard: vi.fn(),
  };
});

import { getAccuracyCard } from '@/lib/api/churn-accuracy';
import { ModelAccuracyCard } from '@/components/dashboard/widgets/ModelAccuracyCard';

const systemAdminUser = {
  id: 1,
  email: 'admin@system.com',
  role: 'owner',
  plan: 'enterprise',
  organization_id: 1,
  is_system_admin: true,
};

const regularUser = { ...systemAdminUser, is_system_admin: false };

const fullMetricsResponse = {
  model_id: 42,
  label_count: 142,
  positive_count: 38,
  precision: 0.73,
  recall: 0.81,
  f1: 0.77,
  auc: 0.84,
  fit_at: '2026-05-01T07:45:00Z',
  is_global_fallback: false,
  history: [],
};

const globalFallbackResponse = {
  ...fullMetricsResponse,
  is_global_fallback: true,
};

const nullMetricsResponse = {
  model_id: null,
  label_count: 5,
  positive_count: 1,
  precision: null,
  recall: null,
  f1: null,
  auc: null,
  fit_at: null,
  is_global_fallback: true,
  history: [],
};

describe('ModelAccuracyCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Test 1: renders precision/recall/label_count when all metrics provided
  it('renders precision, recall and label count when all metrics are provided', async () => {
    mockUseAuth.mockReturnValue({ user: regularUser });
    vi.mocked(getAccuracyCard).mockResolvedValue(fullMetricsResponse);

    render(<ModelAccuracyCard />);

    await waitFor(() => {
      expect(screen.getByText(/73%/)).toBeInTheDocument();
      expect(screen.getByText(/81%/)).toBeInTheDocument();
      expect(screen.getByText(/142/)).toBeInTheDocument();
    });
  });

  // Test 2: shows global-fallback hint when is_global_fallback is true
  it('shows global-fallback hint when is_global_fallback is true', async () => {
    mockUseAuth.mockReturnValue({ user: regularUser });
    vi.mocked(getAccuracyCard).mockResolvedValue(globalFallbackResponse);

    render(<ModelAccuracyCard />);

    await waitFor(() => {
      expect(screen.getByText(/using global model/i)).toBeInTheDocument();
      expect(screen.getByText(/mark customers as churned/i)).toBeInTheDocument();
    });
  });

  // Test 3: shows empty-state message when all metrics null
  it('shows empty-state message when all metrics are null', async () => {
    mockUseAuth.mockReturnValue({ user: regularUser });
    vi.mocked(getAccuracyCard).mockResolvedValue(nullMetricsResponse);

    render(<ModelAccuracyCard />);

    await waitFor(() => {
      expect(screen.getByText(/no labeled outcomes yet/i)).toBeInTheDocument();
      expect(screen.getByText(/start labeling/i)).toBeInTheDocument();
    });
  });

  // Test 4: shows label count even when metrics null
  it('shows label count even when metrics are null', async () => {
    mockUseAuth.mockReturnValue({ user: regularUser });
    vi.mocked(getAccuracyCard).mockResolvedValue(nullMetricsResponse);

    render(<ModelAccuracyCard />);

    await waitFor(() => {
      expect(screen.getByText(/5/)).toBeInTheDocument();
    });
  });

  // Test 5: links to /system/churn-accuracy for system admins
  it('renders a link to /system/churn-accuracy for system admins', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    vi.mocked(getAccuracyCard).mockResolvedValue(fullMetricsResponse);

    render(<ModelAccuracyCard />);

    await waitFor(() => {
      const link = screen.getByRole('link');
      expect(link).toHaveAttribute('href', '/system/churn-accuracy');
    });
  });

  // Test 6: does not link for non-admins
  it('does not render a /system/churn-accuracy link for non-admin users', async () => {
    mockUseAuth.mockReturnValue({ user: regularUser });
    vi.mocked(getAccuracyCard).mockResolvedValue(fullMetricsResponse);

    render(<ModelAccuracyCard />);

    await waitFor(() => {
      expect(screen.getByText(/73%/)).toBeInTheDocument();
    });

    const link = screen.queryByRole('link', { name: /churn accuracy/i });
    expect(link).toBeNull();
  });

  // Test 7: handles error state on API failure
  it('shows error state when API call fails', async () => {
    mockUseAuth.mockReturnValue({ user: regularUser });
    vi.mocked(getAccuracyCard).mockRejectedValue(new Error('Network error'));

    render(<ModelAccuracyCard />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    });
  });

  // Test 8: shows loading skeleton while fetching
  it('shows loading skeleton while fetching data', () => {
    mockUseAuth.mockReturnValue({ user: regularUser });
    // Never resolves during this test
    vi.mocked(getAccuracyCard).mockReturnValue(new Promise(() => {}));

    render(<ModelAccuracyCard />);

    expect(screen.getByTestId('accuracy-card-skeleton')).toBeInTheDocument();
  });
});
