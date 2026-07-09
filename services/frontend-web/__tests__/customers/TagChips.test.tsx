import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TagChips } from '../../components/customers/TagChips';

describe('TagChips', () => {
  it('renders a placeholder when there are no tags', () => {
    render(<TagChips tags={[]} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('renders a placeholder when tags is null', () => {
    render(<TagChips tags={null} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('renders a placeholder when tags is undefined', () => {
    render(<TagChips tags={undefined} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('renders each tag as a chip', () => {
    render(<TagChips tags={['vip', 'at-risk-q3']} />);
    expect(screen.getByText('vip')).toBeInTheDocument();
    expect(screen.getByText('at-risk-q3')).toBeInTheDocument();
  });

  it('collapses tags beyond maxVisible into a "+N" indicator', () => {
    render(<TagChips tags={['a', 'b', 'c', 'd', 'e']} maxVisible={3} />);
    expect(screen.getByText('a')).toBeInTheDocument();
    expect(screen.getByText('b')).toBeInTheDocument();
    expect(screen.getByText('c')).toBeInTheDocument();
    expect(screen.queryByText('d')).not.toBeInTheDocument();
    expect(screen.getByText('+2')).toBeInTheDocument();
  });
});
