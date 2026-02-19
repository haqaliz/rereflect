import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HealthScoreCircle } from '../../components/customers/HealthScoreCircle';

describe('HealthScoreCircle', () => {
  it('renders the score number', () => {
    render(<HealthScoreCircle score={75} />);
    expect(screen.getByText('75')).toBeInTheDocument();
  });

  it('applies green color for score >= 70', () => {
    const { container } = render(<HealthScoreCircle score={70} />);
    const circle = container.firstChild as HTMLElement;
    expect(circle).toHaveStyle({ color: 'var(--chart-5)' });
  });

  it('applies amber color for score 50-69', () => {
    const { container } = render(<HealthScoreCircle score={60} />);
    const circle = container.firstChild as HTMLElement;
    expect(circle).toHaveStyle({ color: 'var(--chart-2)' });
  });

  it('applies coral color for score 30-49', () => {
    const { container } = render(<HealthScoreCircle score={40} />);
    const circle = container.firstChild as HTMLElement;
    expect(circle).toHaveStyle({ color: 'var(--chart-1)' });
  });

  it('applies red color for score < 30', () => {
    const { container } = render(<HealthScoreCircle score={20} />);
    const circle = container.firstChild as HTMLElement;
    expect(circle).toHaveStyle({ color: 'var(--destructive)' });
  });

  it('applies correct color at boundary score 50', () => {
    const { container } = render(<HealthScoreCircle score={50} />);
    const circle = container.firstChild as HTMLElement;
    expect(circle).toHaveStyle({ color: 'var(--chart-2)' });
  });

  it('applies correct color at boundary score 30', () => {
    const { container } = render(<HealthScoreCircle score={30} />);
    const circle = container.firstChild as HTMLElement;
    expect(circle).toHaveStyle({ color: 'var(--chart-1)' });
  });

  it('accepts an optional size prop', () => {
    render(<HealthScoreCircle score={55} size="lg" />);
    expect(screen.getByText('55')).toBeInTheDocument();
  });
});
