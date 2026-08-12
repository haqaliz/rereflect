import apiClient from '../api-client';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface OutreachTemplateSummary {
  key: string;
  label: string;
  description: string;
}

// ─── API Client ───────────────────────────────────────────────────────────────

export async function listOutreachTemplates(): Promise<OutreachTemplateSummary[]> {
  const response = await apiClient.get('/api/v1/outreach/templates');
  return response.data;
}

// ─── Constants ────────────────────────────────────────────────────────────────

/**
 * Contract-pinned fallback registry (outreach-core AC2). Keys are named
 * verbatim by the seeded playbook templates (`playbook_seeder.py:111,215`)
 * and the backend registry (`outreach_templates.py`); labels mirror the
 * backend registry. Used when `GET /api/v1/outreach/templates` fails so the
 * editor never bricks playbooks that already contain send_email steps.
 */
export const BUILTIN_OUTREACH_TEMPLATES: OutreachTemplateSummary[] = [
  {
    key: 're_engagement',
    label: 'Re-engagement check-in',
    description:
      'A friendly nudge for customers who have gone quiet — invites them to tell you what happened, no hard sell.',
  },
  {
    key: 'weekly_digest_entry',
    label: 'Weekly digest entry',
    description:
      'A short weekly check-in that keeps the relationship warm — highlights, fixes, and what\'s coming next.',
  },
];
