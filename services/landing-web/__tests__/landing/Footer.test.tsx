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
  it('renders Rereflect logo and tagline', () => {
    render(<Footer />);
    expect(screen.getByTestId('logo')).toBeInTheDocument();
    expect(screen.getByText(/Transform overwhelming customer feedback/)).toBeInTheDocument();
  });

  it('renders Product column with Features, Pricing, Integrations links', () => {
    render(<Footer />);
    expect(screen.getByRole('heading', { name: 'Product' })).toBeInTheDocument();
    // Use getAllByText since "Features", "Pricing", "Integrations" may appear in nav too
    const featuresLinks = screen.getAllByText('Features');
    expect(featuresLinks.length).toBeGreaterThan(0);
    const pricingLinks = screen.getAllByText('Pricing');
    expect(pricingLinks.length).toBeGreaterThan(0);
    const integrationsLinks = screen.getAllByText('Integrations');
    expect(integrationsLinks.length).toBeGreaterThan(0);
  });

  it('renders Resources column with Blog and Changelog links', () => {
    render(<Footer />);
    expect(screen.getByRole('heading', { name: 'Resources' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Blog' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Changelog' })).toBeInTheDocument();
  });

  it('renders Company column with Privacy and Terms links', () => {
    render(<Footer />);
    expect(screen.getByRole('heading', { name: 'Company' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Privacy/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Terms/ })).toBeInTheDocument();
  });

  it('renders Connect column with X/Twitter link', () => {
    render(<Footer />);
    expect(screen.getByRole('heading', { name: 'Connect' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Twitter|Follow us on X/i })).toBeInTheDocument();
  });

  it('shows 2026 Rereflect in copyright', () => {
    render(<Footer />);
    expect(screen.getByText(/2026 Rereflect/)).toBeInTheDocument();
  });

  it('renders Product Hunt badge', () => {
    render(<Footer />);
    expect(screen.getByAltText(/Product Hunt/i)).toBeInTheDocument();
  });
});
