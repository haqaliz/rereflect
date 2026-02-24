import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { renderHook } from '@testing-library/react';
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

  // Test helpers
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

import { RealtimeProvider, useRealtime } from '@/contexts/RealtimeContext';

// ─── Helper ───────────────────────────────────────────────────────────────────

function wrapper({ children }: { children: ReactNode }) {
  return <RealtimeProvider>{children}</RealtimeProvider>;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('RealtimeContext', () => {
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

  // 1. test_provider_renders_children
  it('test_provider_renders_children — RealtimeProvider wraps children, they render', () => {
    render(
      <RealtimeProvider>
        <div data-testid="child">hello</div>
      </RealtimeProvider>
    );
    expect(screen.getByTestId('child')).toBeTruthy();
  });

  // 2. test_connected_state_false_initially
  it('test_connected_state_false_initially — before WS connects, connected=false', () => {
    const { result } = renderHook(() => useRealtime(), { wrapper });
    expect(result.current.connected).toBe(false);
  });

  // 3. test_connected_state_true_after_ws_open
  it('test_connected_state_true_after_ws_open — after WS.onopen fires, connected=true', () => {
    const { result } = renderHook(() => useRealtime(), { wrapper });
    act(() => {
      wsInstances[0].simulateOpen();
    });
    expect(result.current.connected).toBe(true);
  });

  // 4. test_reconnecting_state_on_abnormal_close
  it('test_reconnecting_state_on_abnormal_close — WS closes abnormally → reconnecting=true', () => {
    const { result } = renderHook(() => useRealtime(), { wrapper });
    act(() => { wsInstances[0].simulateOpen(); });
    act(() => { wsInstances[0].simulateClose(1006); });
    expect(result.current.reconnecting).toBe(true);
  });

  // 5. test_exponential_backoff_reconnection
  it('test_exponential_backoff_reconnection — reconnect delays: 1s, 2s, 4s on consecutive failures', () => {
    renderHook(() => useRealtime(), { wrapper });
    act(() => { wsInstances[0].simulateOpen(); });

    // 1st disconnect (attempt 0) → reconnect after 1s
    act(() => { wsInstances[0].simulateClose(1006); });
    expect(wsInstances.length).toBe(1);
    act(() => { vi.advanceTimersByTime(1000); });
    expect(wsInstances.length).toBe(2);

    // 2nd disconnect without open (attempt 1) → reconnect after 2s
    act(() => { wsInstances[1].simulateClose(1006); });
    act(() => { vi.advanceTimersByTime(1000); });
    expect(wsInstances.length).toBe(2); // not yet at 1s
    act(() => { vi.advanceTimersByTime(1000); });
    expect(wsInstances.length).toBe(3);

    // 3rd disconnect without open (attempt 2) → reconnect after 4s
    act(() => { wsInstances[2].simulateClose(1006); });
    act(() => { vi.advanceTimersByTime(3000); });
    expect(wsInstances.length).toBe(3); // not yet at 3s
    act(() => { vi.advanceTimersByTime(1000); });
    expect(wsInstances.length).toBe(4);
  });

  // 6. test_subscribe_returns_unsubscribe_function
  it('test_subscribe_returns_unsubscribe_function — subscribe() returns a function', () => {
    const { result } = renderHook(() => useRealtime(), { wrapper });
    let unsubscribe: unknown;
    act(() => {
      unsubscribe = result.current.subscribe('feedback:created', vi.fn());
    });
    expect(typeof unsubscribe).toBe('function');
  });

  // 7. test_event_dispatched_to_matching_subscriber
  it('test_event_dispatched_to_matching_subscriber — WS receives event "feedback:created" → subscriber called', () => {
    const { result } = renderHook(() => useRealtime(), { wrapper });
    const handler = vi.fn();
    act(() => {
      wsInstances[0].simulateOpen();
      result.current.subscribe('feedback:created', handler);
    });
    act(() => {
      wsInstances[0].simulateMessage({ type: 'event', event_type: 'feedback:created', data: { id: 1 } });
    });
    expect(handler).toHaveBeenCalledWith({ id: 1 });
  });

  // 8. test_wildcard_pattern_matches
  it('test_wildcard_pattern_matches — subscriber for "feedback:*" receives "feedback:created", "feedback:deleted"', () => {
    const { result } = renderHook(() => useRealtime(), { wrapper });
    const handler = vi.fn();
    act(() => {
      wsInstances[0].simulateOpen();
      result.current.subscribe('feedback:*', handler);
    });
    act(() => {
      wsInstances[0].simulateMessage({ type: 'event', event_type: 'feedback:created', data: { id: 1 } });
      wsInstances[0].simulateMessage({ type: 'event', event_type: 'feedback:deleted', data: { id: 2 } });
    });
    expect(handler).toHaveBeenCalledTimes(2);
    expect(handler).toHaveBeenNthCalledWith(1, { id: 1 });
    expect(handler).toHaveBeenNthCalledWith(2, { id: 2 });
  });

  // 9. test_non_matching_subscriber_not_called
  it('test_non_matching_subscriber_not_called — subscriber for "workflow:*" does NOT receive "feedback:created"', () => {
    const { result } = renderHook(() => useRealtime(), { wrapper });
    const handler = vi.fn();
    act(() => {
      wsInstances[0].simulateOpen();
      result.current.subscribe('workflow:*', handler);
    });
    act(() => {
      wsInstances[0].simulateMessage({ type: 'event', event_type: 'feedback:created', data: { id: 1 } });
    });
    expect(handler).not.toHaveBeenCalled();
  });

  // 10. test_unsubscribe_stops_events
  it('test_unsubscribe_stops_events — after calling unsubscribe(), handler no longer called', () => {
    const { result } = renderHook(() => useRealtime(), { wrapper });
    const handler = vi.fn();
    let unsubscribe: (() => void) | undefined;
    act(() => {
      wsInstances[0].simulateOpen();
      unsubscribe = result.current.subscribe('feedback:created', handler);
    });
    act(() => {
      wsInstances[0].simulateMessage({ type: 'event', event_type: 'feedback:created', data: { id: 1 } });
    });
    expect(handler).toHaveBeenCalledTimes(1);

    act(() => { unsubscribe?.(); });
    act(() => {
      wsInstances[0].simulateMessage({ type: 'event', event_type: 'feedback:created', data: { id: 2 } });
    });
    expect(handler).toHaveBeenCalledTimes(1); // no new calls
  });

  // 11. test_multiple_subscribers_same_pattern
  it('test_multiple_subscribers_same_pattern — 2 subscribers for "feedback:*" → both receive events', () => {
    const { result } = renderHook(() => useRealtime(), { wrapper });
    const handler1 = vi.fn();
    const handler2 = vi.fn();
    act(() => {
      wsInstances[0].simulateOpen();
      result.current.subscribe('feedback:*', handler1);
      result.current.subscribe('feedback:*', handler2);
    });
    act(() => {
      wsInstances[0].simulateMessage({ type: 'event', event_type: 'feedback:created', data: { id: 1 } });
    });
    expect(handler1).toHaveBeenCalledWith({ id: 1 });
    expect(handler2).toHaveBeenCalledWith({ id: 1 });
  });

  // 12. test_ws_not_created_when_unauthenticated
  it('test_ws_not_created_when_unauthenticated — if no access_token in localStorage, no WS connection attempted', () => {
    delete mockStorage['access_token'];
    vi.stubGlobal('localStorage', {
      getItem: vi.fn((_key: string) => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    });

    renderHook(() => useRealtime(), { wrapper });
    expect(wsInstances.length).toBe(0);
  });

  // 13. test_ping_messages_ignored
  it('test_ping_messages_ignored — WS receives {type: "ping"} → no subscriber called', () => {
    const { result } = renderHook(() => useRealtime(), { wrapper });
    const handler = vi.fn();
    act(() => {
      wsInstances[0].simulateOpen();
      result.current.subscribe('ping', handler);
      result.current.subscribe('*', handler);
    });
    act(() => {
      wsInstances[0].simulateMessage({ type: 'ping' });
    });
    expect(handler).not.toHaveBeenCalled();
  });
});
