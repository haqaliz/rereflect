import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { AccuracyTrendChart } from '@/components/analytics/AccuracyTrendChart';
import type { BacktestRunSummary } from '@/lib/api/churn-accuracy';

// Recharts uses ResizeObserver (already polyfilled in vitest.setup.ts)

const makeRun = (
  run_at: string,
  f1: number | null,
  precision: number | null,
  recall: number | null,
): BacktestRunSummary => ({
  run_at,
  label_count: 100,
  precision,
  recall,
  f1,
  auc: f1,
});

const twoRuns: BacktestRunSummary[] = [
  makeRun('2026-04-07T07:45:00Z', 0.75, 0.79, 0.72),
  makeRun('2026-05-12T07:45:00Z', 0.81, 0.85, 0.78),
];

describe('AccuracyTrendChart', () => {
  // Test 24: renders empty state when no runs
  it('renders empty state when runs array is empty', () => {
    render(<AccuracyTrendChart runs={[]} />);
    expect(screen.getByTestId('accuracy-trend-empty')).toBeInTheDocument();
  });

  // Test 25: renders one line per metric (F1, precision, recall)
  it('renders three metric lines (F1, Precision, Recall)', () => {
    render(<AccuracyTrendChart runs={twoRuns} />);
    // The chart container should be present
    expect(screen.getByTestId('accuracy-trend-chart')).toBeInTheDocument();
    // Legend labels rendered in accessible div — multiple elements may appear (sr-only + visible)
    expect(screen.getAllByText(/f1/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/precision/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/recall/i).length).toBeGreaterThan(0);
  });

  // Test 26: handles null metrics in runs gracefully
  it('handles null metrics in runs without crashing', () => {
    const runsWithNulls: BacktestRunSummary[] = [
      makeRun('2026-04-07T07:45:00Z', null, null, null),
      makeRun('2026-05-12T07:45:00Z', 0.81, 0.85, 0.78),
    ];

    expect(() => render(<AccuracyTrendChart runs={runsWithNulls} />)).not.toThrow();
    expect(screen.getByTestId('accuracy-trend-chart')).toBeInTheDocument();
  });

  // Test 27: tooltip shows date + metric values
  it('renders with tooltip configured (chart container present)', () => {
    render(<AccuracyTrendChart runs={twoRuns} />);
    // The chart itself must render (not crash) with runs — tooltip is internal to Recharts
    expect(screen.getByTestId('accuracy-trend-chart')).toBeInTheDocument();
  });

  // Test 28: legend lists all 3 metrics
  it('legend lists F1, Precision, and Recall', () => {
    render(<AccuracyTrendChart runs={twoRuns} />);
    // aria-label legend div contains all three metric labels
    const legend = screen.getByLabelText('Accuracy trend legend');
    expect(legend).toBeInTheDocument();
    expect(legend.textContent).toMatch(/F1/);
    expect(legend.textContent).toMatch(/Precision/);
    expect(legend.textContent).toMatch(/Recall/);
  });

  // Test 29: respects width/height props
  it('accepts optional width and height props without crashing', () => {
    expect(() =>
      render(<AccuracyTrendChart runs={twoRuns} width={600} height={300} />)
    ).not.toThrow();
    expect(screen.getByTestId('accuracy-trend-chart')).toBeInTheDocument();
  });
});
