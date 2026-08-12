import { describe, it, expect } from 'vitest';
import {
  ACTION_TYPE_LABELS,
  SEND_EMAIL_RECIPIENTS,
  type PlaybookAction,
} from '@/lib/api/playbooks';

describe('playbooks send_email action surface', () => {
  it('labels the send_email action type', () => {
    expect(ACTION_TYPE_LABELS.send_email).toBe('Send Email');
  });

  it('type-checks a seeder-shaped send_email action', () => {
    const action: PlaybookAction = {
      type: 'send_email',
      config: { template: 'weekly_digest_entry', recipient: 'cs_assignee' },
    };
    expect(action.type).toBe('send_email');
    expect(action.config).toEqual({
      template: 'weekly_digest_entry',
      recipient: 'cs_assignee',
    });
  });

  it('exports the recipient list as the single source of truth', () => {
    expect(SEND_EMAIL_RECIPIENTS).toEqual(['customer', 'cs_assignee']);
  });
});
