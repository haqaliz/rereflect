import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock Recharts to avoid canvas issues in jsdom
vi.mock('recharts', () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ReferenceLine: ({ y }: { y: number }) => <div data-testid={`reference-line-${y}`} />,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
}));

// Mock customers API
vi.mock('@/lib/api/customers', () => ({
  customersAPI: {
    getHistory: vi.fn(),
  },
}));

import { customersAPI } from '@/lib/api/customers';
import { HealthTimeline } from '../../components/customers/HealthTimeline';

const mockHistoryResponse = {
  history: [
    { health_score: 45, churn_risk_component: 30, sentiment_component: 40, resolution_component: 50, frequency_component: 35, risk_level: 'moderate', recorded_at: '2026-01-20T00:00:00Z' },
    { health_score: 38, churn_risk_component: 25, sentiment_component: 35, resolution_component: 45, frequency_component: 30, risk_level: 'at_risk', recorded_at: '2026-02-01T00:00:00Z' },
    { health_score: 34, churn_risk_component: 22, sentiment_component: 38, resolution_component: 45, frequency_component: 30, risk_level: 'at_risk', recorded_at: '2026-02-18T00:00:00Z' },
  ],
  period_start: '2026-01-19T00:00:00Z',
  period_end: '2026-02-18T23:59:59Z',
};

const emptyHistoryResponse = {
  history: [],
  period_start: '2026-01-19T00:00:00Z',
  period_end: '2026-02-18T23:59:59Z',
};

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe('HealthTimeline', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (customersAPI.getHistory as ReturnType<typeof vi.fn>).mockResolvedValue(mockHistoryResponse);
  });

  it('renders the chart when data is available', async () => {
    renderWithQueryClient(<HealthTimeline email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByTestId('line-chart')).toBeInTheDocument();
    });
  });

  it('renders 30d/60d/90d toggle buttons', async () => {
    renderWithQueryClient(<HealthTimeline email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText('30d')).toBeInTheDocument();
      expect(screen.getByText('60d')).toBeInTheDocument();
      expect(screen.getByText('90d')).toBeInTheDocument();
    });
  });

  it('defaults to 30d period', async () => {
    renderWithQueryClient(<HealthTimeline email="john@acme.com" />);
    await waitFor(() => {
      expect(customersAPI.getHistory).toHaveBeenCalledWith('john@acme.com', 30);
    });
  });

  it('fetches 60d data when 60d button is clicked', async () => {
    renderWithQueryClient(<HealthTimeline email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText('60d')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('60d'));
    await waitFor(() => {
      expect(customersAPI.getHistory).toHaveBeenCalledWith('john@acme.com', 60);
    });
  });

  it('fetches 90d data when 90d button is clicked', async () => {
    renderWithQueryClient(<HealthTimeline email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText('90d')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('90d'));
    await waitFor(() => {
      expect(customersAPI.getHistory).toHaveBeenCalledWith('john@acme.com', 90);
    });
  });

  it('renders reference lines at 70 and 30', async () => {
    renderWithQueryClient(<HealthTimeline email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByTestId('reference-line-70')).toBeInTheDocument();
      expect(screen.getByTestId('reference-line-30')).toBeInTheDocument();
    });
  });

  it('shows empty state when no history data', async () => {
    (customersAPI.getHistory as ReturnType<typeof vi.fn>).mockResolvedValue(emptyHistoryResponse);
    renderWithQueryClient(<HealthTimeline email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/Not enough history yet/i)).toBeInTheDocument();
    });
  });
});
