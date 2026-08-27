import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import React from 'react';
import { PlaybookExecutionsList } from '@/components/playbooks/PlaybookExecutionsList';
import type { PlaybookExecution } from '@/lib/api/playbooks';

const baseExecution: PlaybookExecution = {
  id: 1,
  playbook_id: 10,
  customer_email: 'ada@example.com',
  status: 'done',
  triggered_by: 'automation',
  action_log: [],
  error_message: null,
  started_at: '2026-01-01T10:00:00Z',
  completed_at: '2026-01-01T10:01:00Z',
  created_at: '2026-01-01T10:00:00Z',
};

const executionWithLog: PlaybookExecution = {
  ...baseExecution,
  id: 2,
  customer_email: 'grace@example.com',
  action_log: [
    { type: 'tag', ok: true, result: { tag: 'at-risk', tags: ['at-risk'] } },
    { type: 'notify', ok: false, result: { channel: 'slack' }, error: 'no slack integration connected' },
    { type: 'create_task', ok: true, result: { task_id: 42, description: 'Call', due_at: null } },
    { type: 'send_notification', ok: true, result: 'delivered' },
  ],
};

describe('PlaybookExecutionsList — action log surfacing', () => {
  it('renders rows with status and a "View actions" affordance', () => {
    render(<PlaybookExecutionsList executions={[baseExecution, executionWithLog]} />);

    expect(screen.getByText('ada@example.com')).toBeInTheDocument();
    expect(screen.getAllByText('Done')).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: /view actions/i })).toHaveLength(2);
  });

  it('expanding a row renders each action_log entry with type label and ok/error badge', async () => {
    render(<PlaybookExecutionsList executions={[executionWithLog]} />);

    fireEvent.click(screen.getByRole('button', { name: /view actions/i }));

    const view = screen.getByTestId('execution-actions-2');
    expect(within(view).getByText('Tag')).toBeInTheDocument();
    expect(within(view).getByText('Notify')).toBeInTheDocument();
    expect(within(view).getByText('Create task')).toBeInTheDocument();
    expect(within(view).getByText('Send Notification')).toBeInTheDocument();
    expect(within(view).getAllByText('OK')).toHaveLength(3);
    expect(within(view).getByText('Error')).toBeInTheDocument();
  });

  it('renders the error badge with the destructive variant and shows the error text', async () => {
    render(<PlaybookExecutionsList executions={[executionWithLog]} />);

    fireEvent.click(screen.getByRole('button', { name: /view actions/i }));

    const view = screen.getByTestId('execution-actions-2');
    const errorBadge = within(view).getByText('Error');
    expect(errorBadge.className).toContain('destructive');
    expect(within(view).getByText('no slack integration connected')).toBeInTheDocument();
  });

  it('renders an object result as a JSON summary (e.g. task_id)', async () => {
    render(<PlaybookExecutionsList executions={[executionWithLog]} />);

    fireEvent.click(screen.getByRole('button', { name: /view actions/i }));

    const view = screen.getByTestId('execution-actions-2');
    expect(within(view).getByText(/"task_id"\s*:\s*42/)).toBeInTheDocument();
    expect(within(view).getByText(/"tag"\s*:\s*"at-risk"/)).toBeInTheDocument();
  });

  it('renders a non-object result safely via String(result)', async () => {
    render(<PlaybookExecutionsList executions={[executionWithLog]} />);

    fireEvent.click(screen.getByRole('button', { name: /view actions/i }));

    const view = screen.getByTestId('execution-actions-2');
    expect(within(view).getByText('delivered')).toBeInTheDocument();
  });

  it('shows "No actions recorded" when action_log is missing or empty', async () => {
    const emptyLog: PlaybookExecution = { ...baseExecution, id: 3 };
    const missingLog: PlaybookExecution = {
      ...baseExecution,
      id: 4,
      action_log: undefined as unknown as PlaybookExecution['action_log'],
    };
    render(<PlaybookExecutionsList executions={[emptyLog, missingLog]} />);

    const buttons = screen.getAllByRole('button', { name: /view actions/i });
    fireEvent.click(buttons[0]);
    expect(screen.getByTestId('execution-actions-3')).toHaveTextContent('No actions recorded');

    fireEvent.click(buttons[1]);
    expect(screen.getByTestId('execution-actions-4')).toHaveTextContent('No actions recorded');
  });
});