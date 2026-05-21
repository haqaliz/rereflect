import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CohortHeatmap } from '../../components/analytics/CohortHeatmap';
import type { CohortGridCell } from '../../lib/api/churn-analytics';

const makeCell = (
  cohort_label: string,
  time_bucket: string,
  churn_rate: number,
  churned_count = 5,
): CohortGridCell => ({ cohort_label, time_bucket, churn_rate, churned_count });

describe('CohortHeatmap', () => {
  it('renders empty state when grid is empty', () => {
    render(<CohortHeatmap grid={[]} />);
    expect(screen.getByTestId('cohort-heatmap-empty')).toBeInTheDocument();
  });

  it('renders one cell per (cohort, time_bucket) combination', () => {
    const grid: CohortGridCell[] = [
      makeCell('Direct', '2026-01', 0.1),
      makeCell('Direct', '2026-02', 0.2),
      makeCell('Organic', '2026-01', 0.3),
      makeCell('Organic', '2026-02', 0.4),
    ];
    render(<CohortHeatmap grid={grid} />);
    const cells = screen.getAllByTestId('heatmap-cell');
    expect(cells).toHaveLength(4);
  });

  it('applies color attribute based on churn_rate band', () => {
    const grid: CohortGridCell[] = [
      makeCell('Direct', '2026-01', 0.8),  // critical
      makeCell('Organic', '2026-01', 0.6), // high
      makeCell('Referral', '2026-01', 0.4), // medium
      makeCell('Social', '2026-01', 0.1),  // low
    ];
    render(<CohortHeatmap grid={grid} />);
    const cells = screen.getAllByTestId('heatmap-cell');
    expect(cells[0]).toHaveAttribute('data-band', 'critical');
    expect(cells[1]).toHaveAttribute('data-band', 'high');
    expect(cells[2]).toHaveAttribute('data-band', 'medium');
    expect(cells[3]).toHaveAttribute('data-band', 'low');
  });

  it('shows tooltip with churn rate and count on hover', () => {
    const grid: CohortGridCell[] = [makeCell('Direct', '2026-01', 0.25, 10)];
    render(<CohortHeatmap grid={grid} />);
    const cell = screen.getByTestId('heatmap-cell');
    fireEvent.mouseEnter(cell);
    expect(screen.getByTestId('heatmap-tooltip')).toBeInTheDocument();
    expect(screen.getByTestId('heatmap-tooltip')).toHaveTextContent('25%');
    expect(screen.getByTestId('heatmap-tooltip')).toHaveTextContent('10');
  });

  it('handles single-cohort single-time-bucket gracefully', () => {
    const grid: CohortGridCell[] = [makeCell('Direct', '2026-01', 0.5, 3)];
    render(<CohortHeatmap grid={grid} />);
    expect(screen.getAllByTestId('heatmap-cell')).toHaveLength(1);
  });

  it('sorts cohorts in a stable order (alphabetical)', () => {
    const grid: CohortGridCell[] = [
      makeCell('Zebra', '2026-01', 0.1),
      makeCell('Alpha', '2026-01', 0.2),
      makeCell('Middle', '2026-01', 0.3),
    ];
    render(<CohortHeatmap grid={grid} />);
    const headers = screen.getAllByTestId('heatmap-row-label');
    expect(headers[0]).toHaveTextContent('Alpha');
    expect(headers[1]).toHaveTextContent('Middle');
    expect(headers[2]).toHaveTextContent('Zebra');
  });

  it('sorts time buckets chronologically ascending', () => {
    const grid: CohortGridCell[] = [
      makeCell('Direct', '2026-03', 0.1),
      makeCell('Direct', '2026-01', 0.2),
      makeCell('Direct', '2026-02', 0.3),
    ];
    render(<CohortHeatmap grid={grid} />);
    const colHeaders = screen.getAllByTestId('heatmap-col-label');
    expect(colHeaders[0]).toHaveTextContent('2026-01');
    expect(colHeaders[1]).toHaveTextContent('2026-02');
    expect(colHeaders[2]).toHaveTextContent('2026-03');
  });
});
