// This test pairs with the backend's golden-fixture test
// (services/backend-api/tests/ — see copilot_actions_item.json and the test
// that reads it). The backend test asserts "this is what I emit" — the shape
// of the actions envelope. This file asserts the frontend half of the same
// contract: "given this fixture, I render N buttons." Neither test alone
// would catch a seam between the two ends (a renamed data_type, a renamed
// field) — only running both against the same fixture does.
//
// The render-N-buttons test below is written as `it.fails(...)` because
// MessageBubble does not implement the "actions" data_type yet — it only
// branches on 'table' and 'chart' (MessageBubble.tsx). It is expected to
// start failing loudly (i.e. `it.fails` itself reports a failure) the moment
// the frontend-actions-ui aspect lands; that failure is the signal to flip
// this back to a normal `it`.
//
// Note on `it.fails`: it accepts ANY throw from the test body, including a
// render() crash unrelated to actions rendering at all — a weaker signal
// than a named assertion failure under a normal `it`. Accepted for now; flip
// to `it` (per the acceptance criteria in frontend-actions-ui/spec.md) rather
// than trying to make the negative case more precise while it's still red.

import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import React from 'react';

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { MessageBubble } from '@/components/copilot/MessageBubble';
import type { ChatMessage } from '@/components/copilot/ChatArea';

// __tests__/copilot/ -> frontend-web/ -> services/
const FIXTURE = path.resolve(
  __dirname, '../../../backend-api/tests/fixtures/copilot_actions_item.json',
);
// Mirrors the backend loader's posture: a missing fixture throws rather than
// being skipped — fs.readFileSync already throws, so this is deliberately
// left unguarded (no try/catch).
const goldenActionsItem = JSON.parse(fs.readFileSync(FIXTURE, 'utf-8'));

describe('copilot actions contract (frontend)', () => {
  it.fails('renders one button per action from the golden actions item', () => {
    // F4: the golden fixture has exactly one action, which makes "one button
    // per action" vacuous — a renderer emitting one button per *item* (not
    // per action) would also pass against a single-action fixture. Duplicate
    // the action locally so the assertion actually distinguishes the two.
    // The SHARED fixture (copilot_actions_item.json) stays single-action on
    // purpose: the backend's contract test asserts an exact match against
    // it, and a second action there would break that test.
    const actions = [
      goldenActionsItem.data.actions[0],
      { ...goldenActionsItem.data.actions[0], action: 'tag_customers_2' },
    ];
    const twoActionItem = {
      ...goldenActionsItem,
      data: { ...goldenActionsItem.data, actions },
    };

    const message: ChatMessage = {
      id: 'golden-actions',
      role: 'assistant',
      content: 'Here is what I found:',
      // New-pipeline format: structured_data is an array of {data_type, data}
      // items. Wrap the fixture the same way the real pipeline would.
      structured_data: [twoActionItem] as unknown as ChatMessage['structured_data'],
      created_at: new Date().toISOString(),
    };

    render(<MessageBubble message={message} />);

    const label = actions[0].label as string;
    const actionButtons = screen.getAllByRole('button', { name: label });
    expect(actionButtons).toHaveLength(actions.length);
  });

  it('renders nothing and does not throw for an unrecognised data_type', () => {
    // Pins MessageBubble's silent skip as DELIBERATE. If someone renames the
    // "actions" data_type, the fixture test above fails loudly instead of
    // this feature silently rendering nothing in production.
    const baseline: ChatMessage = {
      id: 'no-structured-data',
      role: 'assistant',
      content: 'Nothing to see',
      structured_data: null,
      created_at: new Date().toISOString(),
    };
    const withUnrecognisedType: ChatMessage = {
      ...baseline,
      id: 'unrecognised-data-type',
      structured_data: [{ data_type: 'some_future_type', data: {} }] as unknown as ChatMessage['structured_data'],
    };

    let baselineContainer!: HTMLElement;
    let testContainer!: HTMLElement;

    expect(() => {
      ({ container: baselineContainer } = render(<MessageBubble message={baseline} />));
    }).not.toThrow();

    expect(() => {
      ({ container: testContainer } = render(<MessageBubble message={withUnrecognisedType} />));
    }).not.toThrow();

    // Same button count as a message with no structured_data at all — proves
    // the unrecognised data_type added nothing (no action button, no error
    // fallback UI), rather than hardcoding a button count that would rot if
    // MessageActions grows another always-on button.
    const baselineButtons = within(baselineContainer).getAllByRole('button');
    const testButtons = within(testContainer).getAllByRole('button');
    expect(testButtons).toHaveLength(baselineButtons.length);
  });
});
