import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import React, { Suspense } from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
const mockRouter = { push: mockPush, replace: vi.fn() };
vi.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@/lib/api/feedback-sources', () => ({
  feedbackSourcesAPI: {
    get: vi.fn(),
    getEvents: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
  TRIGGER_OPTIONS: {
    webhook: [
      { key: 'all_messages', label: 'All Requests', description: 'Process every incoming request' },
      { key: 'keywords', label: 'Content Match (optional)', description: 'Requests containing keywords', hasValues: true },
    ],
  },
}));

import { feedbackSourcesAPI } from '@/lib/api/feedback-sources';
import FeedbackSourceDetailPage from '@/app/(dashboard)/feedback-sources/[id]/page';

const mockGet = feedbackSourcesAPI.get as ReturnType<typeof vi.fn>;
const mockGetEvents = feedbackSourcesAPI.getEvents as ReturnType<typeof vi.fn>;

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

const webhookSource = {
  id: 1,
  organization_id: 1,
  integration_id: null,
  source_type: 'webhook',
  name: 'Product Webhook',
  provider_config: {},
  triggers: { all_messages: true, keywords: [] },
  field_mapping: { text_source: 'message', include_author: true, include_source_name: true, include_context: false, max_context_messages: 5, custom_template: null },
  auto_import: true,
  is_active: true,
  last_event_at: null,
  events_processed: 3,
  error_count: 0,
  last_error: null,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
  webhook_url: 'https://hooks.example.com/rereflect/abc',
};

async function renderDetailPage() {
  let utils: ReturnType<typeof render>;
  await act(async () => {
    utils = render(
      <Suspense fallback={<div>Loading page…</div>}>
        <FeedbackSourceDetailPage params={Promise.resolve({ id: '1' })} />
      </Suspense>
    );
  });
  return utils!;
}

describe('FeedbackSourcesDetailPage — member role', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: memberUser });
    mockGet.mockResolvedValue(webhookSource);
    mockGetEvents.mockResolvedValue([]);
  });

  it('hides Delete/Save and disables write controls, keeping reads visible', async () => {
    await renderDetailPage();

    await waitFor(() => {
      expect(screen.getByText('Product Webhook')).toBeInTheDocument();
    });

    // Reads visible: name, webhook URL, Recent Events.
    expect(screen.getByText('https://hooks.example.com/rereflect/abc')).toBeInTheDocument();
    expect(screen.getByText('Recent Events')).toBeInTheDocument();

    // Writes hidden.
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /save changes/i })).not.toBeInTheDocument();

    // Writes disabled: name input, Active/Auto-import/field-mapping switches,
    // Text Source select, trigger value input.
    expect(screen.getByLabelText('Source Name')).toBeDisabled();
    screen.getAllByRole('switch').forEach(sw => expect(sw).toBeDisabled());
    expect(screen.getByRole('combobox')).toBeDisabled();
    expect(screen.getByPlaceholderText(/e.g., memo, feedback/)).toBeDisabled();
    expect(screen.getByPlaceholderText(/e.g., bug, feedback/)).toBeDisabled();
    expect(screen.getByRole('button', { name: /^Add$/ })).toBeDisabled();
  });
});

describe('FeedbackSourcesDetailPage — admin role', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockGet.mockResolvedValue(webhookSource);
    mockGetEvents.mockResolvedValue([]);
  });

  it('shows write controls enabled for admins', async () => {
    await renderDetailPage();

    await waitFor(() => {
      expect(screen.getByText('Product Webhook')).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save changes/i })).toBeInTheDocument();
    expect(screen.getByLabelText('Source Name')).toBeEnabled();
    expect(screen.getByRole('button', { name: /^Add$/ })).toBeEnabled();
  });
});
