/**
 * Tests for the "Shadow" badge added to the automations list page next to
 * rules whose mode === 'shadow', and that the existing is_active Switch
 * keeps working unmodified.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// ─── mocks ──────────────────────────────────────────────────────────────────

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/settings/automations',
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

const mockList = vi.fn();
const mockToggle = vi.fn();
const mockListTemplates = vi.fn();

vi.mock('@/lib/api/automations', () => ({
  automationsAPI: {
    list: (...args: any[]) => mockList(...args),
    toggle: (...args: any[]) => mockToggle(...args),
    listTemplates: (...args: any[]) => mockListTemplates(...args),
    enableTemplate: vi.fn(),
    delete: vi.fn(),
  },
  TRIGGER_TYPE_LABELS: {
    health_score_threshold: 'Health Score Threshold',
    churn_probability_threshold: 'Churn probability threshold',
  },
  ACTION_TYPE_LABELS: {
    auto_assign: 'Auto-Assign',
    run_playbook: 'Run churn playbook',
  },
  PLAN_AUTOMATION_LIMITS: {
    free: 0,
    pro: 5,
    business: 20,
    enterprise: null,
  },
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import AutomationsPage from '../page';

// ─── fixtures ─────────────────────────────────────────────────────────────

const businessUser = {
  id: 1,
  email: 'admin@test.com',
  role: 'admin',
  plan: 'business',
  organization_id: 1,
  is_system_admin: false,
};

const rules = [
  {
    id: 1,
    name: 'Shadow rule',
    description: null,
    is_active: true,
    mode: 'shadow' as const,
    trigger_type: 'churn_probability_threshold' as const,
    trigger_config: { threshold: 0.7 },
    actions: [{ type: 'run_playbook', config: { playbook_id: 3 } }],
    cooldown_hours: 24,
    execution_count: 0,
    last_executed_at: null,
    is_template: false,
    template_id: null,
    created_at: '2026-05-01T00:00:00Z',
  },
  {
    id: 2,
    name: 'Active rule',
    description: null,
    is_active: true,
    mode: 'active' as const,
    trigger_type: 'health_score_threshold' as const,
    trigger_config: { threshold: 30 },
    actions: [{ type: 'auto_assign', config: {} }],
    cooldown_hours: 24,
    execution_count: 0,
    last_executed_at: null,
    is_template: false,
    template_id: null,
    created_at: '2026-05-01T00:00:00Z',
  },
];

describe('AutomationsPage — shadow mode badge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: businessUser });
    mockList.mockResolvedValue({ rules, count: 2, limit: 20 });
    mockListTemplates.mockResolvedValue([]);
  });

  it('shows a Shadow badge next to rules whose mode is shadow, and not for others', async () => {
    render(<AutomationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Shadow rule')).toBeInTheDocument();
    });

    const shadowRow = screen.getByText('Shadow rule').closest('tr')!;
    const activeRow = screen.getByText('Active rule').closest('tr')!;

    expect(shadowRow.textContent).toMatch(/shadow/i);
    expect(activeRow.textContent).not.toMatch(/shadow/i);
  });

  it('keeps the existing is_active Switch working', async () => {
    mockToggle.mockResolvedValue({ ...rules[0], is_active: false });
    render(<AutomationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Shadow rule')).toBeInTheDocument();
    });

    const switches = screen.getAllByRole('switch');
    fireEvent.click(switches[0]);

    await waitFor(() => {
      expect(mockToggle).toHaveBeenCalledWith(1);
    });
  });
});
