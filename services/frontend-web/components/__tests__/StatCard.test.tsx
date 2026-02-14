import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatCard } from '../StatCard';
import { MessageSquare } from 'lucide-react';

describe('StatCard', () => {
  it('renders the title', () => {
    render(
      <StatCard
        title="Total Feedback"
        value={42}
        icon={MessageSquare}
        color="blue"
      />
    );

    expect(screen.getByText('Total Feedback')).toBeInTheDocument();
  });

  it('renders the value', () => {
    render(
      <StatCard
        title="Total Feedback"
        value={42}
        icon={MessageSquare}
        color="blue"
      />
    );

    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('renders string values', () => {
    render(
      <StatCard
        title="Status"
        value="Active"
        icon={MessageSquare}
        color="green"
      />
    );

    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('renders with trend indicator', () => {
    render(
      <StatCard
        title="Growth"
        value={100}
        icon={MessageSquare}
        color="green"
        trend={{ value: 15, isPositive: true }}
      />
    );

    expect(screen.getByText('15%')).toBeInTheDocument();
  });
});
