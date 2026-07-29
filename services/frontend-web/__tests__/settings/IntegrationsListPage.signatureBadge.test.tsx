import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
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
    signature_verification_configured: true,
    ...overrides,
  };
}

describe('IntegrationsPage - unverified signature badge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
  });

  it('test_unconfigured_slack_integration_shows_unverified_badge', async () => {
    mockList.mockResolvedValue({
      integrations: [
        makeIntegration({
          id: 1,
          type: 'slack',
          name: 'Slack Alerts',
          signature_verification_configured: false,
        }),
      ],
      total: 1,
    });

    render(<IntegrationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Slack Alerts')).toBeInTheDocument();
    });

    const slackRow = screen.getByText('Slack Alerts').closest('div.p-4') as HTMLElement;
    expect(within(slackRow).getByText(/signature.*not.*verified|not.*verified|unverified/i)).toBeInTheDocument();
  });

  it('test_configured_slack_integration_shows_no_badge', async () => {
    mockList.mockResolvedValue({
      integrations: [
        makeIntegration({
          id: 1,
          type: 'slack',
          name: 'Slack Alerts',
          signature_verification_configured: true,
        }),
      ],
      total: 1,
    });

    render(<IntegrationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Slack Alerts')).toBeInTheDocument();
    });

    const slackRow = screen.getByText('Slack Alerts').closest('div.p-4') as HTMLElement;
    expect(within(slackRow).queryByText(/signature.*not.*verified|not.*verified|unverified/i)).not.toBeInTheDocument();
  });

  it('test_unconfigured_intercom_integration_shows_unverified_badge_with_docs_link', async () => {
    mockList.mockResolvedValue({
      integrations: [
        makeIntegration({
          id: 2,
          type: 'intercom',
          name: 'Intercom Bridge',
          signature_verification_configured: false,
        }),
      ],
      total: 1,
    });

    render(<IntegrationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Intercom Bridge')).toBeInTheDocument();
    });

    const intercomRow = screen.getByText('Intercom Bridge').closest('div.p-4') as HTMLElement;
    const badge = within(intercomRow).getByText(/signature.*not.*verified|not.*verified|unverified/i);
    expect(badge).toBeInTheDocument();

    const docsLink = within(intercomRow).getByRole('link', { name: /self.hosting|docs/i });
    expect(docsLink).toHaveAttribute('href', expect.stringContaining('SELF_HOSTING.md'));
  });
});
