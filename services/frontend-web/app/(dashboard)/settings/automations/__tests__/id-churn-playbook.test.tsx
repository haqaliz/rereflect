/**
 * Tests for the churn-triggered-playbooks additions to the automation rule
 * detail/edit page: the `churn_probability_threshold` trigger config, the
 * `run_playbook` action config (playbook picker), and the off|shadow|active
 * rule `mode` selector — including that non-admin/owner users see it
 * disabled (mirrors the existing isAdminOrOwner field-disabling pattern).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// ─── mocks ──────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => ({ id: '5' }),
  usePathname: () => '/settings/automations/5',
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

const playbookFixtures = [
  { id: 3, organization_id: 1, name: 'Win-back offer', description: null, probability_min: 0.5, probability_max: 1, action_sequence: [], is_template: false, is_active: true, source_template_id: null, created_at: '', updated_at: '' },
];

const churnRule = {
  id: 5,
  name: 'Churn playbook rule',
  description: 'Runs a playbook when probability is high',
  is_active: true,
  mode: 'shadow' as const,
  trigger_type: 'churn_probability_threshold' as const,
  trigger_config: { threshold: 0.72, direction: 'above' },
  actions: [{ type: 'run_playbook', config: { playbook_id: 3 } }],
  cooldown_hours: 24,
  execution_count: 4,
  last_executed_at: null,
  is_template: false,
  template_id: null,
  created_at: '2026-05-01T00:00:00Z',
};

describe('AutomationDetailPage — churn_probability_threshold trigger', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockGet.mockResolvedValue(churnRule);
    mockListExecutions.mockResolvedValue([]);
    mockListPlaybooks.mockResolvedValue(playbookFixtures);
  });

  it('renders the threshold input pre-populated from trigger_config', async () => {
    render(<AutomationDetailPage />);
    const thresholdInput = await screen.findByTestId('trigger-config-churn-threshold');
    expect(thresholdInput).toHaveValue(0.72);
  });
});

describe('AutomationDetailPage — run_playbook action', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockGet.mockResolvedValue(churnRule);
    mockListExecutions.mockResolvedValue([]);
    mockListPlaybooks.mockResolvedValue(playbookFixtures);
  });

  it('renders the playbook picker pre-selected with the existing playbook', async () => {
    render(<AutomationDetailPage />);
    const playbookSelect = await screen.findByTestId('action-config-playbook');
    expect(playbookSelect).toHaveTextContent('Win-back offer');
  });
});

describe('AutomationDetailPage — rule mode selector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockGet.mockResolvedValue(churnRule);
    mockListExecutions.mockResolvedValue([]);
    mockListPlaybooks.mockResolvedValue(playbookFixtures);
  });

  it('reflects the loaded mode and sends the updated mode on save', async () => {
    const user = userEvent.setup();
    mockUpdate.mockResolvedValue({ ...churnRule, mode: 'active' });

    render(<AutomationDetailPage />);

    const modeSelect = await screen.findByTestId('rule-mode-select');
    expect(modeSelect).toHaveTextContent(/shadow/i);

    await user.click(modeSelect);
    await user.click(await screen.findByRole('option', { name: 'Active' }));

    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith(5, expect.objectContaining({ mode: 'active' }));
    });
  });
});

describe('AutomationDetailPage — trigger-type switch seeds defaults', () => {
  const healthScoreRule = {
    ...churnRule,
    trigger_type: 'health_score_threshold' as const,
    trigger_config: { threshold: 30, direction: 'below' },
    actions: [{ type: 'send_notification', config: { recipients: 'admins', channels: ['dashboard'] } }],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockGet.mockResolvedValue(healthScoreRule);
    mockListExecutions.mockResolvedValue([]);
    mockListPlaybooks.mockResolvedValue(playbookFixtures);
  });

  it('seeds churn threshold defaults when switching trigger type without editing them, and saves them', async () => {
    const user = userEvent.setup();
    mockUpdate.mockResolvedValue({ ...healthScoreRule, trigger_type: 'churn_probability_threshold' });

    render(<AutomationDetailPage />);

    const triggerTypeSelect = await screen.findByTestId('trigger-type-select');
    await user.click(triggerTypeSelect);
    await user.click(await screen.findByRole('option', { name: 'Churn probability threshold' }));

    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith(
        5,
        expect.objectContaining({
          trigger: {
            type: 'churn_probability_threshold',
            config: { threshold: 0.7, direction: 'above' },
          },
        })
      );
    });
  });
});

describe('AutomationDetailPage — non-admin/owner gating', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: memberUser });
    mockGet.mockResolvedValue(churnRule);
    mockListExecutions.mockResolvedValue([]);
    mockListPlaybooks.mockResolvedValue(playbookFixtures);
  });

  it('disables the mode selector and hides Save for a member', async () => {
    render(<AutomationDetailPage />);

    const modeSelect = await screen.findByTestId('rule-mode-select');
    expect(modeSelect).toBeDisabled();
    expect(screen.queryByRole('button', { name: /save changes/i })).not.toBeInTheDocument();
  });
});
