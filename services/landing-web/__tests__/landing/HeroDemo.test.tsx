import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

import HeroDemo from '@/components/landing/HeroDemo';

// Mock matchMedia to prevent GSAP from loading in tests
beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: query === '(prefers-reduced-motion: reduce)',
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  });
});

describe('HeroDemo', () => {
  // Source nodes
  it('renders Slack source node with label', () => {
    render(<HeroDemo />);
    expect(screen.getByTestId('source-slack')).toBeInTheDocument();
    expect(screen.getByText('Slack')).toBeInTheDocument();
  });

  it('renders Email source node with label', () => {
    render(<HeroDemo />);
    expect(screen.getByTestId('source-email')).toBeInTheDocument();
    expect(screen.getByText('Email')).toBeInTheDocument();
  });

  it('renders Intercom source node with label', () => {
    render(<HeroDemo />);
    expect(screen.getByTestId('source-intercom')).toBeInTheDocument();
    expect(screen.getByText('Intercom')).toBeInTheDocument();
  });

  // AI center node
  it('renders AI processing node with data-testid="ai-brain"', () => {
    render(<HeroDemo />);
    expect(screen.getByTestId('ai-brain')).toBeInTheDocument();
  });

  it('AI node displays "AI" label', () => {
    render(<HeroDemo />);
    const aiNode = screen.getByTestId('ai-brain');
    expect(aiNode).toHaveTextContent('AI');
  });

  // Output category nodes
  it('renders Positive output node with label', () => {
    render(<HeroDemo />);
    expect(screen.getByTestId('output-positive')).toBeInTheDocument();
    expect(screen.getByText('Positive')).toBeInTheDocument();
  });

  it('renders Pain Point output node with label', () => {
    render(<HeroDemo />);
    expect(screen.getByTestId('output-pain-point')).toBeInTheDocument();
    expect(screen.getByText('Pain Point')).toBeInTheDocument();
  });

  it('renders Feature output node with label', () => {
    render(<HeroDemo />);
    expect(screen.getByTestId('output-feature')).toBeInTheDocument();
    expect(screen.getByText('Feature')).toBeInTheDocument();
  });

  // SVG flow structure
  it('renders an SVG element with flow diagram', () => {
    render(<HeroDemo />);
    const container = screen.getByTestId('hero-demo');
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
    expect(svg).toHaveAttribute('viewBox');
  });

  it('SVG contains flow path definitions in defs', () => {
    render(<HeroDemo />);
    const container = screen.getByTestId('hero-demo');
    const defs = container.querySelector('defs');
    expect(defs).toBeInTheDocument();
    const paths = defs!.querySelectorAll('path');
    expect(paths.length).toBeGreaterThanOrEqual(6);
  });

  it('renders animated particles for flow effect', () => {
    render(<HeroDemo />);
    const container = screen.getByTestId('hero-demo');
    const particles = container.querySelectorAll('.flow-particle');
    expect(particles.length).toBeGreaterThan(0);
  });

  // Accessibility
  it('has aria-label "Product demo animation" on container', () => {
    render(<HeroDemo />);
    expect(screen.getByLabelText('Product demo animation')).toBeInTheDocument();
  });

  it('SVG has role="img" and aria-label for screen readers', () => {
    render(<HeroDemo />);
    const svg = screen.getByRole('img', { name: 'AI feedback analysis flow' });
    expect(svg).toBeInTheDocument();
  });

  it('renders Churn Risk output node with label', () => {
    render(<HeroDemo />);
    expect(screen.getByTestId('output-churn-risk')).toBeInTheDocument();
    expect(screen.getByText('Churn Risk')).toBeInTheDocument();
  });

  it('renders 3 source nodes, 1 AI node, and 4 output nodes', () => {
    render(<HeroDemo />);
    expect(screen.getByTestId('source-slack')).toBeInTheDocument();
    expect(screen.getByTestId('source-email')).toBeInTheDocument();
    expect(screen.getByTestId('source-intercom')).toBeInTheDocument();
    expect(screen.getByTestId('ai-brain')).toBeInTheDocument();
    expect(screen.getByTestId('output-positive')).toBeInTheDocument();
    expect(screen.getByTestId('output-pain-point')).toBeInTheDocument();
    expect(screen.getByTestId('output-feature')).toBeInTheDocument();
    expect(screen.getByTestId('output-churn-risk')).toBeInTheDocument();
  });
});
