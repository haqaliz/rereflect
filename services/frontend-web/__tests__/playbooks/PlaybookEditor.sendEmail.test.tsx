import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

const REGISTRY = [
  { key: 're_engagement', label: 'Re-engagement check-in', description: 'nudge' },
  { key: 'weekly_digest_entry', label: 'Weekly digest entry', description: 'digest' },
];

const mockListOutreachTemplates = vi.fn();

vi.mock('@/lib/api/outreach', () => ({
  listOutreachTemplates: (...args: unknown[]) => mockListOutreachTemplates(...args),
  BUILTIN_OUTREACH_TEMPLATES: [
    { key: 're_engagement', label: 'Re-engagement check-in', description: 'nudge' },
    { key: 'weekly_digest_entry', label: 'Weekly digest entry', description: 'digest' },
  ],
}));

vi.mock('@/lib/api/playbooks', () => ({
  ACTION_TYPE_LABELS: {
    assign: 'Assign',
    change_status: 'Change Status',
    send_notification: 'Send Notification',
    draft_response: 'Draft AI Response',
    send_email: 'Send Email',
  },
  SEND_EMAIL_RECIPIENTS: ['customer', 'cs_assignee'],
  SEND_EMAIL_RECIPIENT_LABELS: { customer: 'Customer', cs_assignee: 'CS Assignee' },
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';
import { PlaybookEditor } from '@/components/playbooks/PlaybookEditor';
import type { Playbook } from '@/lib/api/playbooks';

const basePlaybook: Playbook = {
  id: 6,
  organization_id: 1,
  name: 'Outreach',
  description: null,
  probability_min: 0.5,
  probability_max: 0.7,
  action_sequence: [],
  is_template: false,
  is_active: true,
  source_template_id: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const sendEmailPlaybook: Playbook = {
  ...basePlaybook,
  action_sequence: [
    { type: 'send_email', config: { template: 're_engagement', recipient: 'customer' } },
  ],
};

const atRiskSequence: Playbook = {
  ...basePlaybook,
  name: 'At-Risk Outreach',
  action_sequence: [
    { type: 'send_email', config: { template: 'weekly_digest_entry', recipient: 'cs_assignee' } },
  ],
};

describe('PlaybookEditor — send_email step config', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListOutreachTemplates.mockResolvedValue(REGISTRY);
  });

  it('renders template + recipient selects seeded from action.config (AC1)', async () => {
    render(<PlaybookEditor playbook={sendEmailPlaybook} onSave={vi.fn()} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /template/i })).toHaveTextContent(
        'Re-engagement check-in'
      );
    });
    expect(screen.getByRole('combobox', { name: /recipient/i })).toHaveTextContent('Customer');
  });

  it('changing template + recipient updates the save payload exactly (AC2)', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<PlaybookEditor playbook={sendEmailPlaybook} onSave={onSave} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /template/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('combobox', { name: /template/i }));
    await user.click(await screen.findByRole('option', { name: 'Weekly digest entry' }));

    await user.click(screen.getByRole('combobox', { name: /recipient/i }));
    await user.click(await screen.findByRole('option', { name: 'CS Assignee' }));

    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          action_sequence: [
            {
              type: 'send_email',
              config: { template: 'weekly_digest_entry', recipient: 'cs_assignee' },
            },
          ],
        })
      );
    });
  });

  it('switching an existing step to send_email initializes default config (AC4)', async () => {
    const user = userEvent.setup();
    const playbook: Playbook = {
      ...basePlaybook,
      action_sequence: [{ type: 'send_notification', channel: 'email' }],
    };
    render(<PlaybookEditor playbook={playbook} onSave={vi.fn()} onCancel={vi.fn()} />);

    await user.click(screen.getByRole('combobox', { name: /action type/i }));
    await user.click(await screen.findByRole('option', { name: 'Send Email' }));

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /template/i })).toHaveTextContent(
        'Re-engagement check-in'
      );
    });
    expect(screen.getByRole('combobox', { name: /recipient/i })).toHaveTextContent('Customer');
  });

  it('switching away and back preserves the config (AC4)', async () => {
    const user = userEvent.setup();
    render(<PlaybookEditor playbook={atRiskSequence} onSave={vi.fn()} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /template/i })).toHaveTextContent(
        'Weekly digest entry'
      );
    });

    await user.click(screen.getByRole('combobox', { name: /action type/i }));
    await user.click(await screen.findByRole('option', { name: 'Send Notification' }));
    expect(screen.queryByRole('combobox', { name: /template/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole('combobox', { name: /action type/i }));
    await user.click(await screen.findByRole('option', { name: 'Send Email' }));

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /template/i })).toHaveTextContent(
        'Weekly digest entry'
      );
    });
    expect(screen.getByRole('combobox', { name: /recipient/i })).toHaveTextContent('CS Assignee');
  });

  it('unknown template key renders the raw key with a warning and is preserved on save (AC5)', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const playbook: Playbook = {
      ...basePlaybook,
      action_sequence: [
        { type: 'send_email', config: { template: 'legacy_custom_key', recipient: 'customer' } },
      ],
    };
    render(<PlaybookEditor playbook={playbook} onSave={onSave} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /template/i })).toHaveTextContent(
        'legacy_custom_key'
      );
    });
    expect(screen.getByRole('alert')).toHaveTextContent(/legacy_custom_key/);

    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          action_sequence: [
            {
              type: 'send_email',
              config: { template: 'legacy_custom_key', recipient: 'customer' },
            },
          ],
        })
      );
    });
  });

  it('registry fetch failure degrades to built-in keys with a toast (AC6)', async () => {
    mockListOutreachTemplates.mockRejectedValue(new Error('network down'));
    render(<PlaybookEditor playbook={sendEmailPlaybook} onSave={vi.fn()} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
    expect(screen.getByRole('combobox', { name: /template/i })).toHaveTextContent(
      'Re-engagement check-in'
    );
    expect(screen.getByRole('combobox', { name: /recipient/i })).toHaveTextContent('Customer');
  });

  it('readOnly renders a text summary of the config, never selects', async () => {
    render(
      <PlaybookEditor playbook={sendEmailPlaybook} readOnly onSave={vi.fn()} onCancel={vi.fn()} />
    );

    await waitFor(() => {
      expect(screen.getByText(/email template:/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/email template:/i)).toHaveTextContent('Re-engagement check-in');
    expect(screen.getByText(/email template:/i)).toHaveTextContent('Customer');
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('send_email step with no config renders defaults and saves the resolved config', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const playbook: Playbook = {
      ...basePlaybook,
      action_sequence: [{ type: 'send_email' }],
    };
    render(<PlaybookEditor playbook={playbook} onSave={onSave} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /template/i })).toHaveTextContent(
        'Re-engagement check-in'
      );
    });
    expect(screen.getByRole('combobox', { name: /recipient/i })).toHaveTextContent('Customer');

    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          action_sequence: [
            { type: 'send_email', config: { template: 're_engagement', recipient: 'customer' } },
          ],
        })
      );
    });
  });

  it('clone-flow round trip: At-Risk Outreach template renders pre-populated and re-saves unchanged (AC8)', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<PlaybookEditor playbook={atRiskSequence} onSave={onSave} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /template/i })).toHaveTextContent(
        'Weekly digest entry'
      );
    });
    expect(screen.getByRole('combobox', { name: /recipient/i })).toHaveTextContent('CS Assignee');

    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          action_sequence: [
            {
              type: 'send_email',
              config: { template: 'weekly_digest_entry', recipient: 'cs_assignee' },
            },
          ],
        })
      );
    });
  });
});
