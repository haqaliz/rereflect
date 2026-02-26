import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

import ImpactMetrics from '@/components/landing/ImpactMetrics';

describe('ImpactMetrics', () => {
  // Section structure
  it('renders section with "Real Impact" badge', () => {
    render(<ImpactMetrics />);
    expect(screen.getByText('Real Impact')).toBeInTheDocument();
  });

  it('renders section heading', () => {
    render(<ImpactMetrics />);
    const heading = screen.getByRole('heading', { level: 2 });
    expect(heading).toBeInTheDocument();
  });

  // Card 1
  it('renders metric card with before value "10 hrs/week"', () => {
    render(<ImpactMetrics />);
    expect(screen.getByText('10 hrs/week')).toBeInTheDocument();
  });

  it('renders metric card with after value "30 min/week"', () => {
    render(<ImpactMetrics />);
    expect(screen.getByText('30 min/week')).toBeInTheDocument();
  });

  it('renders label "Manual review time saved"', () => {
    render(<ImpactMetrics />);
    expect(screen.getByText('Manual review time saved')).toBeInTheDocument();
  });

  it('before value "10 hrs/week" has line-through styling', () => {
    render(<ImpactMetrics />);
    const beforeEl = screen.getByText('10 hrs/week');
    const style = window.getComputedStyle(beforeEl);
    const hasLineThrough =
      style.textDecoration.includes('line-through') ||
      beforeEl.className.includes('line-through');
    expect(hasLineThrough).toBe(true);
  });

  // Card 2
  it('renders metric card with before value "2+ days"', () => {
    render(<ImpactMetrics />);
    expect(screen.getByText('2+ days')).toBeInTheDocument();
  });

  it('renders metric card with after value "< 1 hour"', () => {
    render(<ImpactMetrics />);
    expect(screen.getByText('< 1 hour')).toBeInTheDocument();
  });

  it('renders label "Time to respond to churn signals"', () => {
    render(<ImpactMetrics />);
    expect(screen.getByText('Time to respond to churn signals')).toBeInTheDocument();
  });

  // Card 3
  it('renders metric card with before value "Gut feeling"', () => {
    render(<ImpactMetrics />);
    expect(screen.getByText('Gut feeling')).toBeInTheDocument();
  });

  it('renders metric card with after value "Data-driven"', () => {
    render(<ImpactMetrics />);
    expect(screen.getByText('Data-driven')).toBeInTheDocument();
  });

  it('renders label "Product roadmap decisions"', () => {
    render(<ImpactMetrics />);
    expect(screen.getByText('Product roadmap decisions')).toBeInTheDocument();
  });

  // Count
  it('renders exactly 3 metric cards', () => {
    render(<ImpactMetrics />);
    const cards = document.querySelectorAll('[data-testid^="metric-card-"]');
    expect(cards).toHaveLength(3);
  });

  it('renders data-testid="impact-section" on the section element', () => {
    render(<ImpactMetrics />);
    expect(screen.getByTestId('impact-section')).toBeInTheDocument();
  });

  it('each metric card has data-testid matching metric-card-{index}', () => {
    render(<ImpactMetrics />);
    expect(screen.getByTestId('metric-card-0')).toBeInTheDocument();
    expect(screen.getByTestId('metric-card-1')).toBeInTheDocument();
    expect(screen.getByTestId('metric-card-2')).toBeInTheDocument();
  });
});
