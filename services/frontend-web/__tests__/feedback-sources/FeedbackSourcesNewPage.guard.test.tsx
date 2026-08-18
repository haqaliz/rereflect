import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
const mockRouter = { push: mockPush, replace: vi.fn() };
let mockSearchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
  useSearchParams: () => mockSearchParams,
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@/lib/api/feedback-sources', () => ({
  feedbackSourcesAPI: {
    getTypes: vi.fn(),
    create: vi.fn(),
  },
  DEFAULT_TRIGGERS: {
    all_messages: false,
    reactions: [],
    mentions: { bot: true, users: [] },
    keywords: [],
    labels: [],
    custom_rules: [],
    new_ticket: false,
  },
  DEFAULT_FIELD_MAPPING: {
    text_source: 'message',
    include_author: true,
    include_source_name: true,
    include_context: false,
    max_context_messages: 5,
    custom_template: null,
  },
  TRIGGER_OPTIONS: {
    webhook: [
      { key: 'all_messages', label: 'All Requests', description: 'Process every incoming request' },
      { key: 'keywords', label: 'Content Match (optional)', description: 'Requests containing keywords', hasValues: true },
    ],
  },
}));

vi.mock('@/lib/api/integrations', () => ({
  integrationsAPI: { list: vi.fn(() => Promise.resolve({ integrations: [] })) },
}));
vi.mock('@/lib/api/linear', () => ({
  linearAPI: { getStatus: vi.fn(() => Promise.resolve({ connected: false })) },
}));
vi.mock('@/lib/api/jira', () => ({
  jiraAPI: { getStatus: vi.fn(() => Promise.resolve({ connected: false })) },
}));
vi.mock('@/lib/api/zendesk', () => ({
  zendeskAPI: { getStatus: vi.fn(() => Promise.resolve({ connected: false })) },
}));

vi.mock('@/components/icons/SlackIcon', () => ({
  SlackIcon: ({ className }: { className?: string }) => <svg data-testid="slack-icon" className={className} />,
}));
vi.mock('@/components/icons/IntercomIcon', () => ({
  IntercomIcon: ({ className }: { className?: string }) => <svg data-testid="intercom-icon" className={className} />,
}));
vi.mock('@/components/icons/LinearIcon', () => ({
  LinearIcon: ({ className }: { className?: string }) => <svg data-testid="linear-icon" className={className} />,
}));
vi.mock('@/components/icons/JiraIcon', () => ({
  JiraIcon: ({ className }: { className?: string }) => <svg data-testid="jira-icon" className={className} />,
}));
vi.mock('@/components/icons/ZendeskIcon', () => ({
  ZendeskIcon: ({ className }: { className?: string }) => <svg data-testid="zendesk-icon" className={className} />,
}));

import { feedbackSourcesAPI } from '@/lib/api/feedback-sources';
import NewFeedbackSourcePage from '@/app/(dashboard)/feedback-sources/new/page';

const mockGetTypes = feedbackSourcesAPI.getTypes as ReturnType<typeof vi.fn>;

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

const sourceTypes = [
  { type: 'webhook', name: 'Webhook', description: 'Send events via HTTP', requires_integration: false, available: true },
  { type: 'slack', name: 'Slack', description: 'Capture messages from Slack', requires_integration: true, available: true },
];

// `?type=webhook` skips straight to the triggers step (no integration
// required), so two Continue clicks reach the confirm step with Create Source.
async function goToConfirmStep() {
  render(<NewFeedbackSourcePage />);
  const user = userEvent.setup();
  await waitFor(() => expect(screen.getByText('Configure Triggers')).toBeInTheDocument());
  await user.click(screen.getByRole('button', { name: /^Continue$/ }));
  await screen.findByText('Include Author Info');
  await user.click(screen.getByRole('button', { name: /^Continue$/ }));
  await screen.findByText('Confirm Settings');
}

describe('NewFeedbackSourcePage — member role', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: memberUser });
    mockSearchParams = new URLSearchParams('type=webhook');
    mockGetTypes.mockResolvedValue(sourceTypes);
  });

  it('hides the Create Source button while keeping the wizard reads visible', async () => {
    await goToConfirmStep();

    expect(screen.queryByRole('button', { name: /create source/i })).not.toBeInTheDocument();
  });
});

describe('NewFeedbackSourcePage — admin role', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockSearchParams = new URLSearchParams('type=webhook');
    mockGetTypes.mockResolvedValue(sourceTypes);
  });

  it('shows the Create Source button on the confirm step for admins', async () => {
    await goToConfirmStep();

    expect(screen.getByRole('button', { name: /create source/i })).toBeInTheDocument();
  });
});
