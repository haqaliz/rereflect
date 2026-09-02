import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';

import { TeamsIcon } from '@/components/icons/TeamsIcon';

describe('TeamsIcon', () => {
  it('renders an svg with the Teams brand color #6264A7', () => {
    const { container } = render(<TeamsIcon />);

    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();

    const path = svg?.querySelector('path');
    expect(path).toHaveAttribute('fill', '#6264A7');
  });

  it('passes className through to the svg', () => {
    const { container } = render(<TeamsIcon className="w-6 h-6" />);

    expect(container.querySelector('svg')).toHaveClass('w-6 h-6');
  });
});