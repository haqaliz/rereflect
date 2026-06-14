import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockListPlaybooks = vi.fn();
const mockUpdatePlaybook = vi.fn();

vi.mock('@/lib/api/playbooks', () => ({
  listPlaybooks: (...args: unknown[]) => mockListPlaybooks(...args),
  updatePlaybook: (...args: unknown[]) => mockUpdatePlaybook(...args),
  createPlaybook: vi.fn(),
  deletePlaybook: vi.fn(),
  getPlaybook: vi.fn(),
  runPlaybook: vi.fn(),
  runPlaybookBatch: vi.fn(),
  listExecutions: vi.fn(),
  formatProbabilityRange: (min: number, max: number) =>
    `${Math.round(min * 100)}%–${Math.round(max * 100)}%`,
  PLAN_PLAYBOOK_LIMITS: { free: 0, pro: 0, business: 20, enterprise: null },
  ACTION_TYPE_LABELS: {
    assign: 'Assign',
    change_status: 'Change Status',
    send_notification: 'Send Notification',
    draft_response: 'Draft AI Response',
  },
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/settings/playbooks',
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

import PlaybooksPage from '@/app/(dashboard)/settings/playbooks/page';
import type { Playbook } from '@/lib/api/playbooks';

// ─── Fixtures ────────────────────────────────────────────────────────────────

const businessUser = {
  id: 1,
  email: 'cs@test.com',
  role: 'admin',
  plan: 'business',
  organization_id: 1,
  is_system_admin: false,
};

const freeUser = { ...businessUser, plan: 'free' };
const proUser = { ...businessUser, plan: 'pro' };

const orgPlaybook: Playbook = {
  id: 10,
  organization_id: 1,
  name: 'My Prevention',
  description: 'Org-level playbook',
  probability_min: 0.5,
  probability_max: 0.85,
  action_sequence: [{ type: 'send_notification', channel: 'slack' }],
  is_template: false,
  is_active: true,
  source_template_id: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const templatePlaybook: Playbook = {
  id: 1,
  organization_id: null,
  name: 'Critical Save',
  description: 'System template for critical saves',
  probability_min: 0.85,
  probability_max: 1.0,
  action_sequence: [
    { type: 'assign', role: 'cs_lead' },
    { type: 'send_notification', channel: 'slack' },
  ],
  is_template: true,
  is_active: true,
  source_template_id: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('PlaybooksListPage - plan gating removed', () => {
  it('shows playbook content for Free plan (no upgrade banner)', async () => {
    mockUseAuth.mockReturnValue({ user: freeUser });
    mockListPlaybooks.mockResolvedValue([]);
    render(<PlaybooksPage />);
    await waitFor(() => {
      expect(screen.getByTestId('section-org-playbooks')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('upgrade-banner')).not.toBeInTheDocument();
  });

  it('shows playbook content for Pro plan (no upgrade banner)', async () => {
    mockUseAuth.mockReturnValue({ user: proUser });
    mockListPlaybooks.mockResolvedValue([]);
    render(<PlaybooksPage />);
    await waitFor(() => {
      expect(screen.getByTestId('section-org-playbooks')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('upgrade-banner')).not.toBeInTheDocument();
  });
});

describe('PlaybooksListPage - data display', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: businessUser });
    mockListPlaybooks.mockResolvedValue([orgPlaybook, templatePlaybook]);
  });

  it('fetches and renders org playbooks and templates in separate sections', async () => {
    render(<PlaybooksPage />);
    await waitFor(() => {
      expect(screen.getByText('My Prevention')).toBeInTheDocument();
      expect(screen.getByText('Critical Save')).toBeInTheDocument();
    });
    expect(screen.getByTestId('section-org-playbooks')).toBeInTheDocument();
    expect(screen.getByTestId('section-templates')).toBeInTheDocument();
  });

  it('templates render in their own section', async () => {
    render(<PlaybooksPage />);
    await waitFor(() => {
      const templateSection = screen.getByTestId('section-templates');
      expect(templateSection).toHaveTextContent('Critical Save');
    });
    const orgSection = screen.getByTestId('section-org-playbooks');
    expect(orgSection).not.toHaveTextContent('Critical Save');
  });

  it('shows count of own playbooks', async () => {
    render(<PlaybooksPage />);
    await waitFor(() => {
      expect(screen.getByTestId('playbook-count')).toHaveTextContent('1');
    });
  });
});

describe('PlaybooksListPage - navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: businessUser });
    mockListPlaybooks.mockResolvedValue([orgPlaybook, templatePlaybook]);
  });

  it('"+ New" navigates to /settings/playbooks/new', async () => {
    render(<PlaybooksPage />);
    await waitFor(() => screen.getByRole('button', { name: /new/i }));
    fireEvent.click(screen.getByRole('button', { name: /new/i }));
    expect(mockPush).toHaveBeenCalledWith('/settings/playbooks/new');
  });

  it('clicking a template navigates to /settings/playbooks/new?template=ID', async () => {
    render(<PlaybooksPage />);
    await waitFor(() => screen.getByText('Critical Save'));
    fireEvent.click(screen.getAllByRole('button', { name: /use template/i })[0]);
    expect(mockPush).toHaveBeenCalledWith(`/settings/playbooks/new?template=${templatePlaybook.id}`);
  });

  it('clicking own playbook navigates to /settings/playbooks/{id}', async () => {
    render(<PlaybooksPage />);
    await waitFor(() => screen.getByText('My Prevention'));
    fireEvent.click(screen.getByText('My Prevention'));
    expect(mockPush).toHaveBeenCalledWith(`/settings/playbooks/${orgPlaybook.id}`);
  });
});

describe('PlaybooksListPage - toggle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: businessUser });
    mockListPlaybooks.mockResolvedValue([orgPlaybook, templatePlaybook]);
    mockUpdatePlaybook.mockResolvedValue({ ...orgPlaybook, is_active: false });
  });

  it('active toggle calls updatePlaybook', async () => {
    render(<PlaybooksPage />);
    await waitFor(() => screen.getByText('My Prevention'));
    const toggles = screen.getAllByRole('switch');
    fireEvent.click(toggles[0]);
    await waitFor(() => {
      expect(mockUpdatePlaybook).toHaveBeenCalledWith(orgPlaybook.id, { is_active: false });
    });
  });
});

describe('PlaybooksListPage - empty state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: businessUser });
    mockListPlaybooks.mockResolvedValue([templatePlaybook]); // templates only, no org playbooks
  });

  it('shows empty state when no org playbooks', async () => {
    render(<PlaybooksPage />);
    await waitFor(() => {
      expect(screen.getByTestId('empty-org-playbooks')).toBeInTheDocument();
    });
  });
});

describe('PlaybooksListPage - error state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: businessUser });
    mockListPlaybooks.mockRejectedValue(new Error('Network error'));
  });

  it('shows error state on API failure', async () => {
    render(<PlaybooksPage />);
    await waitFor(() => {
      expect(screen.getByTestId('error-state')).toBeInTheDocument();
    });
  });
});
