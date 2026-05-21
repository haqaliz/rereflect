import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

const mockCreatePlaybook = vi.fn();
const mockUpdatePlaybook = vi.fn();

vi.mock('@/lib/api/playbooks', () => ({
  listPlaybooks: vi.fn(),
  getPlaybook: vi.fn(),
  createPlaybook: (...args: unknown[]) => mockCreatePlaybook(...args),
  updatePlaybook: (...args: unknown[]) => mockUpdatePlaybook(...args),
  deletePlaybook: vi.fn(),
  runPlaybook: vi.fn(),
  runPlaybookBatch: vi.fn(),
  listExecutions: vi.fn(),
  formatProbabilityRange: (min: number, max: number) =>
    `${Math.round(min * 100)}%–${Math.round(max * 100)}%`,
  PLAN_PLAYBOOK_LIMITS: { free: 0, pro: 0, business: 20, enterprise: null },
  ACTION_TYPE_LABELS: {
    assign: 'Assign',
    change_status: 'Change Status',
    send_notification: 'Send Notification',
    draft_response: 'Draft AI Response',
  },
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(),
}));

import { PlaybookEditor } from '@/components/playbooks/PlaybookEditor';
import type { Playbook } from '@/lib/api/playbooks';

const basePlaybook: Playbook = {
  id: 5,
  organization_id: 1,
  name: 'Churn Prevention',
  description: 'Prevent mid-risk churn',
  probability_min: 0.5,
  probability_max: 0.85,
  action_sequence: [{ type: 'send_notification', channel: 'email' }],
  is_template: false,
  is_active: true,
  source_template_id: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('PlaybookEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders all editable fields', () => {
    render(<PlaybookEditor onSave={mockCreatePlaybook} onCancel={vi.fn()} />);
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
    expect(screen.getByText(/probability range/i)).toBeInTheDocument();
    expect(screen.getByText(/action sequence/i)).toBeInTheDocument();
  });

  it('probability range inputs enforce min < max constraint', async () => {
    render(<PlaybookEditor onSave={mockCreatePlaybook} onCancel={vi.fn()} />);
    const minInput = screen.getByTestId('prob-min-input');
    const maxInput = screen.getByTestId('prob-max-input');

    fireEvent.change(minInput, { target: { value: '0.90' } });
    fireEvent.change(maxInput, { target: { value: '0.50' } });

    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(screen.getByText(/min.*less than.*max|max.*greater than.*min/i)).toBeInTheDocument();
    });
    expect(mockCreatePlaybook).not.toHaveBeenCalled();
  });

  it('action sequence builder allows adding an action', () => {
    render(<PlaybookEditor onSave={mockCreatePlaybook} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /add action/i }));
    expect(screen.getAllByTestId(/action-card/)).toHaveLength(1);
  });

  it('action sequence builder allows removing an action', () => {
    render(<PlaybookEditor playbook={basePlaybook} onSave={mockUpdatePlaybook} onCancel={vi.fn()} />);
    expect(screen.getAllByTestId(/action-card/)).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: /remove action/i }));
    expect(screen.queryAllByTestId(/action-card/)).toHaveLength(0);
  });

  it('calls createPlaybook on submit with valid data', async () => {
    mockCreatePlaybook.mockResolvedValue({ id: 99 });
    render(<PlaybookEditor onSave={mockCreatePlaybook} onCancel={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'My Playbook' } });
    fireEvent.change(screen.getByTestId('prob-min-input'), { target: { value: '0.30' } });
    fireEvent.change(screen.getByTestId('prob-max-input'), { target: { value: '0.70' } });
    fireEvent.click(screen.getByRole('button', { name: /add action/i }));

    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(mockCreatePlaybook).toHaveBeenCalled();
    });
  });

  it('shows validation error for empty name', async () => {
    render(<PlaybookEditor onSave={mockCreatePlaybook} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(screen.getByText(/name is required|name.*required/i)).toBeInTheDocument();
    });
    expect(mockCreatePlaybook).not.toHaveBeenCalled();
  });

  it('shows validation error for empty action sequence', async () => {
    render(<PlaybookEditor onSave={mockCreatePlaybook} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'My Playbook' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(screen.getByText(/at least one action|action.*required/i)).toBeInTheDocument();
    });
    expect(mockCreatePlaybook).not.toHaveBeenCalled();
  });

  it('cancel button fires onCancel without saving', () => {
    const onCancel = vi.fn();
    render(<PlaybookEditor onSave={mockCreatePlaybook} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalled();
    expect(mockCreatePlaybook).not.toHaveBeenCalled();
  });

  it('disables all inputs in read-only mode (template)', () => {
    const template: Playbook = { ...basePlaybook, is_template: true, organization_id: null };
    render(
      <PlaybookEditor
        playbook={template}
        onSave={mockCreatePlaybook}
        onCancel={vi.fn()}
        readOnly
      />
    );
    expect(screen.getByLabelText(/name/i)).toBeDisabled();
    expect(screen.getByLabelText(/description/i)).toBeDisabled();
    expect(screen.queryByRole('button', { name: /save/i })).not.toBeInTheDocument();
  });
});
