/**
 * Typed WebSocket hook for a session event stream.
 *
 * Connects to WS /ws/sessions/{sessionId}?token=<jwt>.
 * Handles reconnection automatically (react-use-websocket default).
 *
 * Usage:
 *   const { lastEvent, readyState } = useSessionWs(sessionId);
 */

import { useEffect } from "react";
import useWebSocket, { ReadyState } from "react-use-websocket";
import { getToken } from "@/api/client";

export interface SessionEvent {
  type: string;
  seq?: number;
  payload: Record<string, unknown>;
}

interface UseSessionWsOptions {
  onEvent?: (event: SessionEvent) => void;
}

export function useSessionWs(sessionId: string | null, options: UseSessionWsOptions = {}) {
  const token = getToken();
  const socketUrl =
    sessionId && token ? `/ws/sessions/${sessionId}?token=${encodeURIComponent(token)}` : null;

  const { lastMessage, readyState } = useWebSocket(socketUrl, {
    shouldReconnect: () => true,
    reconnectAttempts: 10,
    reconnectInterval: 2000,
  });

  useEffect(() => {
    if (!lastMessage?.data) return;
    try {
      const event = JSON.parse(lastMessage.data as string) as SessionEvent;
      options.onEvent?.(event);
    } catch {
      // malformed message — ignore
    }
  }, [lastMessage]);

  return {
    readyState,
    isConnected: readyState === ReadyState.OPEN,
  };
}
