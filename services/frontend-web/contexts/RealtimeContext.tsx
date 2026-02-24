'use client';

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useRef,
  useCallback,
  ReactNode,
} from 'react';

// ─── Types ────────────────────────────────────────────────────────────────────

export type EventHandler = (data: unknown) => void;

export interface RealtimeContextType {
  connected: boolean;
  reconnecting: boolean;
  subscribe: (pattern: string, handler: EventHandler) => () => void;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const BASE_RECONNECT_MS = 1000;
const MAX_RECONNECT_MS = 30_000;

// ─── Context ──────────────────────────────────────────────────────────────────

const RealtimeContext = createContext<RealtimeContextType | undefined>(undefined);

// ─── Pattern matching ─────────────────────────────────────────────────────────

function patternMatches(pattern: string, event: string): boolean {
  if (pattern === event) return true;
  if (pattern.endsWith(':*')) {
    const prefix = pattern.slice(0, -1); // "feedback:"
    return event.startsWith(prefix);
  }
  return false;
}

// ─── Provider ─────────────────────────────────────────────────────────────────

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const [connected, setConnected] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalCloseRef = useRef(false);

  // Map<pattern, Set<EventHandler>>
  const subscriptionsRef = useRef<Map<string, Set<EventHandler>>>(new Map());

  const getWsUrl = useCallback((): string | null => {
    const token =
      typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    if (!token) return null;

    const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const url = new URL(apiBase);
    const protocol = url.protocol === 'https:' ? 'wss' : 'ws';
    return `${protocol}://${url.host}/ws/events?token=${token}`;
  }, []);

  const dispatchEvent = useCallback((event: string, data: unknown) => {
    subscriptionsRef.current.forEach((handlers, pattern) => {
      if (patternMatches(pattern, event)) {
        handlers.forEach((handler) => handler(data));
      }
    });
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      intentionalCloseRef.current = true;
      wsRef.current.close(1000);
      intentionalCloseRef.current = false;
    }

    const url = getWsUrl();
    if (!url) return;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[Realtime] WS connected to', url.replace(/token=.*/, 'token=***'));
      setConnected(true);
      setReconnecting(false);
      reconnectAttemptRef.current = 0;
    };

    ws.onclose = (e) => {
      console.log('[Realtime] WS closed, code:', e.code, e.reason);
      setConnected(false);
      if (e.code === 1000 || intentionalCloseRef.current) {
        return;
      }
      setReconnecting(true);
      const attempt = reconnectAttemptRef.current;
      const delay = Math.min(BASE_RECONNECT_MS * Math.pow(2, attempt), MAX_RECONNECT_MS);
      reconnectAttemptRef.current = attempt + 1;
      reconnectTimerRef.current = setTimeout(() => {
        connect();
      }, delay);
    };

    ws.onmessage = (e: MessageEvent) => {
      try {
        const msg = JSON.parse(e.data as string) as Record<string, unknown>;
        if (msg.type === 'ping') return;
        if (msg.type === 'event') {
          console.log('[Realtime] Event received:', msg.event_type, msg.data);
          dispatchEvent(msg.event_type as string, msg.data);
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onerror = () => {
      // onerror is always followed by onclose, reconnect logic lives there
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getWsUrl, dispatchEvent]);

  useEffect(() => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }

    intentionalCloseRef.current = false;

    const url = getWsUrl();
    if (!url) return;

    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING)
    ) {
      if (wsRef.current.readyState === WebSocket.OPEN) {
        setConnected(true);
      }
      return;
    }

    connect();

    return () => {
      intentionalCloseRef.current = true;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      closeTimerRef.current = setTimeout(() => {
        wsRef.current?.close(1000);
      }, 100);
    };
  }, [connect, getWsUrl]);

  const subscribe = useCallback(
    (pattern: string, handler: EventHandler): (() => void) => {
      const subs = subscriptionsRef.current;
      if (!subs.has(pattern)) {
        subs.set(pattern, new Set());
      }
      subs.get(pattern)!.add(handler);

      return () => {
        const handlers = subs.get(pattern);
        if (handlers) {
          handlers.delete(handler);
          if (handlers.size === 0) {
            subs.delete(pattern);
          }
        }
      };
    },
    []
  );

  return (
    <RealtimeContext.Provider value={{ connected, reconnecting, subscribe }}>
      {children}
    </RealtimeContext.Provider>
  );
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useRealtime(): RealtimeContextType {
  const context = useContext(RealtimeContext);
  if (context === undefined) {
    throw new Error('useRealtime must be used within a RealtimeProvider');
  }
  return context;
}
