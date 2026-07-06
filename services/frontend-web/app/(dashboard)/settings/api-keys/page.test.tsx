import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SCOPE_DESCRIPTIONS, ScopeBadge } from './page';

describe('API key scopes', () => {
  it('has a non-empty description for every scope, including write', () => {
    expect(SCOPE_DESCRIPTIONS.read).toBeTruthy();
    expect(SCOPE_DESCRIPTIONS.ingest).toBeTruthy();
    expect(SCOPE_DESCRIPTIONS.write).toBeTruthy();
  });

  it('gives write its own description, distinct from ingest', () => {
    expect(SCOPE_DESCRIPTIONS.write).not.toEqual(SCOPE_DESCRIPTIONS.ingest);
  });

  it('renders a non-default (non-gray) badge class for the write scope', () => {
    render(<ScopeBadge scope="write" />);
    const badge = screen.getByText('write');
    expect(badge.className).not.toMatch(/bg-gray-100/);
    expect(badge.className).toMatch(/purple/);
  });

  it('still renders read and ingest badges with their existing colors', () => {
    render(<ScopeBadge scope="read" />);
    expect(screen.getByText('read').className).toMatch(/blue/);

    render(<ScopeBadge scope="ingest" />);
    expect(screen.getByText('ingest').className).toMatch(/green/);
  });
});
