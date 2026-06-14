import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

// Mock AI settings API
vi.mock('@/lib/api/ai-settings', () => ({
  aiSettingsAPI: {
    getUsage: vi.fn(),
    getUsageDaily: vi.fn(),
  },
}));

// Mock Recharts so we don't need canvas in tests
vi.mock('recharts', () => ({
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="bar-chart">{children}</div>
  ),
  Bar: () => <div data-testid="bar" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  Legend: () => <div data-testid="legend" />,
}));

import { aiSettingsAPI } from '@/lib/api/ai-settings';
import { AISettingsUsage } from '@/components/settings/AISettingsUsage';

const mockUsage = {
  month: '2026-02',
  total_tokens: 125400,
  total_requests: 342,
  estimated_cost_cents: 123,
  by_provider: [
    { provider: 'openai', tokens: 85000, requests: 250, cost_cents: 90 },
    { provider: 'anthropic', tokens: 40400, requests: 92, cost_cents: 33 },
  ],
  fallback_count: 3,
};

const mockDaily = {
  days: [
    { date: '2026-02-01', tokens: 5200, requests: 15, cost_cents: 5 },
    { date: '2026-02-02', tokens: 4800, requests: 12, cost_cents: 4 },
    { date: '2026-02-03', tokens: 6100, requests: 18, cost_cents: 6 },
  ],
};

describe('AISettingsUsage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(aiSettingsAPI.getUsage).mockResolvedValue(mockUsage);
    vi.mocked(aiSettingsAPI.getUsageDaily).mockResolvedValue(mockDaily);
  });

  it('shows stat cards with total tokens', async () => {
    render(<AISettingsUsage />);
    await waitFor(() => {
      expect(screen.getByText(/125,400|125400/)).toBeInTheDocument();
    });
  });

  it('shows stat cards with total requests', async () => {
    render(<AISettingsUsage />);
    await waitFor(() => {
      expect(screen.getByText(/342/)).toBeInTheDocument();
    });
  });

  it('shows estimated cost stat card', async () => {
    render(<AISettingsUsage />);
    await waitFor(() => {
      // $1.23 (123 cents)
      expect(screen.getByText(/\$1\.23/)).toBeInTheDocument();
    });
  });

  it('renders daily bar chart', async () => {
    render(<AISettingsUsage />);
    await waitFor(() => {
      expect(screen.getByTestId('bar-chart')).toBeInTheDocument();
    });
  });

  it('shows provider breakdown table', async () => {
    render(<AISettingsUsage />);
    await waitFor(() => {
      expect(screen.getByText('openai')).toBeInTheDocument();
      expect(screen.getByText('anthropic')).toBeInTheDocument();
    });
  });

  it('shows fallback count', async () => {
    render(<AISettingsUsage />);
    await waitFor(() => {
      expect(screen.getByText(/3.*fallback|fallback.*3/i)).toBeInTheDocument();
    });
  });

  it('shows provider token breakdown in table', async () => {
    render(<AISettingsUsage />);
    await waitFor(() => {
      expect(screen.getByText(/85,000|85000/)).toBeInTheDocument();
      expect(screen.getByText(/40,400|40400/)).toBeInTheDocument();
    });
  });

  it('always loads usage data (no plan gate)', async () => {
    render(<AISettingsUsage />);
    await waitFor(() => {
      expect(aiSettingsAPI.getUsage).toHaveBeenCalled();
    });
  });
});
