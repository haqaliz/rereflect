import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ChurnProbabilityBadge } from '../../components/customers/ChurnProbabilityBadge';

describe('ChurnProbabilityBadge', () => {
  it('renders percentage rounded to whole number', () => {
    render(<ChurnProbabilityBadge probability={0.456} />);
    expect(screen.getByTestId('churn-probability-badge')).toHaveTextContent('46%');
  });

  it('renders 0% when probability is 0', () => {
    render(<ChurnProbabilityBadge probability={0} />);
    expect(screen.getByTestId('churn-probability-badge')).toHaveTextContent('0%');
  });

  it('renders 100% when probability is 1', () => {
    render(<ChurnProbabilityBadge probability={1} />);
    expect(screen.getByTestId('churn-probability-badge')).toHaveTextContent('100%');
  });

  it('renders neutral dash when probability is undefined', () => {
    render(<ChurnProbabilityBadge probability={undefined as unknown as number} />);
    expect(screen.getByTestId('churn-probability-badge')).toHaveTextContent('—');
  });

  it('renders neutral dash when probability is null', () => {
    render(<ChurnProbabilityBadge probability={null as unknown as number} />);
    expect(screen.getByTestId('churn-probability-badge')).toHaveTextContent('—');
  });

  it('applies red color class when probability >= 0.70', () => {
    render(<ChurnProbabilityBadge probability={0.75} />);
    const badge = screen.getByTestId('churn-probability-badge');
    expect(badge).toHaveAttribute('data-band', 'critical');
  });

  it('applies orange color class when probability is 0.50 <= p < 0.70', () => {
    render(<ChurnProbabilityBadge probability={0.60} />);
    const badge = screen.getByTestId('churn-probability-badge');
    expect(badge).toHaveAttribute('data-band', 'high');
  });

  it('applies yellow color class when probability is 0.30 <= p < 0.50', () => {
    render(<ChurnProbabilityBadge probability={0.40} />);
    const badge = screen.getByTestId('churn-probability-badge');
    expect(badge).toHaveAttribute('data-band', 'medium');
  });

  it('applies green color class when probability < 0.30', () => {
    render(<ChurnProbabilityBadge probability={0.20} />);
    const badge = screen.getByTestId('churn-probability-badge');
    expect(badge).toHaveAttribute('data-band', 'low');
  });

  it('tooltip shows CI when low and high provided', () => {
    render(
      <ChurnProbabilityBadge
        probability={0.55}
        probabilityLow={0.40}
        probabilityHigh={0.70}
        showTooltip
      />
    );
    const tooltip = screen.getByTestId('churn-probability-tooltip');
    expect(tooltip).toHaveTextContent('40%');
    expect(tooltip).toHaveTextContent('70%');
  });

  it('tooltip includes label count when provided', () => {
    render(
      <ChurnProbabilityBadge
        probability={0.55}
        probabilityLow={0.40}
        probabilityHigh={0.70}
        labelCount={120}
        showTooltip
      />
    );
    const tooltip = screen.getByTestId('churn-probability-tooltip');
    expect(tooltip).toHaveTextContent('120');
  });

  it('tooltip hidden when showTooltip is false', () => {
    render(
      <ChurnProbabilityBadge
        probability={0.55}
        probabilityLow={0.40}
        probabilityHigh={0.70}
        showTooltip={false}
      />
    );
    expect(screen.queryByTestId('churn-probability-tooltip')).not.toBeInTheDocument();
  });

  it('accepts sm/md/lg sizes and applies size class', () => {
    const { rerender } = render(<ChurnProbabilityBadge probability={0.5} size="sm" />);
    expect(screen.getByTestId('churn-probability-badge')).toHaveAttribute('data-size', 'sm');

    rerender(<ChurnProbabilityBadge probability={0.5} size="lg" />);
    expect(screen.getByTestId('churn-probability-badge')).toHaveAttribute('data-size', 'lg');
  });

  it('respects className prop', () => {
    render(<ChurnProbabilityBadge probability={0.5} className="my-custom-class" />);
    expect(screen.getByTestId('churn-probability-badge')).toHaveClass('my-custom-class');
  });
});
