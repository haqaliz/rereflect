import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ComponentProgressBars } from '../../components/customers/ComponentProgressBars';

const defaultProps = {
  churn_risk_component: 22,
  sentiment_component: 38,
  resolution_component: 45,
  frequency_component: 30,
};

describe('ComponentProgressBars', () => {
  it('renders 4 progress bars', () => {
    const { container } = render(<ComponentProgressBars {...defaultProps} />);
    const bars = container.querySelectorAll('[data-testid^="progress-bar-"]');
    expect(bars).toHaveLength(4);
  });

  it('renders Churn Risk label with weight 35%', () => {
    render(<ComponentProgressBars {...defaultProps} />);
    expect(screen.getByText(/Churn Risk/i)).toBeInTheDocument();
    expect(screen.getByText(/35%/)).toBeInTheDocument();
  });

  it('renders Sentiment label with weight 25%', () => {
    render(<ComponentProgressBars {...defaultProps} />);
    expect(screen.getByText(/Sentiment/i)).toBeInTheDocument();
  });

  it('renders Resolution label with weight 25%', () => {
    render(<ComponentProgressBars {...defaultProps} />);
    expect(screen.getByText(/Resolution/i)).toBeInTheDocument();
  });

  it('renders Frequency label with weight 15%', () => {
    render(<ComponentProgressBars {...defaultProps} />);
    expect(screen.getByText(/Frequency/i)).toBeInTheDocument();
    expect(screen.getByText(/15%/)).toBeInTheDocument();
  });

  it('renders score display e.g. "22/100"', () => {
    render(<ComponentProgressBars {...defaultProps} />);
    expect(screen.getByText('22/100')).toBeInTheDocument();
  });

  it('renders score display for all components', () => {
    render(<ComponentProgressBars {...defaultProps} />);
    expect(screen.getByText('38/100')).toBeInTheDocument();
    expect(screen.getByText('45/100')).toBeInTheDocument();
    expect(screen.getByText('30/100')).toBeInTheDocument();
  });

  it('uses red color for score < 30', () => {
    const { container } = render(
      <ComponentProgressBars
        churn_risk_component={22}
        sentiment_component={50}
        resolution_component={50}
        frequency_component={50}
      />
    );
    const bar = container.querySelector('[data-testid="progress-bar-churn_risk"]');
    expect(bar).not.toBeNull();
    // The bar fill should have the destructive color
    const fill = bar?.querySelector('[data-testid="progress-fill-churn_risk"]');
    expect(fill).not.toBeNull();
    expect(fill).toHaveStyle({ backgroundColor: 'var(--destructive)' });
  });

  it('uses coral color for score 30-49', () => {
    const { container } = render(
      <ComponentProgressBars
        churn_risk_component={35}
        sentiment_component={50}
        resolution_component={50}
        frequency_component={50}
      />
    );
    const fill = container.querySelector('[data-testid="progress-fill-churn_risk"]');
    expect(fill).not.toBeNull();
    expect(fill).toHaveStyle({ backgroundColor: 'var(--chart-1)' });
  });

  it('uses amber color for score 50-69', () => {
    const { container } = render(
      <ComponentProgressBars
        churn_risk_component={60}
        sentiment_component={50}
        resolution_component={50}
        frequency_component={50}
      />
    );
    const fill = container.querySelector('[data-testid="progress-fill-churn_risk"]');
    expect(fill).not.toBeNull();
    expect(fill).toHaveStyle({ backgroundColor: 'var(--chart-2)' });
  });

  it('uses green color for score >= 70', () => {
    const { container } = render(
      <ComponentProgressBars
        churn_risk_component={75}
        sentiment_component={50}
        resolution_component={50}
        frequency_component={50}
      />
    );
    const fill = container.querySelector('[data-testid="progress-fill-churn_risk"]');
    expect(fill).not.toBeNull();
    expect(fill).toHaveStyle({ backgroundColor: 'var(--chart-5)' });
  });

  it('sets progress bar width proportional to score (22% wide for score 22)', () => {
    const { container } = render(<ComponentProgressBars {...defaultProps} />);
    const fill = container.querySelector('[data-testid="progress-fill-churn_risk"]');
    expect(fill).toHaveStyle({ width: '22%' });
  });
});
