import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const router = { push: vi.fn(), replace: vi.fn() };
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  usePathname: () => '/settings/workflow',
  useSearchParams: () => new URLSearchParams(),
}));

const authMock = vi.hoisted(() => ({ role: 'member' as string, isLoading: false }));
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: authMock.isLoading
      ? null
      : { id: 1, email: 'u@t.c', role: authMock.role, plan: 'free', organization_id: 1, is_system_admin: false },
    isLoading: authMock.isLoading,
    isAuthenticated: true,
  }),
}));

vi.mock('@/lib/api/workflow', () => ({
  workflowAPI: {
    getAutoAssignmentSettings: vi.fn(),
    getAssignmentRules: vi.fn(),
    updateAutoAssignmentSettings: vi.fn(),
    createRule: vi.fn(),
    updateRule: vi.fn(),
    deleteRule: vi.fn(),
  },
}));
vi.mock('@/lib/api/team', () => ({ teamAPI: { getTeam: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { workflowAPI } from '@/lib/api/workflow';
import { teamAPI } from '@/lib/api/team';
import WorkflowPage from '@/app/(dashboard)/settings/workflow/page';

describe('settings/workflow role gate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authMock.isLoading = false;
    (workflowAPI.getAutoAssignmentSettings as ReturnType<typeof vi.fn>).mockResolvedValue({ auto_assignment_enabled: false });
    (workflowAPI.getAssignmentRules as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (teamAPI.getTeam as ReturnType<typeof vi.fn>).mockResolvedValue({ members: [{ id: 1, email: 'a@b.c' }] });
  });

  it('redirects a member to preferences and does not load rules or settings', async () => {
    authMock.role = 'member';
    render(<WorkflowPage />);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/settings/preferences'));
    expect(workflowAPI.getAssignmentRules).not.toHaveBeenCalled();
    expect(workflowAPI.getAutoAssignmentSettings).not.toHaveBeenCalled();
  });

  it('does not redirect while the user is still loading', async () => {
    authMock.role = 'member';
    authMock.isLoading = true;
    render(<WorkflowPage />);
    expect(router.replace).not.toHaveBeenCalled();
  });

  it.each(['admin', 'owner'])('%s stays and loads the rules', async (role) => {
    authMock.role = role;
    render(<WorkflowPage />);
    await waitFor(() => expect(workflowAPI.getAssignmentRules).toHaveBeenCalled());
    expect(router.replace).not.toHaveBeenCalled();
  });
});
