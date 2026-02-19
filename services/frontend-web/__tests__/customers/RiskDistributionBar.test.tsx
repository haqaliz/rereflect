import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { RiskDistributionBar } from '../../components/customers/RiskDistributionBar';

const defaultDistribution = {
  healthy: 89,
  moderate: 38,
  at_risk: 22,
  critical: 7,
};

describe('RiskDistributionBar', () => {
  it('renders 4 colored segments', () => {
    const { container } = render(
      <RiskDistributionBar distribution={defaultDistribution} total={156} />
    );
    const segments = container.querySelectorAll('[data-testid^="bar-segment-"]');
    expect(segments).toHaveLength(4);
  });

  it('renders healthy percentage label', () => {
    render(<RiskDistributionBar distribution={defaultDistribution} total={156} />);
    // 89/156 ≈ 57%
    expect(screen.getByText(/Healthy/i)).toBeInTheDocument();
  });

  it('renders moderate percentage label', () => {
    render(<RiskDistributionBar distribution={defaultDistribution} total={156} />);
    expect(screen.getByText(/Moderate/i)).toBeInTheDocument();
  });

  it('renders at_risk percentage label', () => {
    render(<RiskDistributionBar distribution={defaultDistribution} total={156} />);
    expect(screen.getByText(/At Risk/i)).toBeInTheDocument();
  });

  it('renders critical percentage label', () => {
    render(<RiskDistributionBar distribution={defaultDistribution} total={156} />);
    expect(screen.getByText(/Critical/i)).toBeInTheDocument();
  });

  it('calls onFilterChange with "healthy" when healthy segment is clicked', () => {
    const onFilterChange = vi.fn();
    const { container } = render(
      <RiskDistributionBar
        distribution={defaultDistribution}
        total={156}
        onFilterChange={onFilterChange}
      />
    );
    const healthySegment = container.querySelector('[data-segment="healthy"]');
    expect(healthySegment).not.toBeNull();
    fireEvent.click(healthySegment!);
    expect(onFilterChange).toHaveBeenCalledWith('healthy');
  });

  it('calls onFilterChange with "critical" when critical segment is clicked', () => {
    const onFilterChange = vi.fn();
    const { container } = render(
      <RiskDistributionBar
        distribution={defaultDistribution}
        total={156}
        onFilterChange={onFilterChange}
      />
    );
    const criticalSegment = container.querySelector('[data-segment="critical"]');
    expect(criticalSegment).not.toBeNull();
    fireEvent.click(criticalSegment!);
    expect(onFilterChange).toHaveBeenCalledWith('critical');
  });

  it('renders count numbers for each segment', () => {
    render(<RiskDistributionBar distribution={defaultDistribution} total={156} />);
    expect(screen.getByText('89')).toBeInTheDocument();
    expect(screen.getByText('38')).toBeInTheDocument();
    expect(screen.getByText('22')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
  });
});
