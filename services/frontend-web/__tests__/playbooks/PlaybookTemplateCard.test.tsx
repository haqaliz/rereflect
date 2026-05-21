import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { PlaybookTemplateCard } from '@/components/playbooks/PlaybookTemplateCard';
import type { Playbook } from '@/lib/api/playbooks';

const basePlaybook: Playbook = {
  id: 1,
  organization_id: null,
  name: 'Critical Save',
  description: 'For critical churn risk customers',
  probability_min: 0.85,
  probability_max: 1.0,
  action_sequence: [
    { type: 'assign', assignee_role: 'cs_lead' },
    { type: 'send_notification', channel: 'slack' },
  ],
  is_template: true,
  is_active: true,
  source_template_id: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('PlaybookTemplateCard', () => {
  it('renders name, description, and probability range', () => {
    render(<PlaybookTemplateCard playbook={basePlaybook} onUse={vi.fn()} />);
    expect(screen.getByText('Critical Save')).toBeInTheDocument();
    expect(screen.getByText('For critical churn risk customers')).toBeInTheDocument();
    expect(screen.getByText(/85%.*100%|0\.85.*1\.00/)).toBeInTheDocument();
  });

  it('shows action count', () => {
    render(<PlaybookTemplateCard playbook={basePlaybook} onUse={vi.fn()} />);
    expect(screen.getByText(/2 action/i)).toBeInTheDocument();
  });

  it('"Use template" button calls onUse handler', () => {
    const onUse = vi.fn();
    render(<PlaybookTemplateCard playbook={basePlaybook} onUse={onUse} />);
    fireEvent.click(screen.getByRole('button', { name: /use template/i }));
    expect(onUse).toHaveBeenCalledWith(basePlaybook);
  });

  it('"Active" toggle is NOT shown for template playbooks', () => {
    render(<PlaybookTemplateCard playbook={basePlaybook} onUse={vi.fn()} />);
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
  });

  it('Active toggle is shown and calls onToggleActive for non-template playbooks', () => {
    const orgPlaybook: Playbook = { ...basePlaybook, is_template: false, organization_id: 42 };
    const onToggleActive = vi.fn();
    render(
      <PlaybookTemplateCard
        playbook={orgPlaybook}
        onUse={vi.fn()}
        onToggleActive={onToggleActive}
      />
    );
    const toggle = screen.getByRole('switch');
    expect(toggle).toBeInTheDocument();
    fireEvent.click(toggle);
    expect(onToggleActive).toHaveBeenCalledWith(!orgPlaybook.is_active);
  });
});
