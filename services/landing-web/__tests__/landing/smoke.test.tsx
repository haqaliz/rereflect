import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

describe('Vitest setup smoke test', () => {
  it('renders a simple component', () => {
    render(<div data-testid="smoke">Hello</div>);
    expect(screen.getByTestId('smoke')).toHaveTextContent('Hello');
  });
});
