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

  it('renders all 8 FAQ questions as visible text', () => {
    render(<FAQ />);
    expect(screen.getByText('How accurate is the AI analysis?')).toBeInTheDocument();
    expect(screen.getByText('Is my data secure?')).toBeInTheDocument();
    expect(screen.getByText('Can I use my own AI provider?')).toBeInTheDocument();
    expect(screen.getByText('How long does setup take?')).toBeInTheDocument();
    expect(screen.getByText("What happens when I hit my plan's feedback limit?")).toBeInTheDocument();
    expect(screen.getByText('Can I cancel anytime?')).toBeInTheDocument();
    expect(screen.getByText('Do you offer a free trial?')).toBeInTheDocument();
    expect(screen.getByText('What integrations do you support?')).toBeInTheDocument();
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

  // Content verification (spot check 3)
  it('question "How accurate is the AI analysis?" has answer mentioning "85-95%"', async () => {
    const user = userEvent.setup();
    render(<FAQ />);
    const question = screen.getByText('How accurate is the AI analysis?').closest('button')!;
    await user.click(question);
    // After opening, the answer should contain 85-95%
    expect(screen.getByTestId('faq-answer-0')).toHaveTextContent('85-95%');
  });

  it('question "Is my data secure?" has answer mentioning "SOC 2"', async () => {
    const user = userEvent.setup();
    render(<FAQ />);
    const question = screen.getByText('Is my data secure?').closest('button')!;
    await user.click(question);
    expect(screen.getByTestId('faq-answer-1')).toHaveTextContent('SOC 2');
  });

  it('question "Do you offer a free trial?" has answer mentioning "14-day"', async () => {
    const user = userEvent.setup();
    render(<FAQ />);
    const question = screen.getByText('Do you offer a free trial?').closest('button')!;
    await user.click(question);
    expect(screen.getByTestId('faq-answer-6')).toHaveTextContent('14-day');
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
