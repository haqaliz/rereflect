import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// ─── Mock next/navigation ─────────────────────────────────────────────────────

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => '/workflow',
  useSearchParams: () => new URLSearchParams(),
}));

// ─── Mock workflow API ────────────────────────────────────────────────────────

vi.mock('@/lib/api/workflow', () => ({
  workflowAPI: {
    getOverview: vi.fn(),
    changeStatus: vi.fn(),
    assign: vi.fn(),
  },
}));

// ─── Mock api-client ──────────────────────────────────────────────────────────

vi.mock('@/lib/api-client', () => ({
  default: {
    get: vi.fn(),
  },
}));

// ─── Mock shared components ────────────────────────────────────────────────────

vi.mock('@/components/shared/data-table', () => ({
  DataTable: () => <div data-testid="data-table">Table</div>,
}));

vi.mock('@/components/workflow/BulkActionsBar', () => ({
  BulkActionsBar: () => <div data-testid="bulk-actions">Bulk Actions</div>,
}));

vi.mock('@/app/(dashboard)/workflow/kanban-view', () => ({
  KanbanView: () => <div data-testid="kanban-view">Kanban</div>,
}));

// ─── Mock workflow-utils ──────────────────────────────────────────────────────

vi.mock('@/lib/workflow-utils', () => ({
  getStatusColor: vi.fn(() => '#000'),
  getStatusLabel: vi.fn((s: string) => s),
  formatRelativeTime: vi.fn(() => '5m ago'),
}));

// ─── Mock useRealtimeEvents ───────────────────────────────────────────────────

const mockUseRealtimeEvents = vi.fn();
vi.mock('@/hooks/useRealtimeEvents', () => ({
  useRealtimeEvents: (...args: unknown[]) => {
    mockUseRealtimeEvents(...args);
    return { connected: true, reconnecting: false };
  },
}));

// ─── Mock localStorage ────────────────────────────────────────────────────────

vi.stubGlobal('localStorage', {
  getItem: vi.fn(() => 'test-token'),
  setItem: vi.fn(),
  removeItem: vi.fn(),
});

// ─── Imports (after mocks) ────────────────────────────────────────────────────

import { workflowAPI } from '@/lib/api/workflow';
import apiClient from '@/lib/api-client';

// ─── Helper ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function Wrapper({ children, qc }: { children: React.ReactNode; qc: QueryClient }) {
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('WorkflowPage — realtime migration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (workflowAPI.getOverview as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      status_counts: {},
      total: 0,
      total_pages: 1,
    });
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { members: [] },
    });
  });

  // 10. test_no_refetch_interval_configured
  it('test_no_refetch_interval_configured — React Query config does NOT have refetchInterval', async () => {
    // Read the source file and verify refetchInterval is not present in the workflow query config
    const fs = await import('fs');
    const path = await import('path');
    const filePath = path.resolve(
      process.cwd(),
      'app/(dashboard)/workflow/page.tsx'
    );
    const source = fs.readFileSync(filePath, 'utf-8');

    expect(source).not.toMatch(/refetchInterval\s*:/);
    expect(source).not.toMatch(/refetchIntervalInBackground\s*:/);
  });

  // 11. test_subscribes_to_workflow_events
  it('test_subscribes_to_workflow_events — useRealtimeEvents called with "workflow:*" pattern', async () => {
    const { default: WorkflowPage } = await import('@/app/(dashboard)/workflow/page');
    const qc = makeQueryClient();
    render(
      <Wrapper qc={qc}>
        <WorkflowPage />
      </Wrapper>
    );

    await waitFor(() => {
      expect(mockUseRealtimeEvents).toHaveBeenCalledWith(
        'workflow:*',
        expect.any(Function)
      );
    });
  });

  // 12. test_invalidates_workflow_cache_on_event
  it('test_invalidates_workflow_cache_on_event — push workflow:status_changed → invalidateQueries(["workflow"]) called', async () => {
    let capturedHandler: ((event: unknown) => void) | null = null;

    mockUseRealtimeEvents.mockImplementation((pattern: string, handler: (event: unknown) => void) => {
      if (pattern === 'workflow:*') {
        capturedHandler = handler;
      }
      return { connected: true, reconnecting: false };
    });

    const { default: WorkflowPage } = await import('@/app/(dashboard)/workflow/page');
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');

    render(
      <Wrapper qc={qc}>
        <WorkflowPage />
      </Wrapper>
    );

    await waitFor(() => {
      expect(capturedHandler).not.toBeNull();
    });

    const { act } = await import('@testing-library/react');
    act(() => {
      capturedHandler?.({ type: 'workflow:status_changed', id: 42 });
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ['workflow'] })
      );
    });
  });
});
