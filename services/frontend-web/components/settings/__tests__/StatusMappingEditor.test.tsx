import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => mockToastSuccess(...args),
    error: (...args: unknown[]) => mockToastError(...args),
  },
}));

import { StatusMappingEditor } from '@/components/settings/StatusMappingEditor';

const foreignKeys = [
  { key: 'new', label: 'Category: To Do (new)' },
  { key: 'indeterminate', label: 'Category: In Progress (indeterminate)' },
  { key: 'done', label: 'Category: Done' },
];

describe('StatusMappingEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders one row per foreign key', () => {
    render(
      <StatusMappingEditor foreignKeys={foreignKeys} currentMapping={null} onSave={vi.fn()} />
    );
    expect(screen.getByText('Category: To Do (new)')).toBeInTheDocument();
    expect(screen.getByText('Category: In Progress (indeterminate)')).toBeInTheDocument();
    expect(screen.getByText('Category: Done')).toBeInTheDocument();
    expect(screen.getAllByRole('combobox')).toHaveLength(3);
  });

  it('shows the target-state options for a row', async () => {
    const user = userEvent.setup();
    render(
      <StatusMappingEditor foreignKeys={foreignKeys} currentMapping={null} onSave={vi.fn()} />
    );
    const triggers = screen.getAllByRole('combobox');
    await user.click(triggers[0]);
    await waitFor(() => {
      expect(screen.getByText('New')).toBeInTheDocument();
      expect(screen.getByText('In Review')).toBeInTheDocument();
      expect(screen.getByText('Resolved')).toBeInTheDocument();
      expect(screen.getByText('Closed')).toBeInTheDocument();
    });
  });

  it('pre-selects the current mapping value for each row', () => {
    render(
      <StatusMappingEditor
        foreignKeys={foreignKeys}
        currentMapping={{ new: 'new', indeterminate: 'in_review', done: 'resolved' }}
        onSave={vi.fn()}
      />
    );
    const triggers = screen.getAllByRole('combobox');
    expect(triggers[0]).toHaveTextContent('New');
    expect(triggers[1]).toHaveTextContent('In Review');
    expect(triggers[2]).toHaveTextContent('Resolved');
  });

  it('Save is disabled until a row is changed (not dirty)', () => {
    render(
      <StatusMappingEditor
        foreignKeys={foreignKeys}
        currentMapping={{ new: 'new' }}
        onSave={vi.fn()}
      />
    );
    expect(screen.getByRole('button', { name: /save mapping/i })).toBeDisabled();
  });

  it('changing a row marks the editor dirty and enables Save', async () => {
    const user = userEvent.setup();
    render(
      <StatusMappingEditor foreignKeys={foreignKeys} currentMapping={null} onSave={vi.fn()} />
    );
    const triggers = screen.getAllByRole('combobox');
    await user.click(triggers[0]);
    await waitFor(() => screen.getByText('Resolved'));
    await user.click(screen.getByText('Resolved'));

    expect(screen.getByRole('button', { name: /save mapping/i })).toBeEnabled();
  });

  it('Save calls onSave with the full mapping object and toasts on success', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <StatusMappingEditor
        foreignKeys={foreignKeys}
        currentMapping={{ new: 'new', indeterminate: 'in_review', done: 'resolved' }}
        onSave={onSave}
      />
    );
    const triggers = screen.getAllByRole('combobox');
    await user.click(triggers[2]);
    await waitFor(() => screen.getByText('Closed'));
    await user.click(screen.getByText('Closed'));

    await user.click(screen.getByRole('button', { name: /save mapping/i }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith({ new: 'new', indeterminate: 'in_review', done: 'closed' });
      expect(mockToastSuccess).toHaveBeenCalled();
    });
  });

  it('toasts an error when onSave rejects', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockRejectedValue({
      response: { data: { detail: 'Invalid status mapping.' } },
    });
    render(
      <StatusMappingEditor
        foreignKeys={foreignKeys}
        currentMapping={{ new: 'new' }}
        onSave={onSave}
      />
    );
    const triggers = screen.getAllByRole('combobox');
    await user.click(triggers[0]);
    await waitFor(() => screen.getByText('Closed'));
    await user.click(screen.getByText('Closed'));

    await user.click(screen.getByRole('button', { name: /save mapping/i }));

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith('Invalid status mapping.');
    });
  });

  it('"Reset to defaults" clears the mapping and calls onSave with an empty object', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <StatusMappingEditor
        foreignKeys={foreignKeys}
        currentMapping={{ new: 'new', indeterminate: 'in_review', done: 'resolved' }}
        onSave={onSave}
      />
    );

    await user.click(screen.getByRole('button', { name: /reset to defaults/i }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith({});
      expect(mockToastSuccess).toHaveBeenCalled();
    });
  });

  it('disables all controls and hides Save/Reset when disabled', () => {
    render(
      <StatusMappingEditor
        foreignKeys={foreignKeys}
        currentMapping={{ new: 'new' }}
        onSave={vi.fn()}
        disabled
      />
    );
    screen.getAllByRole('combobox').forEach((trigger) => {
      expect(trigger).toBeDisabled();
    });
    expect(screen.queryByRole('button', { name: /save mapping/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /reset to defaults/i })).not.toBeInTheDocument();
  });

  it('renders the optional description text', () => {
    render(
      <StatusMappingEditor
        foreignKeys={foreignKeys}
        currentMapping={null}
        onSave={vi.fn()}
        description="Map Jira status categories to Rereflect statuses."
      />
    );
    expect(screen.getByText('Map Jira status categories to Rereflect statuses.')).toBeInTheDocument();
  });
});
