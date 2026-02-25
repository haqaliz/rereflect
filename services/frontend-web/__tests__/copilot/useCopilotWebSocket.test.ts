import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

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

  sentMessages: string[] = [];

  constructor(public url: string) {
    instances.push(this);
  }

  send(data: string) {
    this.sentMessages.push(data);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code: 1000, reason: 'closed' } as CloseEvent);
  }

  // Test helpers
  open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.({} as Event);
  }

  receive(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }

  disconnect(code = 1006) {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code, reason: 'disconnected' } as CloseEvent);
  }
}

let instances: MockWebSocket[] = [];

vi.stubGlobal('WebSocket', MockWebSocket);

// ─── Mock AuthContext ──────────────────────────────────────────────────────────

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// ─── Mock timers ──────────────────────────────────────────────────────────────

import { useCopilotWebSocket } from '@/hooks/useCopilotWebSocket';

describe('useCopilotWebSocket', () => {
  const mockLocalStorage: Record<string, string> = {};

  beforeEach(() => {
    vi.clearAllMocks();
    instances = [];
    vi.useFakeTimers();
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      user: { id: 1, role: 'admin' },
    });
    // Mock localStorage with token
    mockLocalStorage['access_token'] = 'test-jwt-token';
    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => mockLocalStorage[key] ?? null),
      setItem: vi.fn((key: string, val: string) => { mockLocalStorage[key] = val; }),
      removeItem: vi.fn((key: string) => { delete mockLocalStorage[key]; }),
    });
    // Mock NEXT_PUBLIC_API_URL
    vi.stubGlobal('process', {
      ...process,
      env: { ...process.env, NEXT_PUBLIC_API_URL: 'http://localhost:8000' },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.stubGlobal('WebSocket', MockWebSocket); // re-stub WebSocket after unstub
  });

  // ── Connection ──────────────────────────────────────────────────────────────

  describe('Connection', () => {
    it('connects with correct WebSocket URL including jwt token', () => {
      renderHook(() => useCopilotWebSocket());
      expect(instances.length).toBe(1);
      expect(instances[0].url).toContain('token=test-jwt-token');
      expect(instances[0].url).toContain('/ws/copilot');
    });

    it('starts with connected=false before open', () => {
      const { result } = renderHook(() => useCopilotWebSocket());
      expect(result.current.connected).toBe(false);
    });

    it('sets connected=true when WebSocket opens', () => {
      const { result } = renderHook(() => useCopilotWebSocket());
      act(() => {
        instances[0].open();
      });
      expect(result.current.connected).toBe(true);
    });

    it('sets connected=false when WebSocket closes', () => {
      const { result } = renderHook(() => useCopilotWebSocket());
      act(() => {
        instances[0].open();
      });
      act(() => {
        instances[0].disconnect();
      });
      expect(result.current.connected).toBe(false);
    });
  });

  // ── sendQuery ───────────────────────────────────────────────────────────────

  describe('sendQuery', () => {
    it('sends a query message over the WebSocket', () => {
      const { result } = renderHook(() => useCopilotWebSocket());
      act(() => { instances[0].open(); });
      act(() => {
        result.current.sendQuery('test-uuid-42', 'How many feedbacks today?', 'all_data');
      });
      const sent = JSON.parse(instances[0].sentMessages[0]);
      expect(sent.type).toBe('query');
      expect(sent.conversation_id).toBe('test-uuid-42');
      expect(sent.content).toBe('How many feedbacks today?');
      expect(sent.context_scope).toBe('all_data');
    });

    it('does not send if WebSocket is not open', () => {
      const { result } = renderHook(() => useCopilotWebSocket());
      // Don't call .open() — ws is still CONNECTING
      act(() => {
        result.current.sendQuery('test-uuid-1', 'test', 'all_data');
      });
      expect(instances[0].sentMessages.length).toBe(0);
    });
  });

  // ── stopGeneration ──────────────────────────────────────────────────────────

  describe('stopGeneration', () => {
    it('sends a stop message with the messageId', () => {
      const { result } = renderHook(() => useCopilotWebSocket());
      act(() => { instances[0].open(); });
      act(() => {
        result.current.stopGeneration(99);
      });
      const sent = JSON.parse(instances[0].sentMessages[0]);
      expect(sent.type).toBe('stop');
      expect(sent.message_id).toBe(99);
    });
  });

  // ── regenerate ──────────────────────────────────────────────────────────────

  describe('regenerate', () => {
    it('sends a regenerate message with the messageId', () => {
      const { result } = renderHook(() => useCopilotWebSocket());
      act(() => { instances[0].open(); });
      act(() => {
        result.current.regenerate(77);
      });
      const sent = JSON.parse(instances[0].sentMessages[0]);
      expect(sent.type).toBe('regenerate');
      expect(sent.message_id).toBe(77);
    });
  });

  // ── Server message handling ─────────────────────────────────────────────────

  describe('Server message handling', () => {
    it('updates status text on status message', () => {
      const { result } = renderHook(() => useCopilotWebSocket());
      act(() => { instances[0].open(); });
      act(() => {
        instances[0].receive({ type: 'status', message_id: 'abc', status: 'processing' });
      });
      expect(result.current.statusText).toBe('processing');
    });

    it('sets streaming=true on first stream delta', () => {
      const { result } = renderHook(() => useCopilotWebSocket());
      act(() => { instances[0].open(); });
      act(() => {
        instances[0].receive({ type: 'stream', message_id: 'abc', delta: 'Hello', done: false });
      });
      expect(result.current.streaming).toBe(true);
    });

    it('accumulates stream deltas into streamingContent', () => {
      const { result } = renderHook(() => useCopilotWebSocket());
      act(() => { instances[0].open(); });
      act(() => {
        instances[0].receive({ type: 'stream', message_id: 'abc', delta: 'Hello', done: false });
        instances[0].receive({ type: 'stream', message_id: 'abc', delta: ' world', done: false });
        instances[0].receive({ type: 'stream', message_id: 'abc', delta: '!', done: false });
      });
      expect(result.current.streamingContent).toBe('Hello world!');
    });

    it('sets streaming=false and clears streamingContent on stream done', () => {
      const onMessage = vi.fn();
      const { result } = renderHook(() => useCopilotWebSocket({ onMessage }));
      act(() => { instances[0].open(); });
      act(() => {
        instances[0].receive({ type: 'stream', message_id: 'abc', delta: 'Hello', done: false });
        instances[0].receive({ type: 'stream', message_id: 'abc', delta: '', done: true, metadata: {} });
      });
      expect(result.current.streaming).toBe(false);
      expect(result.current.streamingContent).toBe('');
    });

    it('calls onMessage with completed message (buffered content) on stream done', () => {
      const onMessage = vi.fn();
      const { result: _ } = renderHook(() => useCopilotWebSocket({ onMessage }));
      act(() => { instances[0].open(); });
      act(() => {
        instances[0].receive({ type: 'stream', message_id: 'abc', delta: 'Result text', done: false });
        instances[0].receive({ type: 'stream', message_id: 'abc', delta: '', done: true, metadata: {} });
      });
      expect(onMessage).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'assistant_message', message_id: 'abc', content: 'Result text' })
      );
    });

    it('calls onMessage with structured_data on structured_data event', () => {
      const onMessage = vi.fn();
      const { result: _ } = renderHook(() => useCopilotWebSocket({ onMessage }));
      act(() => { instances[0].open(); });
      act(() => {
        instances[0].receive({
          type: 'structured_data',
          data: { kind: 'table', columns: ['a'], rows: [[1]] },
          message_id: 'def',
        });
      });
      expect(onMessage).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'structured_data', data: { kind: 'table', columns: ['a'], rows: [[1]] } })
      );
    });

    it('sets error on error message', () => {
      const { result } = renderHook(() => useCopilotWebSocket());
      act(() => { instances[0].open(); });
      act(() => {
        instances[0].receive({ type: 'error', message_id: 'abc', error: 'Query failed', suggestions: [] });
      });
      expect(result.current.error).toBe('Query failed');
    });

    it('ignores ping messages', () => {
      const { result } = renderHook(() => useCopilotWebSocket());
      act(() => { instances[0].open(); });
      act(() => {
        instances[0].receive({ type: 'ping' });
      });
      // No error, no state change
      expect(result.current.error).toBeNull();
      expect(result.current.streaming).toBe(false);
    });
  });

  // ── Reconnect ───────────────────────────────────────────────────────────────

  describe('Reconnect', () => {
    it('shows reconnecting=true on unexpected disconnect', () => {
      const { result } = renderHook(() => useCopilotWebSocket());
      act(() => { instances[0].open(); });
      act(() => {
        instances[0].disconnect(1006); // abnormal closure
      });
      expect(result.current.reconnecting).toBe(true);
    });

    it('attempts reconnect after 1s on first disconnect', () => {
      renderHook(() => useCopilotWebSocket());
      act(() => { instances[0].open(); });
      act(() => { instances[0].disconnect(1006); });
      expect(instances.length).toBe(1); // not yet reconnected
      act(() => { vi.advanceTimersByTime(1000); });
      expect(instances.length).toBe(2); // new ws created
    });

    it('doubles backoff on second disconnect', () => {
      renderHook(() => useCopilotWebSocket());
      act(() => { instances[0].open(); });
      act(() => { instances[0].disconnect(1006); });
      act(() => { vi.advanceTimersByTime(1000); });
      // Second disconnect
      act(() => { instances[1].disconnect(1006); });
      act(() => { vi.advanceTimersByTime(1000); });
      expect(instances.length).toBe(2); // NOT reconnected yet
      act(() => { vi.advanceTimersByTime(1000); });
      expect(instances.length).toBe(3); // reconnected at 2s
    });

    it('does not reconnect on normal close (code 1000)', () => {
      renderHook(() => useCopilotWebSocket());
      act(() => { instances[0].open(); });
      act(() => { instances[0].disconnect(1000); });
      act(() => { vi.advanceTimersByTime(5000); });
      expect(instances.length).toBe(1); // no reconnect
    });

    it('clears reconnecting=false when reconnect succeeds', () => {
      const { result } = renderHook(() => useCopilotWebSocket());
      act(() => { instances[0].open(); });
      act(() => { instances[0].disconnect(1006); });
      expect(result.current.reconnecting).toBe(true);
      act(() => { vi.advanceTimersByTime(1000); });
      act(() => { instances[1].open(); });
      expect(result.current.reconnecting).toBe(false);
    });
  });
});
