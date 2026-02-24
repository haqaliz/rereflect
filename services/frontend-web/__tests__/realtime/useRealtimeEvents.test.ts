import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import React, { ReactNode } from 'react';

// ─── Mock WebSocket ────────────────────────────────────────────────────────────

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState = MockWebSocket.CONNECTING;
  onopen: ((e: Event) => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;

  constructor(public url: string) {
    wsInstances.push(this);
  }

  send(_data: string) {}

  close(code = 1000) {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code, reason: 'closed' } as CloseEvent);
  }

  simulateOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.({} as Event);
  }

  simulateMessage(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }

  simulateClose(code = 1006) {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code, reason: 'disconnected' } as CloseEvent);
  }
}

let wsInstances: MockWebSocket[] = [];

vi.stubGlobal('WebSocket', MockWebSocket);

// ─── Mock localStorage ─────────────────────────────────────────────────────────

const mockStorage: Record<string, string> = {};

vi.stubGlobal('localStorage', {
  getItem: vi.fn((key: string) => mockStorage[key] ?? null),
  setItem: vi.fn((key: string, val: string) => { mockStorage[key] = val; }),
  removeItem: vi.fn((key: string) => { delete mockStorage[key]; }),
});

// ─── Imports (after mocks) ────────────────────────────────────────────────────

import { RealtimeProvider } from '@/contexts/RealtimeContext';
import { useRealtimeEvents } from '@/hooks/useRealtimeEvents';

// ─── Helper wrapper ───────────────────────────────────────────────────────────

function wrapper({ children }: { children: ReactNode }) {
  return React.createElement(RealtimeProvider, null, children);
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('useRealtimeEvents', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    wsInstances = [];
    vi.useFakeTimers();
    mockStorage['access_token'] = 'test-jwt-token';
    vi.stubGlobal('process', {
      ...process,
      env: { ...process.env, NEXT_PUBLIC_API_URL: 'http://localhost:8000' },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.stubGlobal('WebSocket', MockWebSocket);
    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => mockStorage[key] ?? null),
      setItem: vi.fn((key: string, val: string) => { mockStorage[key] = val; }),
      removeItem: vi.fn((key: string) => { delete mockStorage[key]; }),
    });
  });

  // 14. test_hook_subscribes_on_mount
  it('test_hook_subscribes_on_mount — rendering component with useRealtimeEvents subscribes to pattern', () => {
    const handler = vi.fn();
    renderHook(() => useRealtimeEvents('feedback:*', handler), { wrapper });
    act(() => {
      wsInstances[0]?.simulateOpen();
    });
    act(() => {
      wsInstances[0]?.simulateMessage({ type: 'event', event_type: 'feedback:created', data: { id: 1 } });
    });
    expect(handler).toHaveBeenCalledWith({ id: 1 });
  });

  // 15. test_hook_unsubscribes_on_unmount
  it('test_hook_unsubscribes_on_unmount — unmounting component calls unsubscribe', () => {
    const handler = vi.fn();
    const { unmount } = renderHook(() => useRealtimeEvents('feedback:*', handler), { wrapper });
    act(() => {
      wsInstances[0]?.simulateOpen();
    });

    // Verify it works before unmount
    act(() => {
      wsInstances[0]?.simulateMessage({ type: 'event', event_type: 'feedback:created', data: { id: 1 } });
    });
    expect(handler).toHaveBeenCalledTimes(1);

    // Unmount and verify no more calls
    unmount();
    act(() => {
      wsInstances[0]?.simulateMessage({ type: 'event', event_type: 'feedback:created', data: { id: 2 } });
    });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  // 16. test_hook_calls_handler_on_matching_event
  it('test_hook_calls_handler_on_matching_event — push event → handler called with event data', () => {
    const handler = vi.fn();
    renderHook(() => useRealtimeEvents('feedback:created', handler), { wrapper });
    act(() => { wsInstances[0]?.simulateOpen(); });
    act(() => {
      wsInstances[0]?.simulateMessage({ type: 'event', event_type: 'feedback:created', data: { id: 42, text: 'hello' } });
    });
    expect(handler).toHaveBeenCalledWith({ id: 42, text: 'hello' });
  });

  // 17. test_hook_returns_connection_status
  it('test_hook_returns_connection_status — { connected, reconnecting } returned from hook', () => {
    const { result } = renderHook(() => useRealtimeEvents('feedback:*', vi.fn()), { wrapper });
    expect(result.current).toHaveProperty('connected');
    expect(result.current).toHaveProperty('reconnecting');
    expect(result.current.connected).toBe(false);
    expect(result.current.reconnecting).toBe(false);

    act(() => { wsInstances[0]?.simulateOpen(); });
    expect(result.current.connected).toBe(true);
  });

  // 18. test_handler_ref_stays_current
  it('test_handler_ref_stays_current — if handler prop changes, latest handler is called (no stale closure)', () => {
    const handler1 = vi.fn();
    const handler2 = vi.fn();

    let currentHandler = handler1;
    const { rerender } = renderHook(
      () => useRealtimeEvents('feedback:created', currentHandler),
      { wrapper }
    );

    act(() => { wsInstances[0]?.simulateOpen(); });

    // Fire with handler1
    act(() => {
      wsInstances[0]?.simulateMessage({ type: 'event', event_type: 'feedback:created', data: { n: 1 } });
    });
    expect(handler1).toHaveBeenCalledTimes(1);
    expect(handler2).not.toHaveBeenCalled();

    // Change to handler2 and rerender
    currentHandler = handler2;
    rerender();

    // Fire again — should call handler2, not handler1
    act(() => {
      wsInstances[0]?.simulateMessage({ type: 'event', event_type: 'feedback:created', data: { n: 2 } });
    });
    expect(handler1).toHaveBeenCalledTimes(1); // not called again
    expect(handler2).toHaveBeenCalledTimes(1);
    expect(handler2).toHaveBeenCalledWith({ n: 2 });
  });
});
