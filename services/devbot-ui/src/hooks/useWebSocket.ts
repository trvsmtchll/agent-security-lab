import { useCallback, useEffect, useRef, useState } from "react";
import type { WSMessage } from "../types";

/**
 * Custom React hook for WebSocket communication with the agent backend.
 *
 * Connects to the backend WebSocket endpoint (proxied via Vite in dev),
 * sends chat messages as JSON, and dispatches incoming messages via callback.
 * Auto-reconnects on disconnect with exponential backoff (max 10s).
 *
 * Args:
 *   onMessage: Callback invoked for each parsed WSMessage from the server.
 *
 * Returns:
 *   { sendMessage, isConnected } — send function and connection status.
 */
export function useWebSocket(onMessage: (msg: WSMessage) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const reconnectTimeoutRef = useRef<number>();
  const retriesRef = useRef(0);
  // Reason: Store onMessage in a ref so the WebSocket callbacks always
  // see the latest handler without re-creating the connection.
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onopen = () => {
      setIsConnected(true);
      retriesRef.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as WSMessage;
        onMessageRef.current(msg);
      } catch {
        // Reason: Ignore malformed messages — the backend may send
        // heartbeat pings or other non-JSON payloads we don't need.
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      // Reason: Exponential backoff prevents hammering the server
      // when it's temporarily unreachable, capping at 10 seconds.
      const delay = Math.min(1000 * 2 ** retriesRef.current, 10000);
      retriesRef.current += 1;
      reconnectTimeoutRef.current = window.setTimeout(connect, delay);
    };

    ws.onerror = () => ws.close();
    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimeoutRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const sendMessage = useCallback((message: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "chat", message }));
    }
  }, []);

  return { sendMessage, isConnected };
}
