import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ChurnTimelineBadge } from '../../components/customers/ChurnTimelineBadge';

describe('ChurnTimelineBadge', () => {
  it('renders nothing when bucket is null', () => {
    const { container } = render(<ChurnTimelineBadge bucket={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when bucket is undefined', () => {
    const { container } = render(<ChurnTimelineBadge bucket={undefined} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders "Immediate" label for immediate bucket', () => {
    render(<ChurnTimelineBadge bucket="immediate" />);
    expect(screen.getByTestId('churn-timeline-badge')).toHaveTextContent('Immediate');
  });

  it('renders "Within 2 weeks" label for 2w bucket', () => {
    render(<ChurnTimelineBadge bucket="2w" />);
    expect(screen.getByTestId('churn-timeline-badge')).toHaveTextContent('Within 2 weeks');
  });

  it('renders "2–4 weeks" label for 2-4w bucket', () => {
    render(<ChurnTimelineBadge bucket="2-4w" />);
    expect(screen.getByTestId('churn-timeline-badge')).toHaveTextContent('2–4 weeks');
  });

  it('renders "1–3 months" label for 1-3m bucket', () => {
    render(<ChurnTimelineBadge bucket="1-3m" />);
    expect(screen.getByTestId('churn-timeline-badge')).toHaveTextContent('1–3 months');
  });

  it('renders "Low risk" label for low bucket', () => {
    render(<ChurnTimelineBadge bucket="low" />);
    expect(screen.getByTestId('churn-timeline-badge')).toHaveTextContent('Low risk');
  });

  it('shows AlertOctagon icon for immediate', () => {
    render(<ChurnTimelineBadge bucket="immediate" />);
    expect(screen.getByTestId('churn-timeline-icon-alert-octagon')).toBeInTheDocument();
  });

  it('shows CheckCircle icon for low', () => {
    render(<ChurnTimelineBadge bucket="low" />);
    expect(screen.getByTestId('churn-timeline-icon-check-circle')).toBeInTheDocument();
  });

  it('applies matching color class per bucket', () => {
    const { rerender } = render(<ChurnTimelineBadge bucket="immediate" />);
    expect(screen.getByTestId('churn-timeline-badge')).toHaveAttribute('data-band', 'critical');

    rerender(<ChurnTimelineBadge bucket="2w" />);
    expect(screen.getByTestId('churn-timeline-badge')).toHaveAttribute('data-band', 'high');

    rerender(<ChurnTimelineBadge bucket="2-4w" />);
    expect(screen.getByTestId('churn-timeline-badge')).toHaveAttribute('data-band', 'medium');

    rerender(<ChurnTimelineBadge bucket="1-3m" />);
    expect(screen.getByTestId('churn-timeline-badge')).toHaveAttribute('data-band', 'medium');

    rerender(<ChurnTimelineBadge bucket="low" />);
    expect(screen.getByTestId('churn-timeline-badge')).toHaveAttribute('data-band', 'low');
  });
});
