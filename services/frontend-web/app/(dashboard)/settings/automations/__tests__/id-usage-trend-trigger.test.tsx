/**
 * Tests for the `usage_trend` trigger additions to the automation rule
 * detail/edit page: the trigger type option, states config pre-population
 * from trigger_config, client-side blocking of an empty selection,
 * default-seeding when switching trigger type to/away from usage_trend
 * (including the mode default), and that a member-role user sees the
 * states controls disabled (existing isAdminOrOwner gating pattern).
 *
 * Mirrors the mock/import pattern used by id-churn-playbook.test.tsx.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// ─── mocks ──────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => ({ id: '9' }),
  usePathname: () => '/settings/automations/9',
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

const mockGet = vi.fn();
const mockUpdate = vi.fn();
const mockListExecutions = vi.fn();

vi.mock('@/lib/api/automations', () => ({
  automationsAPI: {
    create: vi.fn(),
    list: vi.fn(),
    get: (...args: any[]) => mockGet(...args),
    update: (...args: any[]) => mockUpdate(...args),
    delete: vi.fn(),
    toggle: vi.fn(),
    listExecutions: (...args: any[]) => mockListExecutions(...args),
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
}));

const mockListPlaybooks = vi.fn();
vi.mock('@/lib/api/playbooks', () => ({
  listPlaybooks: (...args: any[]) => mockListPlaybooks(...args),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// ─── import after mocks ───────────────────────────────────────────────────

import AutomationDetailPage from '../[id]/page';

// ─── fixtures ─────────────────────────────────────────────────────────────

const ownerUser = {
  id: 1,
  email: 'owner@test.com',
  role: 'owner',
  plan: 'business',
  organization_id: 1,
  is_system_admin: false,
};

const memberUser = { ...ownerUser, id: 2, email: 'member@test.com', role: 'member' };

const usageTrendRule = {
  id: 9,
  name: 'Usage decline outreach',
  description: 'Fires when a customer starts declining',
  is_active: true,
  mode: 'shadow' as const,
  trigger_type: 'usage_trend' as const,
  trigger_config: { states: ['sharp_decline'] },
  actions: [{ type: 'send_notification', config: { recipients: 'admins', channels: ['dashboard'] } }],
  cooldown_hours: 24,
  execution_count: 0,
  last_executed_at: null,
  is_template: false,
  template_id: null,
  created_at: '2026-07-01T00:00:00Z',
};

describe('AutomationDetailPage — usage_trend trigger type selection (AC1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockGet.mockResolvedValue(usageTrendRule);
    mockListExecutions.mockResolvedValue([]);
    mockListPlaybooks.mockResolvedValue([]);
  });

  it('appears in the trigger type selector with its label', async () => {
    const user = userEvent.setup();
    render(<AutomationDetailPage />);

    const triggerTypeSelect = await screen.findByTestId('trigger-type-select');
    await user.click(triggerTypeSelect);
    expect(await screen.findByRole('option', { name: 'Usage Trend' })).toBeInTheDocument();
  });
});

describe('AutomationDetailPage — usage_trend states config (AC2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockGet.mockResolvedValue(usageTrendRule);
    mockListExecutions.mockResolvedValue([]);
    mockListPlaybooks.mockResolvedValue([]);
  });

  it('pre-populates the states checkboxes from trigger_config (only sharp_decline checked)', async () => {
    render(<AutomationDetailPage />);

    const decliningCheckbox = await screen.findByTestId('trigger-config-state-declining');
    const sharpDeclineCheckbox = await screen.findByTestId('trigger-config-state-sharp_decline');
    expect(decliningCheckbox).not.toBeChecked();
    expect(sharpDeclineCheckbox).toBeChecked();
  });
});

describe('AutomationDetailPage — usage_trend empty selection is blocked (AC3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockGet.mockResolvedValue(usageTrendRule);
    mockListExecutions.mockResolvedValue([]);
    mockListPlaybooks.mockResolvedValue([]);
  });

  it('blocks saving when deselecting the only selected state', async () => {
    const user = userEvent.setup();
    render(<AutomationDetailPage />);

    const sharpDeclineCheckbox = await screen.findByTestId('trigger-config-state-sharp_decline');
    await user.click(sharpDeclineCheckbox);

    await user.click(screen.getByRole('button', { name: /save changes/i }));

    expect(mockUpdate).not.toHaveBeenCalled();
  });
});

describe('AutomationDetailPage — trigger-type switch seeds usage_trend defaults (AC5)', () => {
  const healthScoreRule = {
    ...usageTrendRule,
    mode: 'active' as const,
    trigger_type: 'health_score_threshold' as const,
    trigger_config: { threshold: 30, direction: 'below' },
    actions: [{ type: 'send_notification', config: { recipients: 'admins', channels: ['dashboard'] } }],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockGet.mockResolvedValue(healthScoreRule);
    mockListExecutions.mockResolvedValue([]);
    mockListPlaybooks.mockResolvedValue([]);
  });

  it('seeds usage_trend default states and defaults mode to shadow when switching in', async () => {
    const user = userEvent.setup();
    mockUpdate.mockResolvedValue({ ...healthScoreRule, trigger_type: 'usage_trend' });

    render(<AutomationDetailPage />);

    const triggerTypeSelect = await screen.findByTestId('trigger-type-select');
    await user.click(triggerTypeSelect);
    await user.click(await screen.findByRole('option', { name: 'Usage Trend' }));

    expect(await screen.findByTestId('trigger-config-state-declining')).toBeChecked();
    expect(screen.getByTestId('trigger-config-state-sharp_decline')).toBeChecked();
    expect(screen.getByTestId('rule-mode-select')).toHaveTextContent(/shadow/i);

    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith(
        9,
        expect.objectContaining({
          trigger: {
            type: 'usage_trend',
            config: { states: ['declining', 'sharp_decline'] },
          },
          mode: 'shadow',
        })
      );
    });
  });
});

describe('AutomationDetailPage — trigger-type switch away from usage_trend (AC5)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockGet.mockResolvedValue(usageTrendRule);
    mockListExecutions.mockResolvedValue([]);
    mockListPlaybooks.mockResolvedValue([]);
  });

  it('seeds the other trigger type defaults when switching away from usage_trend', async () => {
    const user = userEvent.setup();
    mockUpdate.mockResolvedValue({ ...usageTrendRule, trigger_type: 'health_score_threshold' });

    render(<AutomationDetailPage />);

    const triggerTypeSelect = await screen.findByTestId('trigger-type-select');
    await user.click(triggerTypeSelect);
    await user.click(await screen.findByRole('option', { name: 'Health Score Threshold' }));

    await waitFor(() => {
      expect(screen.getByTestId('trigger-config-threshold')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('trigger-config-state-declining')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith(
        9,
        expect.objectContaining({
          trigger: {
            type: 'health_score_threshold',
            config: { threshold: 30, direction: 'below' },
          },
        })
      );
    });
  });
});

describe('AutomationDetailPage — non-admin/owner gating on usage_trend controls (AC6)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: memberUser });
    mockGet.mockResolvedValue(usageTrendRule);
    mockListExecutions.mockResolvedValue([]);
    mockListPlaybooks.mockResolvedValue([]);
  });

  it('disables the states checkboxes for a member and hides Save', async () => {
    render(<AutomationDetailPage />);

    const decliningCheckbox = await screen.findByTestId('trigger-config-state-declining');
    const sharpDeclineCheckbox = await screen.findByTestId('trigger-config-state-sharp_decline');
    expect(decliningCheckbox).toBeDisabled();
    expect(sharpDeclineCheckbox).toBeDisabled();
    expect(screen.queryByRole('button', { name: /save changes/i })).not.toBeInTheDocument();
  });
});
