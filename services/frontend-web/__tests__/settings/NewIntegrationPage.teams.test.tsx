import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
const mockReplace = vi.fn();
const mockRouter = { push: mockPush, replace: mockReplace };
// Stable searchParams instance per test (re-assigned in beforeEach), avoids
// re-triggering effects that depend on identity.
let mockSearchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
  useSearchParams: () => mockSearchParams,
  usePathname: () => '/settings/integrations/new',
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@/lib/api/integrations', () => ({
  integrationsAPI: {
    createSlackWebhook: vi.fn(),
    createDiscordWebhook: vi.fn(),
    createTeamsWebhook: vi.fn(),
    getSlackOAuthUrl: vi.fn(),
    getIntercomOAuthUrl: vi.fn(),
    getTemplateVariables: vi.fn(),
  },
  TRIGGER_OPTIONS: [
    { value: 'urgent', label: 'Urgent Feedback', description: 'Alert on urgent feedback' },
    { value: 'negative', label: 'Negative Sentiment', description: 'Alert on negative sentiment' },
    { value: 'daily_digest', label: 'Daily Digest', description: 'Send a daily summary' },
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
vi.mock('@/components/icons/TeamsIcon', () => ({
  TeamsIcon: ({ className }: { className?: string }) => <svg data-testid="teams-icon" className={className} />,
}));

import { integrationsAPI } from '@/lib/api/integrations';
import NewIntegrationPage from '@/app/(dashboard)/settings/integrations/new/page';

const mockCreateSlackWebhook = integrationsAPI.createSlackWebhook as ReturnType<typeof vi.fn>;
const mockCreateDiscordWebhook = integrationsAPI.createDiscordWebhook as ReturnType<typeof vi.fn>;
const mockCreateTeamsWebhook = integrationsAPI.createTeamsWebhook as ReturnType<typeof vi.fn>;
const mockGetTemplateVariables = integrationsAPI.getTemplateVariables as ReturnType<typeof vi.fn>;

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

describe('NewIntegrationPage - Teams tile selection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockSearchParams = new URLSearchParams();
    mockGetTemplateVariables.mockResolvedValue(templateVariablesResponse);
  });

  it('test_teams_tile_selects_teams_and_hides_connection_method_and_oauth_blocks', async () => {
    const user = userEvent.setup();
    render(<NewIntegrationPage />);

    await waitFor(() => {
      expect(mockGetTemplateVariables).toHaveBeenCalled();
    });

    // Before selecting Teams, Slack's OAuth-related UI is present.
    expect(screen.getByText('Connection Method')).toBeInTheDocument();

    const teamsTile = screen.getByRole('button', { name: /Microsoft Teams[\s\S]*Get feedback alerts in your Teams channels/ });
    await user.click(teamsTile);

    // Header now reflects Teams.
    expect(screen.getByText('New Teams Integration')).toBeInTheDocument();

    // Connection Method picker (OAuth vs webhook) is Slack-only — must be gone.
    expect(screen.queryByText('Connection Method')).not.toBeInTheDocument();

    // Neither the Slack OAuth block nor the Intercom OAuth block should render.
    expect(screen.queryByText('Connect to Slack')).not.toBeInTheDocument();
    expect(screen.queryByText('Connect to Intercom')).not.toBeInTheDocument();

    // The webhook form (Teams is webhook-only) should render directly.
    expect(screen.getByText('Webhook Configuration')).toBeInTheDocument();
    expect(screen.getByLabelText('Webhook URL')).toBeInTheDocument();
  });

  it('test_teams_webhook_url_placeholder_and_messagecard_help_text', async () => {
    const user = userEvent.setup();
    render(<NewIntegrationPage />);

    await waitFor(() => expect(mockGetTemplateVariables).toHaveBeenCalled());

    const teamsTile = screen.getByRole('button', { name: /Microsoft Teams[\s\S]*Get feedback alerts in your Teams channels/ });
    await user.click(teamsTile);

    const urlInput = screen.getByLabelText('Webhook URL') as HTMLInputElement;
    expect(urlInput.placeholder).toBe('https://outlook.office.com/webhook/...');

    // Teams MessageCard copy, not Slack mrkdwn.
    expect(screen.getByText(/Teams MessageCard/)).toBeInTheDocument();
    expect(screen.queryByText(/Slack mrkdwn/)).not.toBeInTheDocument();
  });
});

describe('NewIntegrationPage - preselected via ?type=teams', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockSearchParams = new URLSearchParams('type=teams');
    mockGetTemplateVariables.mockResolvedValue(templateVariablesResponse);
  });

  it('test_type_query_param_preselects_teams', async () => {
    render(<NewIntegrationPage />);

    await waitFor(() => {
      expect(screen.getByText('New Teams Integration')).toBeInTheDocument();
    });
    expect(screen.queryByText('Connection Method')).not.toBeInTheDocument();
    // Teams icon renders both in the header and the selected provider tile.
    expect(screen.getAllByTestId('teams-icon').length).toBeGreaterThanOrEqual(1);
  });
});

describe('NewIntegrationPage - submit calls the right API per type', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockGetTemplateVariables.mockResolvedValue(templateVariablesResponse);
    mockCreateDiscordWebhook.mockResolvedValue({ id: 99, type: 'discord' });
    mockCreateSlackWebhook.mockResolvedValue({ id: 98, type: 'slack' });
    mockCreateTeamsWebhook.mockResolvedValue({ id: 97, type: 'teams' });
  });

  it('test_teams_submit_calls_createTeamsWebhook_not_createSlackWebhook', async () => {
    mockSearchParams = new URLSearchParams('type=teams');
    const user = userEvent.setup();
    render(<NewIntegrationPage />);

    await waitFor(() => expect(mockGetTemplateVariables).toHaveBeenCalled());

    await user.type(screen.getByPlaceholderText(/e.g., #feedback-alerts/), 'My Teams Channel');
    await user.type(
      screen.getByLabelText('Webhook URL'),
      'https://outlook.office.com/webhook/123-abc/456-def'
    );

    await user.click(screen.getByRole('button', { name: /Create Integration/ }));

    await waitFor(() => {
      expect(mockCreateTeamsWebhook).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'My Teams Channel',
          webhook_url: 'https://outlook.office.com/webhook/123-abc/456-def',
        })
      );
    });
    expect(mockCreateSlackWebhook).not.toHaveBeenCalled();
    expect(mockCreateDiscordWebhook).not.toHaveBeenCalled();
    expect(mockPush).toHaveBeenCalledWith('/settings/integrations');
  });

  it('test_teams_submit_accepts_tenant_subdomain_workflows_url', async () => {
    mockSearchParams = new URLSearchParams('type=teams');
    const user = userEvent.setup();
    render(<NewIntegrationPage />);

    await waitFor(() => expect(mockGetTemplateVariables).toHaveBeenCalled());

    await user.type(screen.getByPlaceholderText(/e.g., #feedback-alerts/), 'Workflows Connector');
    await user.type(
      screen.getByLabelText('Webhook URL'),
      'https://contoso.webhook.office.com/webhookb2/abc@def/IncomingWebhook/xyz/aaa'
    );

    await user.click(screen.getByRole('button', { name: /Create Integration/ }));

    await waitFor(() => {
      expect(mockCreateTeamsWebhook).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Workflows Connector',
          webhook_url: 'https://contoso.webhook.office.com/webhookb2/abc@def/IncomingWebhook/xyz/aaa',
        })
      );
    });
  });

  it('test_teams_submit_rejects_non_teams_url_client_side', async () => {
    mockSearchParams = new URLSearchParams('type=teams');
    const user = userEvent.setup();
    render(<NewIntegrationPage />);

    await waitFor(() => expect(mockGetTemplateVariables).toHaveBeenCalled());

    await user.type(screen.getByPlaceholderText(/e.g., #feedback-alerts/), 'Bad URL Test');
    await user.type(
      screen.getByLabelText('Webhook URL'),
      'https://example.com/webhook/abc'
    );

    await user.click(screen.getByRole('button', { name: /Create Integration/ }));

    await waitFor(() => {
      expect(screen.getByText(/Invalid Teams webhook URL/)).toBeInTheDocument();
    });
    expect(mockCreateTeamsWebhook).not.toHaveBeenCalled();
  });

  it('test_slack_webhook_submit_still_calls_createSlackWebhook', async () => {
    mockSearchParams = new URLSearchParams();
    const user = userEvent.setup();
    render(<NewIntegrationPage />);

    await waitFor(() => expect(mockGetTemplateVariables).toHaveBeenCalled());

    // Slack defaults to OAuth — switch to the webhook connection method.
    await user.click(screen.getByRole('button', { name: /Webhook URL[\s\S]*Manual setup/ }));

    await user.type(screen.getByPlaceholderText(/e.g., #feedback-alerts/), 'My Slack Channel');
    await user.type(
      screen.getByLabelText('Webhook URL'),
      'https://hooks.slack.com/services/T00/B00/xxx'
    );

    await user.click(screen.getByRole('button', { name: /Create Integration/ }));

    await waitFor(() => {
      expect(mockCreateSlackWebhook).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'My Slack Channel',
          webhook_url: 'https://hooks.slack.com/services/T00/B00/xxx',
        })
      );
    });
    expect(mockCreateTeamsWebhook).not.toHaveBeenCalled();
  });
});

describe('NewIntegrationPage - member redirect', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: memberUser });
    mockSearchParams = new URLSearchParams();
    mockGetTemplateVariables.mockResolvedValue(templateVariablesResponse);
  });

  it('redirects a member user to /settings/preferences and does not render the connect form', async () => {
    render(<NewIntegrationPage />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/settings/preferences');
    });

    expect(screen.queryByText('Connect to Slack')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Create Integration/ })).not.toBeInTheDocument();
    expect(mockGetTemplateVariables).not.toHaveBeenCalled();
  });
});