import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

// Mock next/navigation
const mockReplace = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/settings/usage-events',
}));

// Mock next/link
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

import UsageEventsPage from '../../app/(dashboard)/settings/usage-events/page';

const adminUser = {
  id: 1,
  email: 'admin@test.com',
  role: 'admin',
  plan: 'pro',
  organization_id: 1,
  is_system_admin: false,
};

const memberUser = { ...adminUser, role: 'member' };

describe('UsageEventsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders for admin users', () => {
    mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
    render(<UsageEventsPage />);
    expect(screen.getByText(/send product-usage events/i)).toBeInTheDocument();
  });

  it('renders for owner users', () => {
    mockUseAuth.mockReturnValue({
      user: { ...adminUser, role: 'owner' },
      isLoading: false,
      isAuthenticated: true,
    });
    render(<UsageEventsPage />);
    expect(screen.getByText(/send product-usage events/i)).toBeInTheDocument();
  });

  it('redirects member users to preferences', () => {
    mockUseAuth.mockReturnValue({ user: memberUser, isLoading: false, isAuthenticated: true });
    render(<UsageEventsPage />);
    expect(mockReplace).toHaveBeenCalledWith('/settings/preferences');
  });

  it('renders the ingest endpoint URL', () => {
    mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
    render(<UsageEventsPage />);
    // Multiple elements mention the endpoint (schema, curl, etc.); verify at least one renders
    const els = screen.getAllByText(/\/api\/v1\/webhooks\/usage/i);
    expect(els.length).toBeGreaterThanOrEqual(1);
  });

  it('renders curl example section', () => {
    mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
    render(<UsageEventsPage />);
    expect(screen.getByText(/curl example/i)).toBeInTheDocument();
  });

  it('renders verify section', () => {
    mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
    render(<UsageEventsPage />);
    expect(screen.getByText(/verify it.s working/i)).toBeInTheDocument();
  });

  it('renders link to API keys settings', () => {
    mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
    render(<UsageEventsPage />);
    const link = screen.getByRole('link', { name: /api keys/i });
    expect(link).toHaveAttribute('href', '/settings/api-keys');
  });

  it('shows ingest scope mention', () => {
    mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
    render(<UsageEventsPage />);
    const els = screen.getAllByText(/ingest/i);
    expect(els.length).toBeGreaterThanOrEqual(1);
  });

  it('points the usage weight instructions at Settings > AI, not the preferences page (AC 15)', () => {
    mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
    render(<UsageEventsPage />);
    const link = screen.getByRole('link', { name: /health score weights/i });
    expect(link).toHaveAttribute('href', '/settings/ai');
    expect(screen.queryByRole('link', { name: /settings.{0,3}preferences/i })).not.toBeInTheDocument();
  });
});
