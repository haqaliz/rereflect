import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@/lib/api/feedback-sources', () => ({
  feedbackSourcesAPI: {
    list: vi.fn(),
    getTypes: vi.fn(),
  },
}));

import { feedbackSourcesAPI } from '@/lib/api/feedback-sources';
import FeedbackSourcesPage from '@/app/(dashboard)/feedback-sources/page';

const mockList = feedbackSourcesAPI.list as ReturnType<typeof vi.fn>;
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

function makeSource(overrides: Partial<Record<string, any>> = {}) {
  return {
    id: 1,
    organization_id: 1,
    integration_id: null,
    source_type: 'webhook',
    name: 'Product Webhook',
    provider_config: {},
    triggers: { all_messages: true },
    field_mapping: { text_source: 'message', include_author: true, include_source_name: true, include_context: false, max_context_messages: 5, custom_template: null },
    auto_import: true,
    is_active: true,
    last_event_at: null,
    events_processed: 0,
    error_count: 0,
    last_error: null,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    webhook_url: 'https://hooks.example.com/rereflect/abc',
    ...overrides,
  };
}

const sourceTypes = [
  { type: 'webhook', name: 'Webhook', description: 'Send events via HTTP', requires_integration: false, available: true },
  { type: 'slack', name: 'Slack', description: 'Capture messages from Slack', requires_integration: true, available: true },
  { type: 'discord', name: 'Discord', description: 'Capture messages from Discord', requires_integration: false, available: false },
];

function renderPage() {
  render(<FeedbackSourcesPage />);
}

describe('FeedbackSourcesPage — member role', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: memberUser });
    mockGetTypes.mockResolvedValue(sourceTypes);
  });

  it('hides all write controls but keeps reads visible for members', async () => {
    mockList.mockResolvedValue({
      sources: [makeSource({ id: 1, source_type: 'slack', name: 'Support Slack', provider_config: { channel_name: 'support' } })],
      total: 1,
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Support Slack')).toBeInTheDocument();
    });

    // Reads: source name, webhook URL, pending queue link.
    expect(screen.getByText('Support Slack')).toBeInTheDocument();
    expect(screen.getByText('Available Source Types')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /pending queue/i })).toBeInTheDocument();

    // Writes hidden: Add Source button, per-row Pause/Configure/Delete.
    expect(screen.queryByRole('link', { name: /add source/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pause source/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /activate source/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /configure/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();

    // Per-type "+" links to /feedback-sources/new are gone for members.
    const hrefs = screen.getAllByRole('link').map(a => a.getAttribute('href'));
    expect(hrefs.filter(h => h?.includes('/feedback-sources/new'))).toHaveLength(0);
  });

  it('shows the empty state copy without the Add Your First Source CTA for members', async () => {
    mockList.mockResolvedValue({ sources: [], total: 0 });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('No feedback sources yet')).toBeInTheDocument();
    });

    expect(screen.getByText('Connect a source to start receiving feedback automatically')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /add your first source/i })).not.toBeInTheDocument();
  });
});

describe('FeedbackSourcesPage — admin role', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockGetTypes.mockResolvedValue(sourceTypes);
  });

  it('shows all write controls for admins', async () => {
    mockList.mockResolvedValue({
      sources: [makeSource({ id: 1, source_type: 'webhook', name: 'Product Webhook' })],
      total: 1,
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Product Webhook')).toBeInTheDocument();
    });

    expect(screen.getByRole('link', { name: /add source/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /pause source/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /configure/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();

    const hrefs = screen.getAllByRole('link').map(a => a.getAttribute('href'));
    expect(hrefs.filter(h => h?.includes('/feedback-sources/new'))).toHaveLength(3);
  });
});
