import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import Nav from '@/components/landing/Nav';

vi.mock('next/link', () => ({
  default: ({ children, ...props }: { children: React.ReactNode; [key: string]: unknown }) => (
    <a {...props}>{children}</a>
  ),
}));

describe('Nav', () => {
  it('renders brand logo and text', () => {
    render(<Nav />);
    expect(screen.getByText('reflect')).toBeInTheDocument();
    expect(screen.getByText('Re')).toBeInTheDocument();
  });

  it('renders nav links: Features, Integrations, Blog', () => {
    render(<Nav />);
    expect(screen.getByText('Features')).toBeInTheDocument();
    expect(screen.getByText('Integrations')).toBeInTheDocument();
    expect(screen.getByText('Blog')).toBeInTheDocument();
  });

  it('renders a GitHub CTA', () => {
    render(<Nav />);
    expect(screen.getByRole('link', { name: /GitHub/i })).toBeInTheDocument();
  });

  it('does not render any sign-in, sign-up, or get-started links', () => {
    render(<Nav />);
    expect(screen.queryByText(/sign in/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/sign up/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/get started/i)).not.toBeInTheDocument();
  });
});