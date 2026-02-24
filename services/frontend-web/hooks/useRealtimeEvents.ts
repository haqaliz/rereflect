'use client';

import { useEffect, useRef } from 'react';
import { useRealtime, EventHandler } from '@/contexts/RealtimeContext';

export interface UseRealtimeEventsReturn {
  connected: boolean;
  reconnecting: boolean;
}

export function useRealtimeEvents(
  pattern: string,
  handler: EventHandler
): UseRealtimeEventsReturn {
  const { connected, reconnecting, subscribe } = useRealtime();

  // Keep a ref to the latest handler to avoid stale closures
  const handlerRef = useRef<EventHandler>(handler);
  handlerRef.current = handler;

  useEffect(() => {
    const stableHandler: EventHandler = (data) => {
      handlerRef.current(data);
    };

    const unsubscribe = subscribe(pattern, stableHandler);
    return unsubscribe;
  }, [pattern, subscribe]);

  return { connected, reconnecting };
}
