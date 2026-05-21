import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockListPlaybooks = vi.fn();
const mockRunPlaybook = vi.fn();

vi.mock('@/lib/api/playbooks', () => ({
  listPlaybooks: (...args: unknown[]) => mockListPlaybooks(...args),
  runPlaybook: (...args: unknown[]) => mockRunPlaybook(...args),
  createPlaybook: vi.fn(),
  updatePlaybook: vi.fn(),
  deletePlaybook: vi.fn(),
  getPlaybook: vi.fn(),
  runPlaybookBatch: vi.fn(),
  listExecutions: vi.fn(),
  formatProbabilityRange: (min: number, max: number) =>
    `${Math.round(min * 100)}%–${Math.round(max * 100)}%`,
  PLAN_PLAYBOOK_LIMITS: { free: 0, pro: 0, business: 20, enterprise: null },
}));

const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();
vi.mock('sonner', () => ({
  toast: { success: (...args: unknown[]) => mockToastSuccess(...args), error: (...args: unknown[]) => mockToastError(...args) },
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

import { RunPlaybookDropdown } from '@/components/customers/RunPlaybookDropdown';
import type { Playbook } from '@/lib/api/playbooks';

// ─── Fixtures ────────────────────────────────────────────────────────────────

const businessUser = { id: 1, email: 'cs@test.com', role: 'admin', plan: 'business', organization_id: 1 };
const proUser = { ...businessUser, plan: 'pro' };

const matchingPlaybook: Playbook = {
  id: 3,
  organization_id: 1,
  name: 'At-Risk Outreach',
  description: 'Send outreach for at-risk customers',
  probability_min: 0.5,
  probability_max: 0.85,
  action_sequence: [{ type: 'send_notification', channel: 'email' }],
  is_template: false,
  is_active: true,
  source_template_id: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const nonMatchingPlaybook: Playbook = {
  ...matchingPlaybook,
  id: 4,
  name: 'Critical Save',
  probability_min: 0.85,
  probability_max: 1.0,
};

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('RunPlaybookDropdown', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: businessUser });
    mockListPlaybooks.mockResolvedValue([matchingPlaybook, nonMatchingPlaybook]);
  });

  it('renders nothing (returns null) when churn_probability is null', async () => {
    const { container } = render(
      <RunPlaybookDropdown
        customerEmail="test@example.com"
        churnProbability={null}
      />
    );
    await waitFor(() => {
      expect(container.firstChild).toBeNull();
    });
  });

  it('renders nothing when churn_probability is undefined', async () => {
    const { container } = render(
      <RunPlaybookDropdown
        customerEmail="test@example.com"
        churnProbability={undefined}
      />
    );
    await waitFor(() => {
      expect(container.firstChild).toBeNull();
    });
  });

  it('lists only playbooks matching the customer probability range', async () => {
    const user = userEvent.setup();
    render(
      <RunPlaybookDropdown
        customerEmail="test@example.com"
        churnProbability={0.65}
      />
    );
    await waitFor(() => screen.getByRole('button', { name: /run playbook/i }));
    await user.click(screen.getByRole('button', { name: /run playbook/i }));
    await waitFor(() => {
      expect(screen.getByText('At-Risk Outreach')).toBeInTheDocument();
      expect(screen.queryByText('Critical Save')).not.toBeInTheDocument();
    });
  });

  it('clicking a playbook calls runPlaybook', async () => {
    const user = userEvent.setup();
    mockRunPlaybook.mockResolvedValue({ id: 99, status: 'queued' });
    render(
      <RunPlaybookDropdown
        customerEmail="alice@example.com"
        churnProbability={0.65}
      />
    );
    await waitFor(() => screen.getByRole('button', { name: /run playbook/i }));
    await user.click(screen.getByRole('button', { name: /run playbook/i }));
    await waitFor(() => screen.getByText('At-Risk Outreach'));
    await user.click(screen.getByText('At-Risk Outreach'));
    await waitFor(() => {
      expect(mockRunPlaybook).toHaveBeenCalledWith(matchingPlaybook.id, 'alice@example.com');
    });
  });

  it('shows success toast after run with execution id', async () => {
    const user = userEvent.setup();
    mockRunPlaybook.mockResolvedValue({ id: 99, status: 'queued' });
    render(
      <RunPlaybookDropdown
        customerEmail="alice@example.com"
        churnProbability={0.65}
      />
    );
    await waitFor(() => screen.getByRole('button', { name: /run playbook/i }));
    await user.click(screen.getByRole('button', { name: /run playbook/i }));
    await waitFor(() => screen.getByText('At-Risk Outreach'));
    await user.click(screen.getByText('At-Risk Outreach'));
    await waitFor(() => {
      expect(mockToastSuccess).toHaveBeenCalledWith(expect.stringMatching(/queued|#99/i));
    });
  });

  it('shows error toast on runPlaybook failure', async () => {
    const user = userEvent.setup();
    mockRunPlaybook.mockRejectedValue(new Error('Server error'));
    render(
      <RunPlaybookDropdown
        customerEmail="alice@example.com"
        churnProbability={0.65}
      />
    );
    await waitFor(() => screen.getByRole('button', { name: /run playbook/i }));
    await user.click(screen.getByRole('button', { name: /run playbook/i }));
    await waitFor(() => screen.getByText('At-Risk Outreach'));
    await user.click(screen.getByText('At-Risk Outreach'));
    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalled();
    });
  });

  it('is disabled (renders nothing) for non-Business plan users', async () => {
    mockUseAuth.mockReturnValue({ user: proUser });
    const { container } = render(
      <RunPlaybookDropdown
        customerEmail="alice@example.com"
        churnProbability={0.65}
      />
    );
    await waitFor(() => {
      expect(container.firstChild).toBeNull();
    });
  });
});
