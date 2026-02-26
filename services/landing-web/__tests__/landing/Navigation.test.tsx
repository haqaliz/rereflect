import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { Navigation } from '@/components/landing/Navigation';

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

describe('Navigation', () => {
  it('renders nav links: Features, Pricing, Integrations, Blog', () => {
    render(<Navigation isSticky={false} />);
    expect(screen.getByText('Features')).toBeInTheDocument();
    expect(screen.getByText('Pricing')).toBeInTheDocument();
    expect(screen.getByText('Integrations')).toBeInTheDocument();
    expect(screen.getByText('Blog')).toBeInTheDocument();
  });

  it('renders Sign In and Get Started buttons', () => {
    render(<Navigation isSticky={false} />);
    expect(screen.getByText('Sign In')).toBeInTheDocument();
    expect(screen.getByText(/Get Started/)).toBeInTheDocument();
  });

  it('renders Rereflect logo/brand text', () => {
    render(<Navigation isSticky={false} />);
    expect(screen.getByTestId('logo')).toBeInTheDocument();
    expect(screen.getByText('reflect')).toBeInTheDocument();
  });

  it('applies sticky styles when isSticky=true', () => {
    render(<Navigation isSticky={true} />);
    const nav = screen.getByRole('navigation');
    expect(nav.className).toContain('fixed');
    expect(nav.className).toContain('top-0');
    expect(nav.className).toContain('left-0');
    expect(nav.className).toContain('right-0');
    expect(nav.className).toContain('border-b');
    expect(nav.className).toContain('shadow-sm');
    // Blur and background are applied via inline styles (oklch workaround)
    expect(nav.style.backdropFilter).toBe('blur(24px)');
    expect(nav.style.backgroundColor).toBe('rgba(0, 0, 0, 0.5)');
  });

  it('does not apply sticky styles when isSticky=false', () => {
    render(<Navigation isSticky={false} />);
    const nav = screen.getByRole('navigation');
    expect(nav.className).not.toContain('fixed');
    expect(nav.style.backdropFilter).toBeFalsy();
    expect(nav.style.backgroundColor).toBeFalsy();
  });

  it('renders a mobile menu toggle button', () => {
    render(<Navigation isSticky={false} />);
    const toggle = screen.getByLabelText('Toggle menu');
    expect(toggle).toBeInTheDocument();
  });

  it('mobile menu is hidden by default', () => {
    render(<Navigation isSticky={false} />);
    expect(screen.queryByTestId('mobile-menu')).not.toBeInTheDocument();
  });

  it('opens mobile menu when toggle is clicked', () => {
    render(<Navigation isSticky={false} />);
    fireEvent.click(screen.getByLabelText('Toggle menu'));
    const mobileMenu = screen.getByTestId('mobile-menu');
    expect(mobileMenu).toBeInTheDocument();
    expect(mobileMenu).toHaveTextContent('Features');
    expect(mobileMenu).toHaveTextContent('Pricing');
    expect(mobileMenu).toHaveTextContent('Integrations');
    expect(mobileMenu).toHaveTextContent('Blog');
  });

  it('closes mobile menu when toggle is clicked again', () => {
    render(<Navigation isSticky={false} />);
    const toggle = screen.getByLabelText('Toggle menu');
    fireEvent.click(toggle);
    expect(screen.getByTestId('mobile-menu')).toBeInTheDocument();
    fireEvent.click(toggle);
    expect(screen.queryByTestId('mobile-menu')).not.toBeInTheDocument();
  });
});
