import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { IntegrationBar } from '@/components/landing/IntegrationBar';

vi.mock('@/components/icons/SlackIcon', () => ({
  SlackIcon: ({ className }: { className?: string }) => (
    <svg data-testid="slack-icon" className={className} />
  ),
}));

vi.mock('@/components/icons/IntercomIcon', () => ({
  IntercomIcon: ({ className }: { className?: string }) => (
    <svg data-testid="intercom-icon" className={className} />
  ),
}));

vi.mock('@/components/icons/EmailIcon', () => ({
  EmailIcon: ({ className }: { className?: string }) => (
    <svg data-testid="email-icon" className={className} />
  ),
}));

vi.mock('@/components/icons/ZendeskIcon', () => ({
  ZendeskIcon: ({ className }: { className?: string }) => (
    <svg data-testid="zendesk-icon" className={className} />
  ),
}));

vi.mock('@/components/icons/HubSpotIcon', () => ({
  HubSpotIcon: ({ className }: { className?: string }) => (
    <svg data-testid="hubspot-icon" className={className} />
  ),
}));

describe('IntegrationBar', () => {
  it('renders heading "Connect Your Feedback Sources"', () => {
    render(<IntegrationBar />);
    expect(screen.getByText('Connect Your Feedback Sources')).toBeInTheDocument();
  });

  it('renders 5 integration items with accessible labels: Slack, Intercom, Email, Zendesk, HubSpot', () => {
    render(<IntegrationBar />);
    expect(screen.getByLabelText('Slack')).toBeInTheDocument();
    expect(screen.getByLabelText('Intercom')).toBeInTheDocument();
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Zendesk')).toBeInTheDocument();
    expect(screen.getByLabelText('HubSpot')).toBeInTheDocument();
  });

  it('renders subtitle "Works with the tools you already use"', () => {
    render(<IntegrationBar />);
    expect(screen.getByText(/Works with the tools you already use/)).toBeInTheDocument();
  });
});
