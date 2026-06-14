import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { Footer } from '@/components/landing/Footer';

vi.mock('next/link', () => ({
  default: ({ children, ...props }: { children: React.ReactNode; [key: string]: unknown }) => (
    <a {...props}>{children}</a>
  ),
}));

vi.mock('@rereflect/ui', () => ({
  Logo: ({ size, className }: { size?: string; className?: string }) => (
    <div data-testid="logo" data-size={size} className={className} />
  ),
}));

describe('Footer', () => {
  it('renders Rereflect logo and OSS tagline', () => {
    render(<Footer />);
    expect(screen.getByTestId('logo')).toBeInTheDocument();
    expect(screen.getByText(/Open-source AI feedback analysis/)).toBeInTheDocument();
  });

  it('renders Product column with Features, Open source, Integrations links', () => {
    render(<Footer />);
    expect(screen.getByRole('heading', { name: 'Product' })).toBeInTheDocument();
    const featuresLinks = screen.getAllByText('Features');
    expect(featuresLinks.length).toBeGreaterThan(0);
    const openSourceLinks = screen.getAllByText('Open source');
    expect(openSourceLinks.length).toBeGreaterThan(0);
    const integrationsLinks = screen.getAllByText('Integrations');
    expect(integrationsLinks.length).toBeGreaterThan(0);
  });

  it('renders Resources column with Blog and Self-host guide links', () => {
    render(<Footer />);
    expect(screen.getByRole('heading', { name: 'Resources' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Blog' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Self-host guide' })).toBeInTheDocument();
  });

  it('renders Company column with Privacy and Terms links', () => {
    render(<Footer />);
    expect(screen.getByRole('heading', { name: 'Company' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Privacy/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Terms/ })).toBeInTheDocument();
  });

  it('renders Connect column with GitHub and X/Twitter links', () => {
    render(<Footer />);
    expect(screen.getByRole('heading', { name: 'Connect' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /GitHub/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Twitter|Follow us on X/i })).toBeInTheDocument();
  });

  it('shows 2026 Rereflect in copyright', () => {
    render(<Footer />);
    expect(screen.getByText(/2026 Rereflect/)).toBeInTheDocument();
  });

  it('shows MIT license text in footer bottom', () => {
    render(<Footer />);
    expect(screen.getByText(/MIT licensed/)).toBeInTheDocument();
  });

  it('renders Product Hunt badge', () => {
    render(<Footer />);
    expect(screen.getByAltText(/Product Hunt/i)).toBeInTheDocument();
  });
});
