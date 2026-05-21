import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

// Mock next/link
vi.mock('next/link', () => ({
  default: ({ children, ...props }: any) => <a {...props}>{children}</a>,
}));

// Mock GSAP (lazy-loaded, won't work in jsdom)
vi.mock('gsap', () => ({
  default: {
    registerPlugin: vi.fn(),
    timeline: vi.fn(() => ({ to: vi.fn(), from: vi.fn(), fromTo: vi.fn() })),
    to: vi.fn(),
    from: vi.fn(),
    fromTo: vi.fn(),
    set: vi.fn(),
  },
  gsap: {
    registerPlugin: vi.fn(),
    timeline: vi.fn(() => ({ to: vi.fn(), from: vi.fn(), fromTo: vi.fn() })),
    to: vi.fn(),
    from: vi.fn(),
    fromTo: vi.fn(),
    set: vi.fn(),
  },
}));

vi.mock('gsap/ScrollTrigger', () => ({
  ScrollTrigger: { refresh: vi.fn() },
}));

vi.mock('@gsap/react', () => ({
  useGSAP: vi.fn((fn: () => void) => fn()),
}));

import BentoFeatures from '@/components/landing/BentoFeatures';

describe('BentoFeatures', () => {
  // Section structure
  it('renders section with "Powerful Features" badge', () => {
    render(<BentoFeatures />);
    expect(screen.getByText('Powerful Features')).toBeInTheDocument();
  });

  it('renders section heading with "Analyze feedback." text', () => {
    render(<BentoFeatures />);
    expect(screen.getByText(/Analyze feedback\./)).toBeInTheDocument();
  });

  // Large card - AI Copilot
  it('renders AI Copilot card with heading "AI Copilot"', () => {
    render(<BentoFeatures />);
    expect(screen.getByTestId('card-ai-copilot')).toBeInTheDocument();
    expect(screen.getByTestId('card-ai-copilot')).toHaveTextContent('AI Copilot');
  });

  it('AI Copilot card shows subheading "Ask your feedback data anything"', () => {
    render(<BentoFeatures />);
    expect(screen.getByTestId('card-ai-copilot')).toHaveTextContent('Ask your feedback data anything');
  });

  it('AI Copilot card shows 4 bullet points: Cmd+K command bar, Natural language queries, SQL generation, Charts and tables', () => {
    render(<BentoFeatures />);
    const card = screen.getByTestId('card-ai-copilot');
    expect(card).toHaveTextContent('Cmd+K command bar');
    expect(card).toHaveTextContent('Natural language queries');
    expect(card).toHaveTextContent('SQL generation');
    expect(card).toHaveTextContent('Charts and tables');
  });

  it('AI Copilot card has large variant styling (data-size="large")', () => {
    render(<BentoFeatures />);
    expect(screen.getByTestId('card-ai-copilot')).toHaveAttribute('data-size', 'large');
  });

  // Medium card - Customer 360
  it('renders Customer 360 card with heading "Customer 360"', () => {
    render(<BentoFeatures />);
    expect(screen.getByTestId('card-customer-360')).toBeInTheDocument();
    expect(screen.getByTestId('card-customer-360')).toHaveTextContent('Customer 360');
  });

  it('Customer 360 card shows subtext about health scores and churn prediction', () => {
    render(<BentoFeatures />);
    expect(screen.getByTestId('card-customer-360')).toHaveTextContent('Health scores');
  });

  it('Customer 360 card shows 3 key points: Health score dashboard, 9-factor churn risk, Automated recovery alerts', () => {
    render(<BentoFeatures />);
    const card = screen.getByTestId('card-customer-360');
    expect(card).toHaveTextContent('Health score dashboard');
    expect(card).toHaveTextContent('9-factor churn risk');
    expect(card).toHaveTextContent('Automated recovery alerts');
  });

  // Medium card - Multi-Model AI
  it('renders Multi-Model AI card with heading "Choose Your AI"', () => {
    render(<BentoFeatures />);
    expect(screen.getByTestId('card-multi-model')).toBeInTheDocument();
    expect(screen.getByTestId('card-multi-model')).toHaveTextContent('Choose Your AI');
  });

  it('Multi-Model card shows subtext about BYOK', () => {
    render(<BentoFeatures />);
    expect(screen.getByTestId('card-multi-model')).toHaveTextContent('BYOK');
  });

  it('Multi-Model card shows 3 key points: OpenAI/Anthropic/Google, Automatic fallback chains, Per-org budget tracking', () => {
    render(<BentoFeatures />);
    const card = screen.getByTestId('card-multi-model');
    expect(card).toHaveTextContent('OpenAI');
    expect(card).toHaveTextContent('Anthropic');
    expect(card).toHaveTextContent('Google');
    expect(card).toHaveTextContent('Automatic fallback chains');
    expect(card).toHaveTextContent('Per-org budget tracking');
  });

  // Small cards (8 total)
  it('renders "AI Churn Detection" small card', () => {
    render(<BentoFeatures />);
    expect(screen.getByTestId('card-ai-churn-detection')).toBeInTheDocument();
    expect(screen.getByTestId('card-ai-churn-detection')).toHaveTextContent('AI Churn Detection');
  });

  it('renders "Feedback Workflow" small card', () => {
    render(<BentoFeatures />);
    expect(screen.getByTestId('card-feedback-workflow')).toBeInTheDocument();
    expect(screen.getByTestId('card-feedback-workflow')).toHaveTextContent('Feedback Workflow');
  });

  it('renders "Smart Categorization" small card', () => {
    render(<BentoFeatures />);
    expect(screen.getByTestId('card-smart-categorization')).toBeInTheDocument();
    expect(screen.getByTestId('card-smart-categorization')).toHaveTextContent('Smart Categorization');
  });

  it('renders "Real-Time Alerts" small card', () => {
    render(<BentoFeatures />);
    expect(screen.getByTestId('card-real-time-alerts')).toBeInTheDocument();
    expect(screen.getByTestId('card-real-time-alerts')).toHaveTextContent('Real-Time Alerts');
  });

  it('renders "Weekly AI Insights" small card', () => {
    render(<BentoFeatures />);
    expect(screen.getByTestId('card-weekly-ai-insights')).toBeInTheDocument();
    expect(screen.getByTestId('card-weekly-ai-insights')).toHaveTextContent('Weekly AI Insights');
  });

  it('renders "Dashboard Sharing" small card', () => {
    render(<BentoFeatures />);
    expect(screen.getByTestId('card-dashboard-sharing')).toBeInTheDocument();
    expect(screen.getByTestId('card-dashboard-sharing')).toHaveTextContent('Dashboard Sharing');
  });

  it('renders "Trend Analytics" small card', () => {
    render(<BentoFeatures />);
    expect(screen.getByTestId('card-trend-analytics')).toBeInTheDocument();
    expect(screen.getByTestId('card-trend-analytics')).toHaveTextContent('Trend Analytics');
  });

  it('renders "Integrations" small card', () => {
    render(<BentoFeatures />);
    expect(screen.getByTestId('card-integrations')).toBeInTheDocument();
    expect(screen.getByTestId('card-integrations')).toHaveTextContent('Integrations');
  });

  it('each small card has an icon and description text', () => {
    render(<BentoFeatures />);
    const smallCardIds = [
      'card-ai-churn-detection',
      'card-feedback-workflow',
      'card-smart-categorization',
      'card-real-time-alerts',
      'card-weekly-ai-insights',
      'card-dashboard-sharing',
      'card-trend-analytics',
      'card-integrations',
    ];
    for (const id of smallCardIds) {
      const card = screen.getByTestId(id);
      // Each small card should have data-size="small"
      expect(card).toHaveAttribute('data-size', 'small');
      // Each small card should have an svg icon (lucide-react renders svg)
      expect(card.querySelector('svg')).toBeInTheDocument();
    }
  });

  // Total count
  it('renders exactly 14 feature cards total (1 large + 2 medium + 11 small)', () => {
    render(<BentoFeatures />);
    const largeCards = document.querySelectorAll('[data-size="large"]');
    const mediumCards = document.querySelectorAll('[data-size="medium"]');
    const smallCards = document.querySelectorAll('[data-size="small"]');

    expect(largeCards).toHaveLength(1);
    expect(mediumCards).toHaveLength(2);
    expect(smallCards).toHaveLength(11);
  });

  // Churn prediction card
  it('renders "30-Day Churn Probability" small card', () => {
    render(<BentoFeatures />);
    expect(screen.getByTestId('card-churn-prediction')).toBeInTheDocument();
    expect(screen.getByTestId('card-churn-prediction')).toHaveTextContent('30-Day Churn Probability');
  });

  it('churn prediction card describes calibrated probabilities and prevention playbooks', () => {
    render(<BentoFeatures />);
    const card = screen.getByTestId('card-churn-prediction');
    expect(card).toHaveTextContent('calibrated probabilities');
    expect(card).toHaveTextContent('prevention playbooks');
  });
});
