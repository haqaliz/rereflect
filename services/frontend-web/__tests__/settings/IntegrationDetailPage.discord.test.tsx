import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React, { Suspense } from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
const mockReplace = vi.fn();
const mockRouter = { push: mockPush, replace: mockReplace };
vi.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@/lib/api/integrations', () => ({
  integrationsAPI: {
    get: vi.fn(),
    getLogs: vi.fn(),
    getTemplateVariables: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    testSlack: vi.fn(),
    testDiscord: vi.fn(),
  },
  TRIGGER_OPTIONS: [
    { value: 'urgent', label: 'Urgent Feedback', description: 'Alert on urgent feedback' },
    { value: 'negative', label: 'Negative Sentiment', description: 'Alert on negative sentiment' },
  ],
}));

vi.mock('@/components/icons/SlackIcon', () => ({
  SlackIcon: ({ className }: { className?: string }) => <svg data-testid="slack-icon" className={className} />,
}));
vi.mock('@/components/icons/IntercomIcon', () => ({
  IntercomIcon: ({ className }: { className?: string }) => <svg data-testid="intercom-icon" className={className} />,
}));
vi.mock('@/components/icons/DiscordIcon', () => ({
  DiscordIcon: ({ className }: { className?: string }) => <svg data-testid="discord-icon" className={className} />,
}));

import { integrationsAPI } from '@/lib/api/integrations';
import IntegrationDetailPage from '@/app/(dashboard)/settings/integrations/[id]/page';

const mockGet = integrationsAPI.get as ReturnType<typeof vi.fn>;
const mockGetLogs = integrationsAPI.getLogs as ReturnType<typeof vi.fn>;
const mockGetTemplateVariables = integrationsAPI.getTemplateVariables as ReturnType<typeof vi.fn>;
const mockTestSlack = integrationsAPI.testSlack as ReturnType<typeof vi.fn>;
const mockTestDiscord = integrationsAPI.testDiscord as ReturnType<typeof vi.fn>;

const templateVariablesResponse = {
  variables: [{ name: 'text', description: 'Feedback text', example: 'Great product!' }],
  default_template: 'New feedback: {{text}}',
};

const adminUser = {
  id: 1,
  email: 'admin@test.com',
  role: 'admin',
  plan: 'enterprise',
  organization_id: 1,
  is_system_admin: false,
};

const memberUser = {
  id: 2,
  email: 'member@test.com',
  role: 'member',
  plan: 'enterprise',
  organization_id: 1,
  is_system_admin: false,
};

function makeIntegration(overrides: Partial<Record<string, any>> = {}) {
  return {
    id: 1,
    type: 'slack',
    name: 'My Integration',
    integration_type: 'webhook',
    channel_name: null,
    team_name: null,
    triggers: ['urgent'],
    included_fields: [],
    digest_time: null,
    message_template: null,
    is_active: true,
    last_used_at: null,
    error_count: 0,
    last_error: null,
    created_at: '2026-07-01T00:00:00Z',
    ...overrides,
  };
}

// `use(params)` suspends on the first render even though the promise is
// already resolved — React only learns that once it attaches its own .then()
// and the microtask queue drains. Wrapping the initial render in `act()`
// flushes that before we start asserting, which a bare `waitFor` after a
// non-`act`-wrapped `render()` does not reliably do for this hook in jsdom.
async function renderDetailPage(id = '1') {
  let utils: ReturnType<typeof render>;
  await act(async () => {
    utils = render(
      <Suspense fallback={<div>Loading page…</div>}>
        <IntegrationDetailPage params={Promise.resolve({ id })} />
      </Suspense>
    );
  });
  return utils!;
}

describe('IntegrationDetailPage - Discord row', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockGetLogs.mockResolvedValue([]);
    mockGetTemplateVariables.mockResolvedValue(templateVariablesResponse);
  });

  it('test_discord_integration_renders_discord_icon_not_slack', async () => {
    mockGet.mockResolvedValue(makeIntegration({ id: 2, type: 'discord', name: 'Discord Alerts' }));

    await renderDetailPage('2');

    await waitFor(() => {
      expect(screen.getByText('Discord Alerts')).toBeInTheDocument();
    });

    expect(screen.getByTestId('discord-icon')).toBeInTheDocument();
    expect(screen.queryByTestId('slack-icon')).not.toBeInTheDocument();
    expect(screen.getByText('Configure your Discord integration')).toBeInTheDocument();
  });

  it('test_slack_integration_still_renders_slack_icon', async () => {
    mockGet.mockResolvedValue(makeIntegration({ id: 1, type: 'slack', name: 'Slack Alerts' }));

    await renderDetailPage('1');

    await waitFor(() => {
      expect(screen.getByText('Slack Alerts')).toBeInTheDocument();
    });

    expect(screen.getByTestId('slack-icon')).toBeInTheDocument();
    expect(screen.queryByTestId('discord-icon')).not.toBeInTheDocument();
  });

  it('test_discord_markdown_help_text_replaces_slack_mrkdwn', async () => {
    mockGet.mockResolvedValue(makeIntegration({ id: 2, type: 'discord', name: 'Discord Alerts' }));

    await renderDetailPage('2');

    await waitFor(() => {
      expect(screen.getByText('Discord Alerts')).toBeInTheDocument();
    });

    expect(screen.getByText(/Discord markdown: \*\*bold\*\*/)).toBeInTheDocument();
    expect(screen.queryByText(/Slack mrkdwn/)).not.toBeInTheDocument();
  });
});

describe('IntegrationDetailPage - Test button dispatches per integration type', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockGetLogs.mockResolvedValue([]);
    mockGetTemplateVariables.mockResolvedValue(templateVariablesResponse);
    mockTestSlack.mockResolvedValue({ success: true, message: 'Slack test sent' });
    mockTestDiscord.mockResolvedValue({ success: true, message: 'Discord test sent' });
  });

  it('test_discord_test_button_calls_testDiscord_not_testSlack', async () => {
    mockGet.mockResolvedValue(makeIntegration({ id: 2, type: 'discord', name: 'Discord Alerts' }));
    const user = userEvent.setup();

    await renderDetailPage('2');

    await waitFor(() => {
      expect(screen.getByText('Discord Alerts')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /^Test$/ }));

    await waitFor(() => {
      expect(mockTestDiscord).toHaveBeenCalledWith(2);
    });
    expect(mockTestSlack).not.toHaveBeenCalled();
  });

  it('test_slack_test_button_still_calls_testSlack', async () => {
    mockGet.mockResolvedValue(makeIntegration({ id: 1, type: 'slack', name: 'Slack Alerts' }));
    const user = userEvent.setup();

    await renderDetailPage('1');

    await waitFor(() => {
      expect(screen.getByText('Slack Alerts')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /^Test$/ }));

    await waitFor(() => {
      expect(mockTestSlack).toHaveBeenCalledWith(1);
    });
    expect(mockTestDiscord).not.toHaveBeenCalled();
  });
});

describe('IntegrationDetailPage - member redirect', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: memberUser });
    mockGetLogs.mockResolvedValue([]);
    mockGetTemplateVariables.mockResolvedValue(templateVariablesResponse);
  });

  it('redirects a member user to /settings/preferences and does not render the admin surface', async () => {
    mockGet.mockResolvedValue(makeIntegration({ id: 1, type: 'slack', name: 'Slack Alerts' }));

    await renderDetailPage('1');

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/settings/preferences');
    });

    expect(screen.queryByRole('button', { name: /^Test$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Delete/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Save Changes/ })).not.toBeInTheDocument();
    expect(mockGet).not.toHaveBeenCalled();
  });
});
