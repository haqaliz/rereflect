import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

// Mock categories API — must be before the component import
vi.mock('@/lib/api/categories', () => ({
  categoriesAPI: {
    getHealthWeights: vi.fn(),
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    updateHealthWeights: vi.fn(),
  },
}));

import { categoriesAPI } from '@/lib/api/categories';
import { ComponentProgressBars } from '../../components/customers/ComponentProgressBars';

// Documented defaults (35/25/25/15/0)
const DEFAULT_API_WEIGHTS = { churn: 35, sentiment: 25, resolution: 25, frequency: 15, usage: 0 };

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

const defaultProps = {
  churn_risk_component: 22,
  sentiment_component: 38,
  resolution_component: 45,
  frequency_component: 30,
  usage_component: 55,
};

beforeEach(() => {
  vi.clearAllMocks();
  (categoriesAPI.getHealthWeights as ReturnType<typeof vi.fn>).mockResolvedValue(
    DEFAULT_API_WEIGHTS
  );
});

describe('ComponentProgressBars', () => {
  it('renders 5 progress bars', () => {
    const { container } = renderWithQuery(<ComponentProgressBars {...defaultProps} />);
    const bars = container.querySelectorAll('[data-testid^="progress-bar-"]');
    expect(bars).toHaveLength(5);
  });

  it('renders Churn Risk label', () => {
    renderWithQuery(<ComponentProgressBars {...defaultProps} />);
    expect(screen.getByText(/Churn Risk/i)).toBeInTheDocument();
  });

  it('renders Churn Risk weight 35% from org config (default)', async () => {
    renderWithQuery(<ComponentProgressBars {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText(/35%/)).toBeInTheDocument();
    });
  });

  it('renders Sentiment label', () => {
    renderWithQuery(<ComponentProgressBars {...defaultProps} />);
    expect(screen.getByText(/Sentiment/i)).toBeInTheDocument();
  });

  it('renders Resolution label', () => {
    renderWithQuery(<ComponentProgressBars {...defaultProps} />);
    expect(screen.getByText(/Resolution/i)).toBeInTheDocument();
  });

  it('renders Frequency label', () => {
    renderWithQuery(<ComponentProgressBars {...defaultProps} />);
    expect(screen.getByText(/Frequency/i)).toBeInTheDocument();
  });

  it('renders Frequency weight 15% from org config (default)', async () => {
    renderWithQuery(<ComponentProgressBars {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText(/15%/)).toBeInTheDocument();
    });
  });

  it('renders Usage Activity label', () => {
    renderWithQuery(<ComponentProgressBars {...defaultProps} />);
    expect(screen.getByText(/Usage Activity/i)).toBeInTheDocument();
  });

  it('renders score display e.g. "22/100"', () => {
    renderWithQuery(<ComponentProgressBars {...defaultProps} />);
    expect(screen.getByText('22/100')).toBeInTheDocument();
  });

  it('renders score display for all components', () => {
    renderWithQuery(<ComponentProgressBars {...defaultProps} />);
    expect(screen.getByText('38/100')).toBeInTheDocument();
    expect(screen.getByText('45/100')).toBeInTheDocument();
    expect(screen.getByText('30/100')).toBeInTheDocument();
    expect(screen.getByText('55/100')).toBeInTheDocument();
  });

  it('defaults usage_component to 50 when not provided', () => {
    const props = {
      churn_risk_component: 22,
      sentiment_component: 38,
      resolution_component: 45,
      frequency_component: 30,
    };
    renderWithQuery(<ComponentProgressBars {...props} />);
    expect(screen.getByText('50/100')).toBeInTheDocument();
  });

  it('uses red color for score < 30', () => {
    const { container } = renderWithQuery(
      <ComponentProgressBars
        churn_risk_component={22}
        sentiment_component={50}
        resolution_component={50}
        frequency_component={50}
        usage_component={50}
      />
    );
    const bar = container.querySelector('[data-testid="progress-bar-churn_risk"]');
    expect(bar).not.toBeNull();
    const fill = bar?.querySelector('[data-testid="progress-fill-churn_risk"]');
    expect(fill).not.toBeNull();
    expect(fill).toHaveStyle({ backgroundColor: 'var(--destructive)' });
  });

  it('uses coral color for score 30-49', () => {
    const { container } = renderWithQuery(
      <ComponentProgressBars
        churn_risk_component={35}
        sentiment_component={50}
        resolution_component={50}
        frequency_component={50}
        usage_component={50}
      />
    );
    const fill = container.querySelector('[data-testid="progress-fill-churn_risk"]');
    expect(fill).not.toBeNull();
    expect(fill).toHaveStyle({ backgroundColor: 'var(--chart-1)' });
  });

  it('uses amber color for score 50-69', () => {
    const { container } = renderWithQuery(
      <ComponentProgressBars
        churn_risk_component={60}
        sentiment_component={50}
        resolution_component={50}
        frequency_component={50}
        usage_component={50}
      />
    );
    const fill = container.querySelector('[data-testid="progress-fill-churn_risk"]');
    expect(fill).not.toBeNull();
    expect(fill).toHaveStyle({ backgroundColor: 'var(--chart-2)' });
  });

  it('uses green color for score >= 70', () => {
    const { container } = renderWithQuery(
      <ComponentProgressBars
        churn_risk_component={75}
        sentiment_component={50}
        resolution_component={50}
        frequency_component={50}
        usage_component={50}
      />
    );
    const fill = container.querySelector('[data-testid="progress-fill-churn_risk"]');
    expect(fill).not.toBeNull();
    expect(fill).toHaveStyle({ backgroundColor: 'var(--chart-5)' });
  });

  it('sets progress bar width proportional to score (22% wide for score 22)', () => {
    const { container } = renderWithQuery(<ComponentProgressBars {...defaultProps} />);
    const fill = container.querySelector('[data-testid="progress-fill-churn_risk"]');
    expect(fill).toHaveStyle({ width: '22%' });
  });

  it('renders usage progress bar data-testid', () => {
    const { container } = renderWithQuery(<ComponentProgressBars {...defaultProps} />);
    const usageBar = container.querySelector('[data-testid="progress-bar-usage"]');
    expect(usageBar).not.toBeNull();
  });

  // --- TDD: live org weights for the "· N%" display ---

  it('shows live usage weight "· 10%" when org config has usage=10', async () => {
    (categoriesAPI.getHealthWeights as ReturnType<typeof vi.fn>).mockResolvedValue({
      churn: 25,
      sentiment: 25,
      resolution: 25,
      frequency: 15,
      usage: 10,
    });
    renderWithQuery(<ComponentProgressBars {...defaultProps} />);
    await waitFor(() => {
      const usageBar = screen.getByTestId('progress-bar-usage');
      expect(usageBar).toHaveTextContent('· 10%');
    });
  });

  it('shows "· 0%" for usage weight when org config has usage=0 (default disabled)', async () => {
    (categoriesAPI.getHealthWeights as ReturnType<typeof vi.fn>).mockResolvedValue(
      DEFAULT_API_WEIGHTS
    );
    renderWithQuery(<ComponentProgressBars {...defaultProps} />);
    await waitFor(() => {
      const usageBar = screen.getByTestId('progress-bar-usage');
      expect(usageBar).toHaveTextContent('· 0%');
    });
  });

  it('falls back to documented defaults (35/25/25/15/0) when health-weights fetch fails', async () => {
    (categoriesAPI.getHealthWeights as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('network error')
    );
    renderWithQuery(<ComponentProgressBars {...defaultProps} />);
    // After the failed fetch the component renders with DEFAULT_WEIGHTS
    // Weights are shown with fallback values
    await waitFor(() => {
      const churnBar = screen.getByTestId('progress-bar-churn_risk');
      expect(churnBar).toHaveTextContent('· 35%');
    });
    const usageBar = screen.getByTestId('progress-bar-usage');
    expect(usageBar).toHaveTextContent('· 0%');
  });

  it('shows all live weights correctly when org has custom weights (usage=20)', async () => {
    (categoriesAPI.getHealthWeights as ReturnType<typeof vi.fn>).mockResolvedValue({
      churn: 30,
      sentiment: 20,
      resolution: 20,
      frequency: 10,
      usage: 20,
    });
    renderWithQuery(<ComponentProgressBars {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByTestId('progress-bar-churn_risk')).toHaveTextContent('· 30%');
      expect(screen.getByTestId('progress-bar-sentiment')).toHaveTextContent('· 20%');
      expect(screen.getByTestId('progress-bar-resolution')).toHaveTextContent('· 20%');
      expect(screen.getByTestId('progress-bar-frequency')).toHaveTextContent('· 10%');
      expect(screen.getByTestId('progress-bar-usage')).toHaveTextContent('· 20%');
    });
  });
});
