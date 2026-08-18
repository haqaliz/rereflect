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

import { integrationsAPI } from '@/lib/api/integrations';
import NewIntegrationPage from '@/app/(dashboard)/settings/integrations/new/page';

const mockCreateSlackWebhook = integrationsAPI.createSlackWebhook as ReturnType<typeof vi.fn>;
const mockCreateDiscordWebhook = integrationsAPI.createDiscordWebhook as ReturnType<typeof vi.fn>;
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

describe('NewIntegrationPage - Discord tile selection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockSearchParams = new URLSearchParams();
    mockGetTemplateVariables.mockResolvedValue(templateVariablesResponse);
  });

  it('test_discord_tile_selects_discord_and_hides_connection_method_and_oauth_blocks', async () => {
    const user = userEvent.setup();
    render(<NewIntegrationPage />);

    await waitFor(() => {
      expect(mockGetTemplateVariables).toHaveBeenCalled();
    });

    // Before selecting Discord, Slack's OAuth-related UI is present.
    expect(screen.getByText('Connection Method')).toBeInTheDocument();

    const discordTile = screen.getByRole('button', { name: /Discord[\s\S]*Get feedback alerts in your Discord server/ });
    await user.click(discordTile);

    // Header now reflects Discord.
    expect(screen.getByText('New Discord Integration')).toBeInTheDocument();

    // Connection Method picker (OAuth vs webhook) is Slack-only — must be gone.
    expect(screen.queryByText('Connection Method')).not.toBeInTheDocument();

    // Neither the Slack OAuth block nor the Intercom OAuth block should render.
    expect(screen.queryByText('Connect to Slack')).not.toBeInTheDocument();
    expect(screen.queryByText('Connect to Intercom')).not.toBeInTheDocument();

    // The webhook form (Discord is webhook-only) should render directly.
    expect(screen.getByText('Webhook Configuration')).toBeInTheDocument();
    expect(screen.getByLabelText('Webhook URL')).toBeInTheDocument();
  });

  it('test_discord_webhook_url_placeholder_and_markdown_help_text', async () => {
    const user = userEvent.setup();
    render(<NewIntegrationPage />);

    await waitFor(() => expect(mockGetTemplateVariables).toHaveBeenCalled());

    const discordTile = screen.getByRole('button', { name: /Discord[\s\S]*Get feedback alerts in your Discord server/ });
    await user.click(discordTile);

    const urlInput = screen.getByLabelText('Webhook URL') as HTMLInputElement;
    expect(urlInput.placeholder).toBe('https://discord.com/api/webhooks/...');

    // Discord markdown, not Slack mrkdwn (per spec: **bold** not *bold*).
    expect(screen.getByText(/Discord markdown: \*\*bold\*\*/)).toBeInTheDocument();
    expect(screen.queryByText(/Slack mrkdwn/)).not.toBeInTheDocument();
  });
});

describe('NewIntegrationPage - preselected via ?type=discord', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockSearchParams = new URLSearchParams('type=discord');
    mockGetTemplateVariables.mockResolvedValue(templateVariablesResponse);
  });

  it('test_type_query_param_preselects_discord', async () => {
    render(<NewIntegrationPage />);

    await waitFor(() => {
      expect(screen.getByText('New Discord Integration')).toBeInTheDocument();
    });
    expect(screen.queryByText('Connection Method')).not.toBeInTheDocument();
    // Discord icon renders both in the header and the selected provider tile.
    expect(screen.getAllByTestId('discord-icon').length).toBeGreaterThanOrEqual(1);
  });
});

describe('NewIntegrationPage - submit calls the right API per type', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockGetTemplateVariables.mockResolvedValue(templateVariablesResponse);
    mockCreateDiscordWebhook.mockResolvedValue({ id: 99, type: 'discord' });
    mockCreateSlackWebhook.mockResolvedValue({ id: 98, type: 'slack' });
  });

  it('test_discord_submit_calls_createDiscordWebhook_not_createSlackWebhook', async () => {
    mockSearchParams = new URLSearchParams('type=discord');
    const user = userEvent.setup();
    render(<NewIntegrationPage />);

    await waitFor(() => expect(mockGetTemplateVariables).toHaveBeenCalled());

    await user.type(screen.getByPlaceholderText(/e.g., #feedback-alerts/), 'My Discord Channel');
    await user.type(
      screen.getByLabelText('Webhook URL'),
      'https://discord.com/api/webhooks/123/abc'
    );

    await user.click(screen.getByRole('button', { name: /Create Integration/ }));

    await waitFor(() => {
      expect(mockCreateDiscordWebhook).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'My Discord Channel',
          webhook_url: 'https://discord.com/api/webhooks/123/abc',
        })
      );
    });
    expect(mockCreateSlackWebhook).not.toHaveBeenCalled();
    expect(mockPush).toHaveBeenCalledWith('/settings/integrations');
  });

  it('test_discord_submit_rejects_non_discord_url_client_side', async () => {
    mockSearchParams = new URLSearchParams('type=discord');
    const user = userEvent.setup();
    render(<NewIntegrationPage />);

    await waitFor(() => expect(mockGetTemplateVariables).toHaveBeenCalled());

    await user.type(screen.getByPlaceholderText(/e.g., #feedback-alerts/), 'Bad URL Test');
    await user.type(
      screen.getByLabelText('Webhook URL'),
      'https://hooks.slack.com/services/T00/B00/xxx'
    );

    await user.click(screen.getByRole('button', { name: /Create Integration/ }));

    await waitFor(() => {
      expect(screen.getByText(/Discord webhook URLs must start with/)).toBeInTheDocument();
    });
    expect(mockCreateDiscordWebhook).not.toHaveBeenCalled();
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
    expect(mockCreateDiscordWebhook).not.toHaveBeenCalled();
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
