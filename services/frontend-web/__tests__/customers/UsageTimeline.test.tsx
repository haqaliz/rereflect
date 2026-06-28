import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

// Mock the API
vi.mock('@/lib/api/customers', () => ({
  customersAPI: {
    getUsage: vi.fn(),
  },
}));

// Mock Recharts to avoid SVG/canvas issues in jsdom
vi.mock('recharts', () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
}));

import { customersAPI } from '@/lib/api/customers';
import { UsageTimeline } from '../../components/customers/UsageTimeline';

const mockGetUsage = customersAPI.getUsage as ReturnType<typeof vi.fn>;

const mockUsageWithSeries = {
  email: 'alice@acme.com',
  last_active_at: '2026-06-28T08:00:00Z',
  login_count_7d: 5,
  login_count_30d: 18,
  active_days_30d: 14,
  distinct_feature_count: 6,
  usage_score: 72,
  period_days: 30,
  series: [
    { date: '2026-06-01', events: 4 },
    { date: '2026-06-02', events: 7 },
    { date: '2026-06-03', events: 2 },
  ],
};

const mockUsageEmpty = {
  ...mockUsageWithSeries,
  series: [],
};

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe('UsageTimeline', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders period toggle buttons (30d, 60d, 90d)', async () => {
    mockGetUsage.mockResolvedValue(mockUsageWithSeries);
    renderWithQueryClient(<UsageTimeline email="alice@acme.com" />);
    expect(screen.getByText('30d')).toBeInTheDocument();
    expect(screen.getByText('60d')).toBeInTheDocument();
    expect(screen.getByText('90d')).toBeInTheDocument();
  });

  it('renders chart when series data is present', async () => {
    mockGetUsage.mockResolvedValue(mockUsageWithSeries);
    renderWithQueryClient(<UsageTimeline email="alice@acme.com" />);
    await waitFor(() => {
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  it('renders empty state when series is empty', async () => {
    mockGetUsage.mockResolvedValue(mockUsageEmpty);
    renderWithQueryClient(<UsageTimeline email="alice@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/no usage events/i)).toBeInTheDocument();
    });
  });

  it('calls getUsage with default 30 days', async () => {
    mockGetUsage.mockResolvedValue(mockUsageWithSeries);
    renderWithQueryClient(<UsageTimeline email="alice@acme.com" />);
    await waitFor(() => {
      expect(mockGetUsage).toHaveBeenCalledWith('alice@acme.com', 30);
    });
  });

  it('refetches with new period on toggle click', async () => {
    mockGetUsage.mockResolvedValue(mockUsageWithSeries);
    renderWithQueryClient(<UsageTimeline email="alice@acme.com" />);
    await waitFor(() => {
      expect(mockGetUsage).toHaveBeenCalledWith('alice@acme.com', 30);
    });

    fireEvent.click(screen.getByText('60d'));
    await waitFor(() => {
      expect(mockGetUsage).toHaveBeenCalledWith('alice@acme.com', 60);
    });
  });

  it('shows the header label', async () => {
    mockGetUsage.mockResolvedValue(mockUsageWithSeries);
    renderWithQueryClient(<UsageTimeline email="alice@acme.com" />);
    expect(screen.getByText(/product usage over time/i)).toBeInTheDocument();
  });

  it('handles 404/error from getUsage gracefully (empty state)', async () => {
    mockGetUsage.mockRejectedValue(Object.assign(new Error('Not Found'), { response: { status: 404 } }));
    renderWithQueryClient(<UsageTimeline email="alice@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/no usage events/i)).toBeInTheDocument();
    });
  });
});
