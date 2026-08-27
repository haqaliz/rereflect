import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import Footer from '@/components/landing/Footer';

vi.mock('next/link', () => ({
  default: ({ children, ...props }: { children: React.ReactNode; [key: string]: unknown }) => (
    <a {...props}>{children}</a>
  ),
}));

describe('Footer', () => {
  it('renders Rereflect logo and OSS tagline', () => {
    render(<Footer />);
    expect(screen.getByText('reflect')).toBeInTheDocument();
    expect(
      screen.getByText(/Customer feedback, analyzed\. Open source, self-hosted, and yours\./),
    ).toBeInTheDocument();
  });

  it('renders Product column with Features, Integrations, Blog links', () => {
    render(<Footer />);
    expect(screen.getByRole('heading', { name: 'Product' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Features' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Integrations' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Blog' })).toBeInTheDocument();
  });

  it('renders Open source column with GitHub, Self-host guide, Privacy, Terms links', () => {
    render(<Footer />);
    expect(screen.getByRole('heading', { name: 'Open source' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'GitHub' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Self-host guide' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Privacy' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Terms' })).toBeInTheDocument();
  });

  it('does not render any sign-in or sign-up links', () => {
    render(<Footer />);
    expect(screen.queryByText(/sign in/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/sign up/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/get started/i)).not.toBeInTheDocument();
  });

  it('renders Product Hunt badge', () => {
    render(<Footer />);
    expect(screen.getByAltText(/Product Hunt/i)).toBeInTheDocument();
  });

  it('shows 2026 Rereflect in copyright', () => {
    render(<Footer />);
    expect(screen.getByText(/2026 Rereflect/)).toBeInTheDocument();
  });

  it('shows MIT license text in footer bottom', () => {
    render(<Footer />);
    expect(screen.getByText(/MIT licensed/)).toBeInTheDocument();
  });
});