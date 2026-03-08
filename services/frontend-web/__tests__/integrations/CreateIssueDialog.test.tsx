import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock Linear API
vi.mock('@/lib/api/linear', () => ({
  linearAPI: {
    getStatus: vi.fn(),
    createIssue: vi.fn(),
    getTeams: vi.fn(),
    getProjects: vi.fn(),
    getLabels: vi.fn(),
    getLinkedIssues: vi.fn(),
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
import { CreateIssueDialog } from '@/components/integrations/CreateIssueDialog';

const proUser = {
  id: 1,
  email: 'user@test.com',
  role: 'owner',
  plan: 'pro',
  organization_id: 1,
  is_system_admin: false,
};

const freeUser = { ...proUser, plan: 'free' };

const connectedStatus = {
  connected: true,
  org_name: 'Acme Corp',
  org_id: 'linear-org-id',
  connected_by_email: 'admin@test.com',
  connected_at: '2026-01-01T00:00:00Z',
  is_active: true,
};

const disconnectedStatus = {
  connected: false,
  org_name: null,
  org_id: null,
  connected_by_email: null,
  connected_at: null,
  is_active: false,
};

const mockTeams = [
  { id: 'team-1', name: 'Engineering', key: 'ENG' },
  { id: 'team-2', name: 'Design', key: 'DES' },
];

const mockProjects = [
  { id: 'proj-1', name: 'Q1 Roadmap', team_id: 'team-1' },
];

const mockLabels = [
  { id: 'label-1', name: 'Bug', color: '#ff0000' },
  { id: 'label-2', name: 'Feature', color: '#00ff00' },
];

const mockFeedbackContext = {
  feedbackId: 123,
  title: 'Fix CSV export timeout for large datasets',
  description: '## Summary\n\nMultiple customers report CSV export fails for datasets > 10K rows.',
};

const mockCreatedIssue = {
  issue: {
    id: 1,
    linear_issue_id: 'linear-uuid',
    linear_issue_identifier: 'ENG-142',
    linear_issue_url: 'https://linear.app/acme/issue/ENG-142',
    linear_issue_title: 'Fix CSV export timeout',
    linear_status: 'Backlog',
    linear_assignee: null,
    linear_priority: 3,
    created_at: '2026-03-08T00:00:00Z',
  },
  linear_url: 'https://linear.app/acme/issue/ENG-142',
};

describe('CreateIssueDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(linearAPI.getStatus).mockResolvedValue(connectedStatus);
    vi.mocked(linearAPI.getTeams).mockResolvedValue(mockTeams);
    vi.mocked(linearAPI.getProjects).mockResolvedValue(mockProjects);
    vi.mocked(linearAPI.getLabels).mockResolvedValue(mockLabels);
    vi.mocked(linearAPI.getLinkedIssues).mockResolvedValue([]);
    vi.mocked(linearAPI.createIssue).mockResolvedValue(mockCreatedIssue);
  });

  describe('Dialog open/close', () => {
    it('renders trigger button', async () => {
      mockUseAuth.mockReturnValue({ user: proUser });
      render(
        <CreateIssueDialog
          feedbackId={123}
          aiTitle={mockFeedbackContext.title}
          aiDescription={mockFeedbackContext.description}
        />
      );
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /create issue/i })).toBeInTheDocument();
      });
    });

    it('opens dialog when trigger button is clicked', async () => {
      mockUseAuth.mockReturnValue({ user: proUser });
      render(
        <CreateIssueDialog
          feedbackId={123}
          aiTitle={mockFeedbackContext.title}
          aiDescription={mockFeedbackContext.description}
        />
      );
      await waitFor(() => {
        fireEvent.click(screen.getByRole('button', { name: /create issue/i }));
      });
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });

    it('closes dialog on cancel', async () => {
      mockUseAuth.mockReturnValue({ user: proUser });
      render(
        <CreateIssueDialog
          feedbackId={123}
          aiTitle={mockFeedbackContext.title}
          aiDescription={mockFeedbackContext.description}
        />
      );
      await waitFor(() => {
        fireEvent.click(screen.getByRole('button', { name: /create issue/i }));
      });
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      });
    });
  });

  describe('Integration selection step', () => {
    it('shows integration selector as step 1', async () => {
      mockUseAuth.mockReturnValue({ user: proUser });
      render(
        <CreateIssueDialog
          feedbackId={123}
          aiTitle={mockFeedbackContext.title}
          aiDescription={mockFeedbackContext.description}
        />
      );
      await waitFor(() => {
        fireEvent.click(screen.getByRole('button', { name: /create issue/i }));
      });
      await waitFor(() => {
        expect(screen.getByText(/linear/i)).toBeInTheDocument();
      });
    });

    it('shows JIRA and Asana as "Coming soon" (greyed out)', async () => {
      mockUseAuth.mockReturnValue({ user: proUser });
      render(
        <CreateIssueDialog
          feedbackId={123}
          aiTitle={mockFeedbackContext.title}
          aiDescription={mockFeedbackContext.description}
        />
      );
      await waitFor(() => {
        fireEvent.click(screen.getByRole('button', { name: /create issue/i }));
      });
      await waitFor(() => {
        const comingSoonLabels = screen.getAllByText(/coming soon/i);
        expect(comingSoonLabels.length).toBeGreaterThanOrEqual(2);
      });
    });

    it('advances to form step when Linear is selected', async () => {
      mockUseAuth.mockReturnValue({ user: proUser });
      render(
        <CreateIssueDialog
          feedbackId={123}
          aiTitle={mockFeedbackContext.title}
          aiDescription={mockFeedbackContext.description}
        />
      );
      await waitFor(() => {
        fireEvent.click(screen.getByRole('button', { name: /create issue/i }));
      });
      await waitFor(() => {
        // Click on Linear option (the heading inside the button)
        fireEvent.click(screen.getByRole('button', { name: /linear.*acme corp/i, hidden: true }));
      });
      await waitFor(() => {
        // Should show form with title field
        const titleInput = screen.getByDisplayValue(mockFeedbackContext.title);
        expect(titleInput).toBeInTheDocument();
      });
    });
  });

  describe('Issue form fields', () => {
    async function openLinearForm() {
      render(
        <CreateIssueDialog
          feedbackId={123}
          aiTitle={mockFeedbackContext.title}
          aiDescription={mockFeedbackContext.description}
        />
      );
      await waitFor(() => {
        fireEvent.click(screen.getByRole('button', { name: /create issue/i }));
      });
      await waitFor(() => {
        fireEvent.click(screen.getByRole('button', { name: /linear.*acme corp/i, hidden: true }));
      });
      await waitFor(() => {
        expect(screen.getByDisplayValue(mockFeedbackContext.title)).toBeInTheDocument();
      });
    }

    it('pre-fills title with AI-generated content', async () => {
      mockUseAuth.mockReturnValue({ user: proUser });
      await openLinearForm();
      expect(screen.getByDisplayValue(mockFeedbackContext.title)).toBeInTheDocument();
    });

    it('allows editing the AI-generated title', async () => {
      mockUseAuth.mockReturnValue({ user: proUser });
      await openLinearForm();
      const titleInput = screen.getByDisplayValue(mockFeedbackContext.title);
      fireEvent.change(titleInput, { target: { value: 'Custom title' } });
      expect(screen.getByDisplayValue('Custom title')).toBeInTheDocument();
    });

    it('shows team selector dropdown', async () => {
      mockUseAuth.mockReturnValue({ user: proUser });
      await openLinearForm();
      // Should have a team label in the form
      expect(screen.getByText('Team')).toBeInTheDocument();
    });

    it('shows priority selector', async () => {
      mockUseAuth.mockReturnValue({ user: proUser });
      await openLinearForm();
      expect(screen.getByText(/priority/i)).toBeInTheDocument();
    });
  });

  describe('Submit flow', () => {
    async function openLinearFormAndSubmit() {
      render(
        <CreateIssueDialog
          feedbackId={123}
          aiTitle={mockFeedbackContext.title}
          aiDescription={mockFeedbackContext.description}
        />
      );
      await waitFor(() => {
        fireEvent.click(screen.getByRole('button', { name: /create issue/i }));
      });
      await waitFor(() => {
        fireEvent.click(screen.getByRole('button', { name: /linear.*acme corp/i, hidden: true }));
      });
      await waitFor(() => {
        expect(screen.getByDisplayValue(mockFeedbackContext.title)).toBeInTheDocument();
      });
    }

    it('calls createIssue API on submit', async () => {
      mockUseAuth.mockReturnValue({ user: proUser });
      await openLinearFormAndSubmit();
      const submitBtn = screen.getByRole('button', { name: /^create$/i });
      fireEvent.click(submitBtn);
      await waitFor(() => {
        expect(linearAPI.createIssue).toHaveBeenCalled();
      });
    });

    it('shows success state with Linear link after creation', async () => {
      mockUseAuth.mockReturnValue({ user: proUser });
      await openLinearFormAndSubmit();
      fireEvent.click(screen.getByRole('button', { name: /^create$/i }));
      await waitFor(() => {
        expect(screen.getByText(/ENG-142/i)).toBeInTheDocument();
      });
    });
  });

  describe('Duplicate warning', () => {
    it('shows duplicate warning banner when feedback already has linked issue', async () => {
      mockUseAuth.mockReturnValue({ user: proUser });
      vi.mocked(linearAPI.getLinkedIssues).mockResolvedValue([
        {
          id: 1,
          linear_issue_id: 'existing-uuid',
          linear_issue_identifier: 'ENG-100',
          linear_issue_url: 'https://linear.app/acme/issue/ENG-100',
          linear_issue_title: 'Existing issue',
          linear_status: 'In Progress',
          linear_assignee: null,
          linear_priority: null,
          created_at: '2026-01-01T00:00:00Z',
        },
      ]);
      render(
        <CreateIssueDialog
          feedbackId={123}
          aiTitle={mockFeedbackContext.title}
          aiDescription={mockFeedbackContext.description}
        />
      );
      await waitFor(() => {
        fireEvent.click(screen.getByRole('button', { name: /create issue/i }));
      });
      await waitFor(() => {
        fireEvent.click(screen.getByRole('button', { name: /linear.*acme corp/i, hidden: true }));
      });
      await waitFor(() => {
        // Should show warning about existing issue
        expect(screen.getByText(/already linked/i)).toBeInTheDocument();
        expect(screen.getByText(/ENG-100/i)).toBeInTheDocument();
      });
    });
  });

  describe('Plan gating', () => {
    it('shows disabled button with upgrade tooltip for free plan users', async () => {
      mockUseAuth.mockReturnValue({ user: freeUser });
      render(
        <CreateIssueDialog
          feedbackId={123}
          aiTitle={mockFeedbackContext.title}
          aiDescription={mockFeedbackContext.description}
        />
      );
      await waitFor(() => {
        const btn = screen.getByRole('button', { name: /create issue/i });
        expect(btn).toBeDisabled();
      });
    });
  });

  describe('No integration connected', () => {
    it('hides button when no integration is connected', async () => {
      mockUseAuth.mockReturnValue({ user: proUser });
      vi.mocked(linearAPI.getStatus).mockResolvedValue(disconnectedStatus);
      render(
        <CreateIssueDialog
          feedbackId={123}
          aiTitle={mockFeedbackContext.title}
          aiDescription={mockFeedbackContext.description}
        />
      );
      await waitFor(() => {
        expect(screen.queryByRole('button', { name: /create issue/i })).not.toBeInTheDocument();
      });
    });
  });
});
