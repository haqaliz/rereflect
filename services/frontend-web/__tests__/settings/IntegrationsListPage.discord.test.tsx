import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
const mockReplace = vi.fn();
// Stable references — a fresh object/URLSearchParams on every render would
// re-trigger the page's `useEffect(..., [searchParams, router])` forever.
const mockRouter = { push: mockPush, replace: mockReplace };
const mockSearchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
  useSearchParams: () => mockSearchParams,
  usePathname: () => '/settings/integrations',
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@/lib/api/integrations', () => ({
  integrationsAPI: {
    list: vi.fn(),
    delete: vi.fn(),
    testSlack: vi.fn(),
    testDiscord: vi.fn(),
  },
  TRIGGER_OPTIONS: [
    { value: 'urgent', label: 'Urgent Feedback', description: 'Alert on urgent feedback' },
    { value: 'negative', label: 'Negative Sentiment', description: 'Alert on negative sentiment' },
  ],
}));

vi.mock('@/lib/api/linear', () => ({ linearAPI: { getStatus: vi.fn().mockResolvedValue({ connected: false }) } }));
vi.mock('@/lib/api/hubspot', () => ({ hubspotAPI: { getStatus: vi.fn().mockResolvedValue({ connected: false }) } }));
vi.mock('@/lib/api/salesforce', () => ({ salesforceAPI: { getStatus: vi.fn().mockResolvedValue({ connected: false }) } }));
vi.mock('@/lib/api/jira', () => ({ jiraAPI: { getStatus: vi.fn().mockResolvedValue({ connected: false }) } }));
vi.mock('@/lib/api/zendesk', () => ({ zendeskAPI: { getStatus: vi.fn().mockResolvedValue({ connected: false }) } }));
vi.mock('@/lib/api/asana', () => ({ asanaAPI: { getStatus: vi.fn().mockResolvedValue({ connected: false }) } }));

// Icons — swap for identifiable stubs so we can assert which one rendered
// without depending on SVG path internals.
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
import IntegrationsPage from '@/app/(dashboard)/settings/integrations/page';

const mockList = integrationsAPI.list as ReturnType<typeof vi.fn>;
const mockTestSlack = integrationsAPI.testSlack as ReturnType<typeof vi.fn>;
const mockTestDiscord = integrationsAPI.testDiscord as ReturnType<typeof vi.fn>;

const adminUser = {
  id: 1,
  email: 'admin@test.com',
  role: 'admin',
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

describe('IntegrationsPage - Discord row rendering', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
  });

  it('test_discord_row_renders_discord_icon_not_slack', async () => {
    mockList.mockResolvedValue({
      integrations: [
        makeIntegration({ id: 1, type: 'slack', name: 'Slack Alerts' }),
        makeIntegration({ id: 2, type: 'discord', name: 'Discord Alerts' }),
      ],
      total: 2,
    });

    render(<IntegrationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Slack Alerts')).toBeInTheDocument();
    });

    const slackRow = screen.getByText('Slack Alerts').closest('div.p-4') as HTMLElement;
    const discordRow = screen.getByText('Discord Alerts').closest('div.p-4') as HTMLElement;

    expect(within(slackRow).getByTestId('slack-icon')).toBeInTheDocument();
    expect(within(slackRow).queryByTestId('discord-icon')).not.toBeInTheDocument();

    expect(within(discordRow).getByTestId('discord-icon')).toBeInTheDocument();
    expect(within(discordRow).queryByTestId('slack-icon')).not.toBeInTheDocument();
  });

  it('test_intercom_row_still_renders_intercom_icon', async () => {
    mockList.mockResolvedValue({
      integrations: [makeIntegration({ id: 3, type: 'intercom', name: 'Intercom Bridge' })],
      total: 1,
    });

    render(<IntegrationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Intercom Bridge')).toBeInTheDocument();
    });

    const intercomRow = screen.getByText('Intercom Bridge').closest('div.p-4') as HTMLElement;
    expect(within(intercomRow).getByTestId('intercom-icon')).toBeInTheDocument();
    expect(within(intercomRow).queryByTestId('slack-icon')).not.toBeInTheDocument();
    expect(within(intercomRow).queryByTestId('discord-icon')).not.toBeInTheDocument();
  });
});

describe('IntegrationsPage - Test button dispatches per integration type', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockList.mockResolvedValue({
      integrations: [
        makeIntegration({ id: 1, type: 'slack', name: 'Slack Alerts' }),
        makeIntegration({ id: 2, type: 'discord', name: 'Discord Alerts' }),
      ],
      total: 2,
    });
    mockTestSlack.mockResolvedValue({ success: true, message: 'Slack test sent' });
    mockTestDiscord.mockResolvedValue({ success: true, message: 'Discord test sent' });
  });

  it('test_discord_row_test_button_calls_testDiscord_not_testSlack', async () => {
    const user = userEvent.setup();
    render(<IntegrationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Discord Alerts')).toBeInTheDocument();
    });

    const discordRow = screen.getByText('Discord Alerts').closest('div.p-4') as HTMLElement;
    const testButton = within(discordRow).getByTitle('Send test message');
    await user.click(testButton);

    await waitFor(() => {
      expect(mockTestDiscord).toHaveBeenCalledWith(2);
    });
    expect(mockTestSlack).not.toHaveBeenCalled();
  });

  it('test_slack_row_test_button_still_calls_testSlack', async () => {
    const user = userEvent.setup();
    render(<IntegrationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Slack Alerts')).toBeInTheDocument();
    });

    const slackRow = screen.getByText('Slack Alerts').closest('div.p-4') as HTMLElement;
    const testButton = within(slackRow).getByTitle('Send test message');
    await user.click(testButton);

    await waitFor(() => {
      expect(mockTestSlack).toHaveBeenCalledWith(1);
    });
    expect(mockTestDiscord).not.toHaveBeenCalled();
  });
});

describe('IntegrationsPage - Discord available card', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockList.mockResolvedValue({ integrations: [], total: 0 });
  });

  it('test_discord_card_is_available_and_links_to_new_discord_flow', async () => {
    render(<IntegrationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Available Integrations')).toBeInTheDocument();
    });

    const discordHeading = screen.getByText('Discord', { selector: 'span' });
    const discordCard = discordHeading.closest('a');
    expect(discordCard).toHaveAttribute('href', '/settings/integrations/new?type=discord');

    // The card is no longer disabled "Coming Soon" — it says "Available" like Slack/Intercom.
    const discordCardBody = discordHeading.closest('div.p-4') as HTMLElement;
    expect(within(discordCardBody).getByText('Available')).toBeInTheDocument();
    expect(within(discordCardBody).queryByText('Coming Soon')).not.toBeInTheDocument();
    expect(discordCardBody.className).not.toContain('cursor-not-allowed');
    expect(discordCardBody.className).not.toContain('opacity-60');
  });
});
