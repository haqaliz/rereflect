import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ── next/navigation ──────────────────────────────────────────────────────────
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => ({ id: '42' }),
}));

// ── AuthContext ───────────────────────────────────────────────────────────────
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@test.com', role: 'owner', plan: 'business', organization_id: 1 },
    isLoading: false,
    isAuthenticated: true,
  }),
}));

// ── feedback API ──────────────────────────────────────────────────────────────
const mockFeedback = {
  id: 42,
  organization_id: 1,
  text: 'The payment sync keeps failing for our account.',
  extracted_issue: 'Payment sync failure',
  source: 'email',
};
vi.mock('@/lib/api/feedback', () => ({
  feedbackAPI: { get: vi.fn(() => Promise.resolve(mockFeedback)) },
}));

// ── Linear API (not connected — keeps that card disabled/uninteresting) ──────
vi.mock('@/lib/api/linear', () => ({
  linearAPI: {
    getStatus: vi.fn(() => Promise.resolve({ connected: false })),
    getTeams: vi.fn(() => Promise.resolve([])),
    getLabels: vi.fn(() => Promise.resolve([])),
    getLinkedIssues: vi.fn(() => Promise.resolve([])),
    getProjects: vi.fn(() => Promise.resolve([])),
    createIssue: vi.fn(),
  },
  LINEAR_PRIORITY_LABELS: { '0': 'No priority', '1': 'Urgent', '2': 'High', '3': 'Normal', '4': 'Low' },
}));

// ── Jira API ──────────────────────────────────────────────────────────────────
const { jiraCreateIssue } = vi.hoisted(() => ({ jiraCreateIssue: vi.fn() }));
vi.mock('@/lib/api/jira', () => ({
  jiraAPI: {
    getStatus: vi.fn(() =>
      Promise.resolve({ connected: true, is_active: true, site_url: 'https://acme.atlassian.net' })
    ),
    getProjects: vi.fn(() => Promise.resolve([{ id: '10001', key: 'ENG', name: 'Engineering' }])),
    getIssueTypes: vi.fn(() => Promise.resolve([{ id: '10000', name: 'Bug' }])),
    getLinkedIssues: vi.fn(() => Promise.resolve([])),
    createIssue: jiraCreateIssue,
  },
}));

// ── Asana API ─────────────────────────────────────────────────────────────────
const { asanaCreateTask } = vi.hoisted(() => ({ asanaCreateTask: vi.fn() }));
vi.mock('@/lib/api/asana', () => ({
  asanaAPI: {
    getStatus: vi.fn(() =>
      Promise.resolve({ connected: true, is_active: true, display_name: 'Acme Co' })
    ),
    getWorkspaces: vi.fn(() => Promise.resolve([{ gid: 'w1', name: 'Acme Workspace' }])),
    getProjects: vi.fn(() => Promise.resolve([{ gid: 'p1', name: 'Backlog' }])),
    getLinkedTasks: vi.fn(() => Promise.resolve([])),
    createTask: asanaCreateTask,
  },
}));

// ── jira/asana wizard helpers — real implementations are pure, no mock needed ─

// ── AI settings API (T2 gate) ────────────────────────────────────────────────
const { aiSettingsGet, aiSettingsListKeys } = vi.hoisted(() => ({
  aiSettingsGet: vi.fn(),
  aiSettingsListKeys: vi.fn(),
}));
vi.mock('@/lib/api/ai-settings', () => ({
  aiSettingsAPI: {
    get: (...args: unknown[]) => aiSettingsGet(...args),
    listKeys: (...args: unknown[]) => aiSettingsListKeys(...args),
  },
}));

// ── Issue draft client ────────────────────────────────────────────────────────
const { draftIssueContent } = vi.hoisted(() => ({ draftIssueContent: vi.fn() }));
vi.mock('@/lib/api/issueDraft', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/issueDraft')>('@/lib/api/issueDraft');
  return {
    ...actual,
    draftIssueContent: (...args: unknown[]) => draftIssueContent(...args),
  };
});

// ── toast ─────────────────────────────────────────────────────────────────────
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from 'sonner';
import CreateIssuePage from '../create-issue/page';

const CONFIGURED_CLOUD_SETTINGS = {
  ai_analysis_enabled: true,
  has_custom_key: true,
  default_provider: 'openai',
  base_url: null,
  model_embeddings: null,
  models: { categorization: 'gpt-4o-mini', analysis: 'gpt-4o-mini', insights: 'gpt-4o-mini' },
};

const CONFIGURED_LOCAL_SETTINGS = {
  ai_analysis_enabled: true,
  has_custom_key: false,
  default_provider: 'ollama',
  base_url: 'http://localhost:11434',
  model_embeddings: null,
  models: { categorization: 'llama3', analysis: 'llama3', insights: 'llama3' },
};

const UNCONFIGURED_SETTINGS = {
  ai_analysis_enabled: false,
  has_custom_key: false,
  default_provider: 'openai',
  base_url: null,
  model_embeddings: null,
  models: { categorization: 'gpt-4o-mini', analysis: 'gpt-4o-mini', insights: 'gpt-4o-mini' },
};

async function goToJiraConfigure() {
  render(<CreateIssuePage />);
  const jiraCard = await screen.findByText('Jira');
  await userEvent.click(jiraCard.closest('button')!);
  await screen.findByText('Configure Jira Issue');
}

async function goToAsanaConfigure() {
  render(<CreateIssuePage />);
  const asanaCard = await screen.findByText('Asana');
  await userEvent.click(asanaCard.closest('button')!);
  await screen.findByText('Configure Asana Task');
}

describe('create-issue wizard — Draft with AI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    aiSettingsGet.mockResolvedValue(CONFIGURED_CLOUD_SETTINGS);
    aiSettingsListKeys.mockResolvedValue([{ provider: 'openai', key_hint: '...abcd', is_valid: true, created_at: '2026-01-01' }]);
    draftIssueContent.mockResolvedValue({ title: 'AI title', body: 'AI body' });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('hides the Draft with AI button in the Jira branch when no LLM is configured', async () => {
    aiSettingsGet.mockResolvedValue(UNCONFIGURED_SETTINGS);
    aiSettingsListKeys.mockResolvedValue([]);
    await goToJiraConfigure();
    expect(screen.queryByRole('button', { name: /draft with ai/i })).not.toBeInTheDocument();
  });

  it('hides the Draft with AI button in the Asana branch when no LLM is configured', async () => {
    aiSettingsGet.mockResolvedValue(UNCONFIGURED_SETTINGS);
    aiSettingsListKeys.mockResolvedValue([]);
    await goToAsanaConfigure();
    expect(screen.queryByRole('button', { name: /draft with ai/i })).not.toBeInTheDocument();
  });

  it('shows the Draft with AI button in the Jira branch when a cloud key is configured', async () => {
    await goToJiraConfigure();
    expect(await screen.findByRole('button', { name: /draft with ai/i })).toBeInTheDocument();
  });

  it('shows the Draft with AI button when a local provider + base_url is configured (T2)', async () => {
    aiSettingsGet.mockResolvedValue(CONFIGURED_LOCAL_SETTINGS);
    aiSettingsListKeys.mockResolvedValue([]);
    await goToJiraConfigure();
    expect(await screen.findByRole('button', { name: /draft with ai/i })).toBeInTheDocument();
  });

  it('hides the button for a local provider with no base_url set (T2)', async () => {
    aiSettingsGet.mockResolvedValue({ ...CONFIGURED_LOCAL_SETTINGS, base_url: null });
    aiSettingsListKeys.mockResolvedValue([]);
    await goToJiraConfigure();
    expect(screen.queryByRole('button', { name: /draft with ai/i })).not.toBeInTheDocument();
  });

  it('shows the button in the Asana branch when configured', async () => {
    await goToAsanaConfigure();
    expect(await screen.findByRole('button', { name: /draft with ai/i })).toBeInTheDocument();
  });

  it('click populates Jira summary/description from the draft and fires no create call', async () => {
    await goToJiraConfigure();
    const draftButton = await screen.findByRole('button', { name: /draft with ai/i });
    await userEvent.click(draftButton);

    await waitFor(() => {
      expect(screen.getByDisplayValue('AI title')).toBeInTheDocument();
    });
    expect(screen.getByDisplayValue('AI body')).toBeInTheDocument();
    expect(draftIssueContent).toHaveBeenCalledWith(42, 'jira');
    expect(jiraCreateIssue).not.toHaveBeenCalled();
  });

  it('click populates Asana name/notes from the draft and fires no create call', async () => {
    await goToAsanaConfigure();
    const draftButton = await screen.findByRole('button', { name: /draft with ai/i });
    await userEvent.click(draftButton);

    await waitFor(() => {
      expect(screen.getByDisplayValue('AI title')).toBeInTheDocument();
    });
    expect(screen.getByDisplayValue('AI body')).toBeInTheDocument();
    expect(draftIssueContent).toHaveBeenCalledWith(42, 'asana');
    expect(asanaCreateTask).not.toHaveBeenCalled();
  });

  it('overwrites directly (no confirm) when fields still equal the auto-seeded defaults', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm');
    await goToJiraConfigure();
    // Fields are seeded from feedback.extracted_issue / feedback.text and untouched.
    const draftButton = await screen.findByRole('button', { name: /draft with ai/i });
    await userEvent.click(draftButton);

    await waitFor(() => expect(screen.getByDisplayValue('AI title')).toBeInTheDocument());
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('asks for confirmation before overwriting edited fields — accept overwrites', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    await goToJiraConfigure();

    const summaryInput = screen.getByDisplayValue('Payment sync failure');
    await userEvent.clear(summaryInput);
    await userEvent.type(summaryInput, 'My own edited summary');

    const draftButton = await screen.findByRole('button', { name: /draft with ai/i });
    await userEvent.click(draftButton);

    expect(confirmSpy).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByDisplayValue('AI title')).toBeInTheDocument());
  });

  it('asks for confirmation before overwriting edited fields — cancel leaves fields untouched', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    await goToJiraConfigure();

    const summaryInput = screen.getByDisplayValue('Payment sync failure');
    await userEvent.clear(summaryInput);
    await userEvent.type(summaryInput, 'My own edited summary');

    const draftButton = await screen.findByRole('button', { name: /draft with ai/i });
    await userEvent.click(draftButton);

    await waitFor(() => expect(draftIssueContent).toHaveBeenCalled());
    // Field must remain as the user's edit, not the AI draft.
    expect(screen.getByDisplayValue('My own edited summary')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('AI title')).not.toBeInTheDocument();
  });

  it('shows an error toast and leaves fields untouched on a 409 (no LLM) failure', async () => {
    const { IssueDraftApiError } = await import('@/lib/api/issueDraft');
    draftIssueContent.mockRejectedValue(new IssueDraftApiError(409, 'No AI model configured.'));
    await goToJiraConfigure();

    const draftButton = await screen.findByRole('button', { name: /draft with ai/i });
    await userEvent.click(draftButton);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('No AI model configured.');
    });
    expect(screen.getByDisplayValue('Payment sync failure')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('AI title')).not.toBeInTheDocument();
    // Button re-enabled after the failure.
    expect(await screen.findByRole('button', { name: /draft with ai/i })).not.toBeDisabled();
  });

  it('disables the button while a draft is in flight', async () => {
    let resolveDraft: (v: unknown) => void;
    draftIssueContent.mockReturnValue(new Promise((res) => { resolveDraft = res; }));
    await goToJiraConfigure();

    const draftButton = await screen.findByRole('button', { name: /draft with ai/i });
    await userEvent.click(draftButton);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /drafting/i })).toBeDisabled();
    });

    resolveDraft!({ title: 'AI title', body: 'AI body' });
    await waitFor(() => expect(screen.getByDisplayValue('AI title')).toBeInTheDocument());
  });
});
