import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

import FAQ from '@/components/landing/FAQ';

describe('FAQ', () => {
  // Structure
  it('renders heading "Frequently Asked Questions"', () => {
    render(<FAQ />);
    expect(screen.getByRole('heading', { name: /Frequently Asked Questions/i })).toBeInTheDocument();
  });

  it('renders all 10 FAQ questions as visible text', () => {
    render(<FAQ />);
    expect(screen.getByText('Is it really free?')).toBeInTheDocument();
    expect(screen.getByText('How do I self-host it?')).toBeInTheDocument();
    expect(screen.getByText('Do I need an LLM API key?')).toBeInTheDocument();
    expect(screen.getByText('Can I use it without sending any data to an external LLM?')).toBeInTheDocument();
    expect(screen.getByText('What is the license?')).toBeInTheDocument();
    expect(screen.getByText('What integrations are included?')).toBeInTheDocument();
    expect(screen.getByText('Who owns my data?')).toBeInTheDocument();
    expect(screen.getByText('Can I contribute or request features?')).toBeInTheDocument();
    expect(screen.getByText('How does churn prediction work without sending data to a hosted service?')).toBeInTheDocument();
    expect(screen.getByText('Can I automate actions based on feedback events?')).toBeInTheDocument();
  });

  // Expand/collapse behavior
  it('answers are initially hidden', () => {
    render(<FAQ />);
    // All answer containers should be hidden initially
    const answers = document.querySelectorAll('[data-testid^="faq-answer-"]');
    answers.forEach((answer) => {
      // Either hidden attribute, or data-state="closed", or not in DOM
      const isHidden =
        answer.hasAttribute('hidden') ||
        answer.getAttribute('data-state') === 'closed' ||
        (answer as HTMLElement).style.display === 'none';
      expect(isHidden).toBe(true);
    });
  });

  it('clicking a question shows its answer', async () => {
    const user = userEvent.setup();
    render(<FAQ />);
    const firstQuestion = screen.getByTestId('faq-question-0');
    await user.click(firstQuestion);
    const firstAnswer = screen.getByTestId('faq-answer-0');
    const isVisible =
      !firstAnswer.hasAttribute('hidden') &&
      firstAnswer.getAttribute('data-state') !== 'closed' &&
      (firstAnswer as HTMLElement).style.display !== 'none';
    expect(isVisible).toBe(true);
  });

  it('clicking an expanded question hides its answer', async () => {
    const user = userEvent.setup();
    render(<FAQ />);
    const firstQuestion = screen.getByTestId('faq-question-0');
    // open
    await user.click(firstQuestion);
    // close
    await user.click(firstQuestion);
    const firstAnswer = screen.getByTestId('faq-answer-0');
    const isHidden =
      firstAnswer.hasAttribute('hidden') ||
      firstAnswer.getAttribute('data-state') === 'closed' ||
      (firstAnswer as HTMLElement).style.display === 'none';
    expect(isHidden).toBe(true);
  });

  it('only the clicked question expands (others stay collapsed)', async () => {
    const user = userEvent.setup();
    render(<FAQ />);
    const secondQuestion = screen.getByTestId('faq-question-1');
    await user.click(secondQuestion);

    // answer-1 should be open
    const answer1 = screen.getByTestId('faq-answer-1');
    const isOpen =
      !answer1.hasAttribute('hidden') &&
      answer1.getAttribute('data-state') !== 'closed' &&
      (answer1 as HTMLElement).style.display !== 'none';
    expect(isOpen).toBe(true);

    // answer-0 should still be closed
    const answer0 = screen.getByTestId('faq-answer-0');
    const isClosed =
      answer0.hasAttribute('hidden') ||
      answer0.getAttribute('data-state') === 'closed' ||
      (answer0 as HTMLElement).style.display === 'none';
    expect(isClosed).toBe(true);
  });

  // Content verification (spot check 3 OSS answers)
  it('question "Is it really free?" has answer mentioning "MIT"', async () => {
    const user = userEvent.setup();
    render(<FAQ />);
    const question = screen.getByText('Is it really free?').closest('button')!;
    await user.click(question);
    expect(screen.getByTestId('faq-answer-0')).toHaveTextContent('MIT');
  });

  it('question "Who owns my data?" has answer mentioning "your infrastructure"', async () => {
    const user = userEvent.setup();
    render(<FAQ />);
    const question = screen.getByText('Who owns my data?').closest('button')!;
    await user.click(question);
    expect(screen.getByTestId('faq-answer-6')).toHaveTextContent('your infrastructure');
  });

  it('question "What is the license?" has answer mentioning "MIT"', async () => {
    const user = userEvent.setup();
    render(<FAQ />);
    const question = screen.getByText('What is the license?').closest('button')!;
    await user.click(question);
    expect(screen.getByTestId('faq-answer-4')).toHaveTextContent('MIT');
  });

  // Accessibility
  it('each question button has aria-expanded attribute', () => {
    render(<FAQ />);
    const buttons = document.querySelectorAll('[data-testid^="faq-question-"]');
    buttons.forEach((btn) => {
      expect(btn).toHaveAttribute('aria-expanded');
    });
  });

  it('aria-expanded is "false" when collapsed', () => {
    render(<FAQ />);
    const buttons = document.querySelectorAll('[data-testid^="faq-question-"]');
    buttons.forEach((btn) => {
      expect(btn).toHaveAttribute('aria-expanded', 'false');
    });
  });

  it('aria-expanded is "true" when expanded', async () => {
    const user = userEvent.setup();
    render(<FAQ />);
    const firstQuestion = screen.getByTestId('faq-question-0');
    await user.click(firstQuestion);
    expect(firstQuestion).toHaveAttribute('aria-expanded', 'true');
  });

  it('answers have proper id matching aria-controls', () => {
    render(<FAQ />);
    const buttons = document.querySelectorAll('[data-testid^="faq-question-"]');
    buttons.forEach((btn, i) => {
      expect(btn).toHaveAttribute('aria-controls', `faq-answer-${i}`);
      const answerId = document.getElementById(`faq-answer-${i}`);
      expect(answerId).toBeInTheDocument();
    });
  });

  it('renders data-testid="faq-section" on the section element', () => {
    render(<FAQ />);
    expect(screen.getByTestId('faq-section')).toBeInTheDocument();
  });
});
