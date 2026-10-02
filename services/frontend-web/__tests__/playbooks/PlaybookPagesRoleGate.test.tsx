import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

const mockReplace = vi.fn();
// Stable identity, like the real Next router (the [id] page lists router in effect deps).
const router = { push: vi.fn(), replace: mockReplace };
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: '10' }),
  usePathname: () => '/settings/playbooks',
}));

const authMock = vi.hoisted(() => ({
  role: 'member' as string,
  isLoading: false,
}));
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'a@b.c', role: authMock.role, plan: 'free', organization_id: 1 },
    isLoading: authMock.isLoading,
  }),
}));

const mockGetPlaybook = vi.fn();
vi.mock('@/lib/api/playbooks', () => ({
  getPlaybook: (...a: unknown[]) => mockGetPlaybook(...a),
  createPlaybook: vi.fn(),
  updatePlaybook: vi.fn(),
  deletePlaybook: vi.fn(),
  formatProbabilityRange: () => '50%',
}));
vi.mock('@/components/playbooks/PlaybookEditor', () => ({
  PlaybookEditor: () => <div data-testid="editor" />,
}));
vi.mock('@/components/playbooks/PlaybookExecutionsList', () => ({
  PlaybookExecutionsList: () => <div data-testid="executions" />,
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import NewPlaybookPage from '@/app/(dashboard)/settings/playbooks/new/page';
import PlaybookDetailPage from '@/app/(dashboard)/settings/playbooks/[id]/page';

const detail = {
  id: 10, name: 'PB', description: '', probability_min: 0.5, probability_max: 0.8,
  action_sequence: [], is_template: false, is_active: true, executions: [],
};

describe.each([
  ['new', NewPlaybookPage],
  ['[id]', PlaybookDetailPage],
])('playbooks/%s role gate', (_name, Page) => {
  beforeEach(() => {
    vi.clearAllMocks();
    authMock.isLoading = false;
    mockGetPlaybook.mockResolvedValue(detail);
  });

  it('redirects a member to the list and never loads the playbook', async () => {
    authMock.role = 'member';
    render(<Page />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/settings/playbooks'));
    expect(screen.queryByTestId('editor')).not.toBeInTheDocument();
    expect(mockGetPlaybook).not.toHaveBeenCalled();
  });

  it('does not redirect while the user is still loading', async () => {
    authMock.role = 'member';
    authMock.isLoading = true;
    render(<Page />);
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it.each(['admin', 'owner'])('lets %s through regardless of plan', async (role) => {
    authMock.role = role;
    render(<Page />);
    await waitFor(() => expect(screen.getByTestId('editor')).toBeInTheDocument());
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
