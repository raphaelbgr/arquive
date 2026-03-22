import { useState } from 'react';

interface WebSocketMessage {
  type: string;
  data: unknown;
}

interface UseWebSocketReturn {
  lastMessage: WebSocketMessage | null;
  isConnected: boolean;
}

/**
 * WebSocket hook stub.
 * TODO: Implement actual WebSocket connection to ws://host/ws
 * for real-time scan progress, recording status, and fleet updates.
 */
export function useWebSocket(): UseWebSocketReturn {
  const [lastMessage] = useState<WebSocketMessage | null>(null);
  const [isConnected] = useState(false);

  return { lastMessage, isConnected };
}
