import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock admin query templates API
vi.mock('@/lib/api/admin-query-templates', () => ({
  adminQueryTemplatesAPI: {
    list: vi.fn(),
    getStats: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
}));

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { adminQueryTemplatesAPI } from '@/lib/api/admin-query-templates';
import QueryTemplatesAdminPage from '@/app/(dashboard)/system/query-templates/page';

// ─── Fixtures ────────────────────────────────────────────────────────────────

const adminUser = {
  id: 1,
  email: 'admin@test.com',
  role: 'owner',
  plan: 'enterprise',
  organization_id: 1,
  is_system_admin: true,
};

const regularUser = { ...adminUser, role: 'member', is_system_admin: false };

const mockTemplate1 = {
  id: 1,
  organization_id: null,
  sql_query: 'SELECT sentiment, COUNT(*) FROM feedbacks WHERE organization_id = :org_id GROUP BY sentiment',
  description: 'Count feedbacks by sentiment',
  parameter_schema: {},
  created_by: 'system' as const,
  usage_count: 42,
  last_used_at: '2026-02-20T10:00:00Z',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-02-20T10:00:00Z',
};

const mockTemplate2 = {
  id: 2,
  organization_id: 10,
  sql_query: 'SELECT * FROM feedbacks WHERE organization_id = :org_id AND is_urgent = true LIMIT 50',
  description: 'Get urgent feedbacks',
  parameter_schema: {},
  created_by: 'llm' as const,
  usage_count: 7,
  last_used_at: '2026-02-22T14:00:00Z',
  is_active: true,
  created_at: '2026-02-10T00:00:00Z',
  updated_at: '2026-02-22T14:00:00Z',
};

const mockTemplate3 = {
  ...mockTemplate1,
  id: 3,
  description: 'Disabled template',
  is_active: false,
  created_by: 'admin' as const,
  usage_count: 0,
};

const mockListResponse = {
  items: [mockTemplate1, mockTemplate2, mockTemplate3],
  total: 3,
  page: 1,
  page_size: 20,
};

const mockStats = {
  total_templates: 3,
  active_templates: 2,
  template_hit_rate_percent: 67.4,
  queries_today: 14,
  avg_latency_ms: 1240,
};

const mockedList = adminQueryTemplatesAPI.list as ReturnType<typeof vi.fn>;
const mockedGetStats = adminQueryTemplatesAPI.getStats as ReturnType<typeof vi.fn>;
const mockedUpdate = adminQueryTemplatesAPI.update as ReturnType<typeof vi.fn>;
const mockedDelete = adminQueryTemplatesAPI.delete as ReturnType<typeof vi.fn>;

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('QueryTemplatesAdminPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedList.mockResolvedValue(mockListResponse);
    mockedGetStats.mockResolvedValue(mockStats);
    mockedUpdate.mockResolvedValue({ ...mockTemplate1, is_active: false });
    mockedDelete.mockResolvedValue(undefined);
  });

  // ── Access control ─────────────────────────────────────────────────────────

  describe('Access control', () => {
    it('redirects non-admin users to dashboard', async () => {
      mockUseAuth.mockReturnValue({ user: regularUser, isLoading: false, isAuthenticated: true });
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/dashboard');
      });
    });

    it('renders page for admin/owner users', async () => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByText(/query templates/i)).toBeInTheDocument();
      });
    });
  });

  // ── Stats header ───────────────────────────────────────────────────────────

  describe('Stats header', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
    });

    it('renders total templates stat', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('stat-total-templates')).toHaveTextContent('3');
      });
    });

    it('renders template hit rate stat', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('stat-hit-rate')).toHaveTextContent('67.4%');
      });
    });

    it('renders queries today stat', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('stat-queries-today')).toHaveTextContent('14');
      });
    });

    it('renders avg latency stat', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('stat-avg-latency')).toHaveTextContent('1240');
      });
    });
  });

  // ── Table rendering ────────────────────────────────────────────────────────

  describe('Table rendering', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
    });

    it('renders all template descriptions', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByText('Count feedbacks by sentiment')).toBeInTheDocument();
        expect(screen.getByText('Get urgent feedbacks')).toBeInTheDocument();
        expect(screen.getByText('Disabled template')).toBeInTheDocument();
      });
    });

    it('renders created_by values', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        // Use getAllByText since 'system'/'llm'/'admin' also appear as <option> values
        expect(screen.getAllByText('system').length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText('llm').length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText('admin').length).toBeGreaterThanOrEqual(1);
      });
    });

    it('renders usage count for each template', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByText('42')).toBeInTheDocument();
        expect(screen.getByText('7')).toBeInTheDocument();
      });
    });

    it('renders active/disabled status badges', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getAllByText('Active').length).toBeGreaterThanOrEqual(1);
        // Use getAllByText since 'Disabled' also appears as an <option> value
        expect(screen.getAllByText('Disabled').length).toBeGreaterThanOrEqual(1);
      });
    });

    it('renders a truncated SQL query preview', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        // Should show truncated SQL — check for partial match
        expect(screen.getByTestId('sql-preview-1')).toBeInTheDocument();
      });
    });
  });

  // ── Filtering ──────────────────────────────────────────────────────────────

  describe('Filtering', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
    });

    it('renders a filter dropdown for created_by type', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('filter-created-by')).toBeInTheDocument();
      });
    });

    it('renders a filter for active/disabled status', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('filter-status')).toBeInTheDocument();
      });
    });

    it('filters to show only system templates', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('filter-created-by')).toBeInTheDocument();
      });
      // Click "system" filter option
      fireEvent.change(screen.getByTestId('filter-created-by'), { target: { value: 'system' } });
      await waitFor(() => {
        expect(screen.getByText('Count feedbacks by sentiment')).toBeInTheDocument();
        expect(screen.queryByText('Get urgent feedbacks')).not.toBeInTheDocument();
      });
    });

    it('filters to show only disabled templates', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('filter-status')).toBeInTheDocument();
      });
      fireEvent.change(screen.getByTestId('filter-status'), { target: { value: 'disabled' } });
      await waitFor(() => {
        expect(screen.getByText('Disabled template')).toBeInTheDocument();
        expect(screen.queryByText('Count feedbacks by sentiment')).not.toBeInTheDocument();
      });
    });
  });

  // ── Disable / Enable toggle ────────────────────────────────────────────────

  describe('Disable/Enable toggle', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
    });

    it('renders a disable button for active templates', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('toggle-active-1')).toBeInTheDocument();
      });
    });

    it('calls update API with is_active=false when disable is clicked', async () => {
      mockedUpdate.mockResolvedValue({ ...mockTemplate1, is_active: false });
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('toggle-active-1')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId('toggle-active-1'));
      await waitFor(() => {
        expect(mockedUpdate).toHaveBeenCalledWith(1, { is_active: false });
      });
    });

    it('calls update API with is_active=true when enable is clicked on disabled template', async () => {
      mockedUpdate.mockResolvedValue({ ...mockTemplate3, is_active: true });
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('toggle-active-3')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId('toggle-active-3'));
      await waitFor(() => {
        expect(mockedUpdate).toHaveBeenCalledWith(3, { is_active: true });
      });
    });
  });

  // ── Delete with confirmation ───────────────────────────────────────────────

  describe('Delete with confirmation', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
    });

    it('renders a delete button for each template', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('delete-btn-1')).toBeInTheDocument();
      });
    });

    it('shows confirmation dialog before deleting', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('delete-btn-1')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId('delete-btn-1'));
      expect(screen.getByTestId('delete-confirm-dialog')).toBeInTheDocument();
    });

    it('calls delete API after confirming', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('delete-btn-1')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId('delete-btn-1'));
      fireEvent.click(screen.getByTestId('delete-confirm-yes'));
      await waitFor(() => {
        expect(mockedDelete).toHaveBeenCalledWith(1);
      });
    });

    it('does not call delete API when cancelling', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('delete-btn-1')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId('delete-btn-1'));
      fireEvent.click(screen.getByTestId('delete-confirm-no'));
      expect(mockedDelete).not.toHaveBeenCalled();
    });

    it('removes deleted template from table', async () => {
      const user = userEvent.setup();
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByText('Count feedbacks by sentiment')).toBeInTheDocument();
      });
      await user.click(screen.getByTestId('delete-btn-1'));
      await user.click(screen.getByTestId('delete-confirm-yes'));
      await waitFor(() => {
        expect(screen.queryByText('Count feedbacks by sentiment')).not.toBeInTheDocument();
      });
    });
  });

  // ── SQL expand view ────────────────────────────────────────────────────────

  describe('SQL expand view', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
    });

    it('renders a view/expand button per template', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('expand-btn-1')).toBeInTheDocument();
      });
    });

    it('shows full SQL when expand button is clicked', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('expand-btn-1')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId('expand-btn-1'));
      expect(screen.getByTestId('sql-full-1')).toBeInTheDocument();
      expect(screen.getByTestId('sql-full-1')).toHaveTextContent('SELECT sentiment');
    });

    it('hides full SQL when collapse button is clicked', async () => {
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('expand-btn-1')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId('expand-btn-1'));
      fireEvent.click(screen.getByTestId('expand-btn-1'));
      expect(screen.queryByTestId('sql-full-1')).not.toBeInTheDocument();
    });
  });

  // ── Empty state ────────────────────────────────────────────────────────────

  describe('Empty state', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
    });

    it('shows empty state when no templates exist', async () => {
      mockedList.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
      render(<QueryTemplatesAdminPage />);
      await waitFor(() => {
        expect(screen.getByTestId('templates-empty-state')).toBeInTheDocument();
      });
    });
  });
});
