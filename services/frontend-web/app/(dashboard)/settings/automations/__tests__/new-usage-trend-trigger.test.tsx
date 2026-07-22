/**
 * Tests for the `usage_trend` trigger additions to the "New Automation Rule"
 * page: the trigger type option, the states config (declining/sharp_decline
 * checkboxes, both pre-selected), client-side blocking of an empty selection,
 * and the per-trigger `mode` default (usage_trend -> shadow, every other
 * trigger type -> active, asserted as an explicit negative case).
 *
 * Mirrors the mock/import pattern used by new-churn-playbook.test.tsx.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// ─── mocks ──────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/settings/automations/new',
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

const mockCreate = vi.fn();
vi.mock('@/lib/api/automations', () => ({
  automationsAPI: {
    create: (...args: any[]) => mockCreate(...args),
    list: vi.fn().mockResolvedValue({ rules: [], count: 0, limit: 5 }),
    get: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    toggle: vi.fn(),
    listExecutions: vi.fn().mockResolvedValue([]),
    listTemplates: vi.fn().mockResolvedValue([]),
    enableTemplate: vi.fn(),
  },
  TRIGGER_TYPE_LABELS: {
    health_score_threshold: 'Health Score Threshold',
    sentiment_pattern: 'Sentiment Pattern',
    churn_risk_level_change: 'Churn Risk Level Change',
    feedback_category_match: 'Category Match',
    churn_probability_threshold: 'Churn probability threshold',
    usage_trend: 'Usage Trend',
  },
  ACTION_TYPE_LABELS: {
    auto_assign: 'Auto-Assign',
    change_status: 'Change Status',
    send_notification: 'Send Notification',
    draft_response: 'Draft AI Response',
    run_playbook: 'Run churn playbook',
  },
  PLAN_AUTOMATION_LIMITS: {
    free: 0,
    pro: 5,
    business: 20,
    enterprise: null,
  },
}));

const mockListPlaybooks = vi.fn();
vi.mock('@/lib/api/playbooks', () => ({
  listPlaybooks: (...args: any[]) => mockListPlaybooks(...args),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// ─── import after mocks ───────────────────────────────────────────────────

import NewAutomationPage from '../new/page';

// ─── fixtures ─────────────────────────────────────────────────────────────

const ownerUser = {
  id: 1,
  email: 'owner@test.com',
  role: 'owner',
  plan: 'business',
  organization_id: 1,
  is_system_admin: false,
};

describe('NewAutomationPage — usage_trend trigger type selection (AC1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockListPlaybooks.mockResolvedValue([]);
  });

  it('appears in the trigger type selector with its label', async () => {
    const user = userEvent.setup();
    render(<NewAutomationPage />);

    await user.click(screen.getByTestId('trigger-type-select'));
    expect(await screen.findByText('Usage Trend')).toBeInTheDocument();
  });
});

describe('NewAutomationPage — usage_trend states config (AC2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockListPlaybooks.mockResolvedValue([]);
  });

  it('renders the states control with both states pre-selected, and submits the states payload', async () => {
    const user = userEvent.setup();
    mockCreate.mockResolvedValue({ id: 77, name: 'x' });

    render(<NewAutomationPage />);

    await user.type(screen.getByTestId('rule-name-input'), 'Usage decline outreach');

    await user.click(screen.getByTestId('trigger-type-select'));
    await user.click(await screen.findByText('Usage Trend'));

    const decliningCheckbox = await screen.findByTestId('trigger-config-state-declining');
    const sharpDeclineCheckbox = await screen.findByTestId('trigger-config-state-sharp_decline');
    expect(decliningCheckbox).toBeChecked();
    expect(sharpDeclineCheckbox).toBeChecked();

    await user.click(screen.getByRole('button', { name: /save rule/i }));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          trigger: {
            type: 'usage_trend',
            config: { states: ['declining', 'sharp_decline'] },
          },
        })
      );
    });
  });
});

describe('NewAutomationPage — usage_trend empty selection is blocked (AC3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockListPlaybooks.mockResolvedValue([]);
  });

  it('blocks submission client-side when both states are deselected', async () => {
    const user = userEvent.setup();

    render(<NewAutomationPage />);

    await user.type(screen.getByTestId('rule-name-input'), 'Empty states rule');

    await user.click(screen.getByTestId('trigger-type-select'));
    await user.click(await screen.findByText('Usage Trend'));

    const decliningCheckbox = await screen.findByTestId('trigger-config-state-declining');
    const sharpDeclineCheckbox = await screen.findByTestId('trigger-config-state-sharp_decline');
    await user.click(decliningCheckbox);
    await user.click(sharpDeclineCheckbox);

    await user.click(screen.getByRole('button', { name: /save rule/i }));

    expect(mockCreate).not.toHaveBeenCalled();
  });
});

describe('NewAutomationPage — usage_trend defaults mode to shadow (AC4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockListPlaybooks.mockResolvedValue([]);
  });

  it('submits mode: "shadow" for a new usage_trend rule without touching the mode selector', async () => {
    const user = userEvent.setup();
    mockCreate.mockResolvedValue({ id: 78, name: 'x' });

    render(<NewAutomationPage />);

    await user.type(screen.getByTestId('rule-name-input'), 'Shadow by default');

    await user.click(screen.getByTestId('trigger-type-select'));
    await user.click(await screen.findByText('Usage Trend'));

    expect(screen.getByTestId('rule-mode-select')).toHaveTextContent(/shadow/i);

    await user.click(screen.getByRole('button', { name: /save rule/i }));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith(expect.objectContaining({ mode: 'shadow' }));
    });
  });
});

describe('NewAutomationPage — other trigger types still default to active (AC4 negative case)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockListPlaybooks.mockResolvedValue([]);
  });

  it('submits mode: "active" for a non-usage_trend rule — the usage_trend shadow default must not leak', async () => {
    const user = userEvent.setup();
    mockCreate.mockResolvedValue({ id: 79, name: 'x' });

    render(<NewAutomationPage />);

    await user.type(screen.getByTestId('rule-name-input'), 'Still active by default');

    await user.click(screen.getByTestId('trigger-type-select'));
    await user.click(await screen.findByText('Health Score Threshold'));

    expect(screen.getByTestId('rule-mode-select')).toHaveTextContent(/active/i);

    await user.click(screen.getByRole('button', { name: /save rule/i }));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith(expect.objectContaining({ mode: 'active' }));
    });
  });
});
