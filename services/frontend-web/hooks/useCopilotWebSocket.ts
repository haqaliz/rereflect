'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface AssistantMessage {
  type: 'assistant_message';
  message_id: string;
  content: string;
}

export interface StructuredDataMessage {
  type: 'structured_data';
  message_id: string;
  data: Record<string, unknown>;
}

export type CopilotMessage = AssistantMessage | StructuredDataMessage;

export interface UseCopilotWebSocketOptions {
  onMessage?: (msg: CopilotMessage) => void;
}

export interface UseCopilotWebSocketReturn {
  connected: boolean;
  streaming: boolean;
  streamingContent: string;
  statusText: string;
  reconnecting: boolean;
  error: string | null;
  sendQuery: (conversationId: string, content: string, contextScope: string) => void;
  stopGeneration: (messageId: number | string) => void;
  regenerate: (messageId: number | string) => void;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const BASE_RECONNECT_MS = 1000;
const MAX_RECONNECT_MS = 30_000;

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useCopilotWebSocket(
  options: UseCopilotWebSocketOptions = {}
): UseCopilotWebSocketReturn {
  const { isAuthenticated } = useAuth();
  const onMessageRef = useRef(options.onMessage);
  onMessageRef.current = options.onMessage;

  const [connected, setConnected] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [statusText, setStatusText] = useState('');
  const [reconnecting, setReconnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalCloseRef = useRef(false);
  const streamBufferRef = useRef('');

  const getWsUrl = useCallback(() => {
    const t = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    if (!t) return null;
    // Use the same API base URL as REST calls (NEXT_PUBLIC_API_URL)
    const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const url = new URL(apiBase);
    const protocol = url.protocol === 'https:' ? 'wss' : 'ws';
    return `${protocol}://${url.host}/ws/copilot?token=${t}`;
  }, [isAuthenticated]); // eslint-disable-line react-hooks/exhaustive-deps

  const connect = useCallback(() => {
    // Close any existing connection before opening a new one
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
      setConnected(true);
      setReconnecting(false);
      reconnectAttemptRef.current = 0;
    };

    ws.onclose = (e) => {
      setConnected(false);
      // Normal closure — don't reconnect
      if (e.code === 1000 || intentionalCloseRef.current) {
        return;
      }
      // Abnormal closure — reconnect with exponential backoff
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
        const msg = JSON.parse(e.data as string);
        handleServerMessage(msg);
      } catch {
        // ignore malformed messages
      }
    };

    ws.onerror = () => {
      // onerror is always followed by onclose, so reconnect logic lives there
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getWsUrl]);

  function handleServerMessage(msg: Record<string, unknown>) {
    switch (msg.type) {
      case 'ping':
        // Server heartbeat — ignore
        break;

      case 'status': {
        // Backend sends: { type: "status", message_id, status: "processing"|"generating"|"stopped" }
        const st = msg.status as string;
        setStatusText(st);
        // Show the streaming bubble while the backend is working
        if (st === 'processing' || st === 'generating') {
          setStreaming(true);
        } else if (st === 'stopped') {
          setStreaming(false);
          setStreamingContent('');
          setStatusText('');
          streamBufferRef.current = '';
        }
        break;
      }

      case 'stream': {
        // Backend sends: { type: "stream", message_id, delta: "text", done: false }
        //           or:  { type: "stream", message_id, delta: "", done: true, metadata: {...} }
        if (msg.done) {
          const finalContent = streamBufferRef.current;
          const messageId = msg.message_id as string;
          setStreaming(false);
          setStreamingContent('');
          setStatusText('');
          streamBufferRef.current = '';
          onMessageRef.current?.({
            type: 'assistant_message',
            message_id: messageId,
            content: finalContent,
          });
        } else {
          const delta = (msg.delta as string) ?? '';
          streamBufferRef.current += delta;
          setStreaming(true);
          setStreamingContent(streamBufferRef.current);
        }
        break;
      }

      case 'structured_data':
        onMessageRef.current?.({
          type: 'structured_data',
          message_id: msg.message_id as string,
          data: msg.data as Record<string, unknown>,
        });
        break;

      case 'error':
        // Backend sends: { type: "error", message_id, error: "...", suggestions: [...] }
        setError(msg.error as string);
        setStreaming(false);
        setStreamingContent('');
        streamBufferRef.current = '';
        break;
    }
  }

  useEffect(() => {
    if (!isAuthenticated) return;

    // Cancel any pending close from a previous cleanup (React Strict Mode double-mount)
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }

    intentionalCloseRef.current = false;

    // If we already have an open/connecting WS, reuse it instead of creating a new one
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) {
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
      // Delay close to survive React Strict Mode double-mount.
      // If the component remounts within 100ms, the timer is cancelled above.
      closeTimerRef.current = setTimeout(() => {
        wsRef.current?.close(1000);
      }, 100);
    };
  }, [isAuthenticated, connect]);

  const send = useCallback((data: object) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify(data));
  }, []);

  const sendQuery = useCallback(
    (conversationId: string, content: string, contextScope: string) => {
      setError(null);
      streamBufferRef.current = '';
      send({ type: 'query', conversation_id: conversationId, content, context_scope: contextScope });
    },
    [send]
  );

  const stopGeneration = useCallback(
    (messageId: number | string) => {
      send({ type: 'stop', message_id: messageId });
    },
    [send]
  );

  const regenerate = useCallback(
    (messageId: number | string) => {
      send({ type: 'regenerate', message_id: messageId });
    },
    [send]
  );

  return {
    connected,
    streaming,
    streamingContent,
    statusText,
    reconnecting,
    error,
    sendQuery,
    stopGeneration,
    regenerate,
  };
}
