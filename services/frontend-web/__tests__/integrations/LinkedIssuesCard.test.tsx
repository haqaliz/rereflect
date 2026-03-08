import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

// Mock Linear API
vi.mock('@/lib/api/linear', () => ({
  linearAPI: {
    getLinkedIssues: vi.fn(),
    getStatus: vi.fn(),
  },
  LINEAR_PRIORITY_LABELS: {
    0: 'No priority',
    1: 'Urgent',
    2: 'High',
    3: 'Medium',
    4: 'Low',
  },
}));

import { linearAPI } from '@/lib/api/linear';
import { LinkedIssuesCard } from '@/components/feedback/LinkedIssuesCard';

const mockSingleIssue = [
  {
    id: 1,
    linear_issue_id: 'linear-uuid-1',
    linear_issue_identifier: 'ENG-142',
    linear_issue_url: 'https://linear.app/acme/issue/ENG-142',
    linear_issue_title: 'Fix CSV export timeout for large datasets',
    linear_status: 'In Progress',
    linear_assignee: 'Jane Smith',
    linear_priority: 2,
    created_at: '2026-03-01T00:00:00Z',
  },
];

const mockMultipleIssues = [
  ...mockSingleIssue,
  {
    id: 2,
    linear_issue_id: 'linear-uuid-2',
    linear_issue_identifier: 'ENG-200',
    linear_issue_url: 'https://linear.app/acme/issue/ENG-200',
    linear_issue_title: 'Related performance issue',
    linear_status: 'Backlog',
    linear_assignee: null,
    linear_priority: 3,
    created_at: '2026-03-02T00:00:00Z',
  },
];

describe('LinkedIssuesCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(linearAPI.getLinkedIssues).mockResolvedValue([]);
    vi.mocked(linearAPI.getStatus).mockResolvedValue({
      connected: true,
      org_name: 'Acme Corp',
      org_id: 'linear-org-id',
      connected_by_email: 'admin@test.com',
      connected_at: '2026-01-01T00:00:00Z',
      is_active: true,
    });
  });

  describe('Empty state', () => {
    it('renders nothing (null) when there are no linked issues', async () => {
      vi.mocked(linearAPI.getLinkedIssues).mockResolvedValue([]);
      const { container } = render(<LinkedIssuesCard feedbackId={123} />);
      await waitFor(() => {
        // Card should not be visible or rendered empty
        expect(container.firstChild).toBeNull();
      });
    });
  });

  describe('Single issue display', () => {
    beforeEach(() => {
      vi.mocked(linearAPI.getLinkedIssues).mockResolvedValue(mockSingleIssue);
    });

    it('renders the issue identifier as a clickable link', async () => {
      render(<LinkedIssuesCard feedbackId={123} />);
      await waitFor(() => {
        const link = screen.getByRole('link', { name: /ENG-142/i });
        expect(link).toBeInTheDocument();
        expect(link).toHaveAttribute('href', 'https://linear.app/acme/issue/ENG-142');
      });
    });

    it('renders the issue title', async () => {
      render(<LinkedIssuesCard feedbackId={123} />);
      await waitFor(() => {
        expect(screen.getByText(/Fix CSV export timeout/i)).toBeInTheDocument();
      });
    });

    it('renders the status badge', async () => {
      render(<LinkedIssuesCard feedbackId={123} />);
      await waitFor(() => {
        expect(screen.getByText(/In Progress/i)).toBeInTheDocument();
      });
    });

    it('renders the assignee name', async () => {
      render(<LinkedIssuesCard feedbackId={123} />);
      await waitFor(() => {
        expect(screen.getByText(/Jane Smith/i)).toBeInTheDocument();
      });
    });

    it('renders the priority label', async () => {
      render(<LinkedIssuesCard feedbackId={123} />);
      await waitFor(() => {
        // priority 2 = High
        expect(screen.getByText(/high/i)).toBeInTheDocument();
      });
    });

    it('opens link in new tab', async () => {
      render(<LinkedIssuesCard feedbackId={123} />);
      await waitFor(() => {
        const link = screen.getByRole('link', { name: /ENG-142/i });
        expect(link).toHaveAttribute('target', '_blank');
        expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
      });
    });
  });

  describe('Multiple linked issues', () => {
    beforeEach(() => {
      vi.mocked(linearAPI.getLinkedIssues).mockResolvedValue(mockMultipleIssues);
    });

    it('renders all linked issues', async () => {
      render(<LinkedIssuesCard feedbackId={123} />);
      await waitFor(() => {
        expect(screen.getByText(/ENG-142/i)).toBeInTheDocument();
        expect(screen.getByText(/ENG-200/i)).toBeInTheDocument();
      });
    });

    it('renders multiple issue titles', async () => {
      render(<LinkedIssuesCard feedbackId={123} />);
      await waitFor(() => {
        expect(screen.getByText(/Fix CSV export timeout/i)).toBeInTheDocument();
        expect(screen.getByText(/Related performance issue/i)).toBeInTheDocument();
      });
    });
  });

  describe('Issue with no assignee', () => {
    it('renders gracefully when assignee is null', async () => {
      vi.mocked(linearAPI.getLinkedIssues).mockResolvedValue([
        {
          ...mockSingleIssue[0],
          linear_assignee: null,
        },
      ]);
      render(<LinkedIssuesCard feedbackId={123} />);
      await waitFor(() => {
        expect(screen.getByText(/ENG-142/i)).toBeInTheDocument();
        // No assignee text shown
        expect(screen.queryByText(/Jane Smith/i)).not.toBeInTheDocument();
      });
    });
  });

  describe('Issue with no priority', () => {
    it('renders gracefully when priority is null', async () => {
      vi.mocked(linearAPI.getLinkedIssues).mockResolvedValue([
        {
          ...mockSingleIssue[0],
          linear_priority: null,
        },
      ]);
      render(<LinkedIssuesCard feedbackId={123} />);
      await waitFor(() => {
        expect(screen.getByText(/ENG-142/i)).toBeInTheDocument();
      });
    });
  });

  describe('Card header', () => {
    it('shows a "Linked Issues" heading', async () => {
      vi.mocked(linearAPI.getLinkedIssues).mockResolvedValue(mockSingleIssue);
      render(<LinkedIssuesCard feedbackId={123} />);
      await waitFor(() => {
        expect(screen.getByText(/linked issues/i)).toBeInTheDocument();
      });
    });
  });
});
