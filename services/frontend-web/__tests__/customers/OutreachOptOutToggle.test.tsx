import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

const mockUseAuth = vi.fn();
const mockUpdateOutreachOptOut = vi.fn();

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@/lib/api/customers', () => ({
  customersAPI: {
    updateOutreachOptOut: (...args: unknown[]) => mockUpdateOutreachOptOut(...args),
  },
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';
import { OutreachOptOutToggle } from '@/components/customers/OutreachOptOutToggle';

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('OutreachOptOutToggle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({
      user: { id: 1, email: 'owner@test.com', role: 'owner', organization_id: 1 },
      isLoading: false,
      isAuthenticated: true,
    });
  });

  it('renders a switch unchecked when initialValue is false (AC9)', () => {
    renderWithQueryClient(
      <OutreachOptOutToggle email="john@acme.com" initialValue={false} />
    );
    expect(
      screen.getByRole('switch', { name: /opted out of outreach emails/i })
    ).not.toBeChecked();
  });

  it('renders a switch checked when initialValue is true (AC9)', () => {
    renderWithQueryClient(
      <OutreachOptOutToggle email="jane@acme.com" initialValue={true} />
    );
    expect(
      screen.getByRole('switch', { name: /opted out of outreach emails/i })
    ).toBeChecked();
  });

  it('toggling PATCHes the negated value and stays on on success (AC9)', async () => {
    mockUpdateOutreachOptOut.mockResolvedValue({ outreach_opt_out: true });
    renderWithQueryClient(
      <OutreachOptOutToggle email="john@acme.com" initialValue={false} />
    );
    const toggle = screen.getByRole('switch', { name: /opted out of outreach emails/i });

    fireEvent.click(toggle);

    await waitFor(() => {
      expect(mockUpdateOutreachOptOut).toHaveBeenCalledWith('john@acme.com', true);
    });
    expect(toggle).toBeChecked();
  });

  it('reverts the switch and fires a toast on failure (AC9)', async () => {
    mockUpdateOutreachOptOut.mockRejectedValue(new Error('member forbidden'));
    renderWithQueryClient(
      <OutreachOptOutToggle email="john@acme.com" initialValue={true} />
    );
    const toggle = screen.getByRole('switch', { name: /opted out of outreach emails/i });

    fireEvent.click(toggle);

    await waitFor(() => {
      expect(mockUpdateOutreachOptOut).toHaveBeenCalledWith('john@acme.com', false);
    });
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
    expect(toggle).toBeChecked();
  });

  it('explains the opt-out consequence under the switch (AC9)', () => {
    renderWithQueryClient(
      <OutreachOptOutToggle email="john@acme.com" initialValue={true} />
    );
    expect(
      screen.getByText(
        /when on, this customer will not receive outreach emails from playbooks or campaigns/i
      )
    ).toBeInTheDocument();
  });

  it('is absent for the member role (AC10)', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 2, email: 'member@test.com', role: 'member', organization_id: 1 },
      isLoading: false,
      isAuthenticated: true,
    });
    renderWithQueryClient(
      <OutreachOptOutToggle email="john@acme.com" initialValue={false} />
    );
    expect(
      screen.queryByRole('switch', { name: /opted out of outreach emails/i })
    ).not.toBeInTheDocument();
  });
});
