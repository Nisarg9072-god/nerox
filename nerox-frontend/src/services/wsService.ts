/**
 * src/services/wsService.ts
 * ===========================
 * Phase 2.6 — WebSocket client for real-time notifications.
 *
 * Features:
 *   - Auto-reconnect with exponential backoff
 *   - JWT authentication via query parameter
 *   - Keepalive ping/pong
 *   - Event subscription system
 *   - Connection state tracking
 *
 * Event types:
 *   - detection_found
 *   - alert_created
 *   - job_progress
 *   - job_completed
 *   - connected / pong (system)
 */

type EventType =
  | 'detection_found'
  | 'alert_created'
  | 'job_progress'
  | 'job_completed'
  | 'connected'
  | 'pong'
  | 'ping'
  | 'batch'
  | 'job_failed';

export interface WsEvent {
  event_id?: string;
  type: EventType;
  timestamp: string;
  sequence?: number;
  data: Record<string, unknown>;
}

type EventHandler = (event: WsEvent) => void;

export class NeroxWebSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private pingInterval: ReturnType<typeof setInterval> | null = null;
  private handlers: Map<string, Set<EventHandler>> = new Map();
  private _connected = false;
  private _status: 'disconnected' | 'connecting' | 'reconnecting' | 'connected' = 'disconnected';
  private seenEventIds = new Set<string>();
  private seenEventOrder: string[] = [];

  constructor() {
    // Derive WS URL from current page location
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Default to port 8000 (FastAPI backend)
    const host = window.location.hostname;
    this.url = `${protocol}//${host}:8000/ws/notifications`;
  }

  /** Connect to WebSocket with JWT token. */
  connect(token: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    this.cleanup();

    try {
      this._status = this.reconnectAttempts > 0 ? 'reconnecting' : 'connecting';
      this.emitStatus();
      this.ws = new WebSocket(`${this.url}?token=${token}`);

      this.ws.onopen = () => {
        this._connected = true;
        this._status = 'connected';
        this.emitStatus();
        this.reconnectAttempts = 0;

        // Start keepalive ping every 30s
        this.pingInterval = setInterval(() => {
          if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send('ping');
          }
        }, 30000);
      };

      this.ws.onmessage = (event) => {
        try {
          const data: WsEvent = JSON.parse(event.data);

          // Handle server ping
          if (data.type === 'ping') {
            this.ws?.send('ping');
            return;
          }

          if (data.type === 'batch') {
            const events = ((data.data?.events as WsEvent[]) || [])
              .sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
            for (const e of events) {
              if (!this.shouldProcess(e)) continue;
              this.emit(e.type, e);
              this.emit('*', e);
            }
            return;
          }

          if (!this.shouldProcess(data)) return;
          this.emit(data.type, data);
          this.emit('*', data); // Wildcard handler
        } catch (err) {
          void err;
        }
      };

      this.ws.onclose = (event) => {
        this._connected = false;
        this._status = 'disconnected';
        this.emitStatus();
        this.stopPing();

        if (event.code === 4001 || event.code === 4003) {
          // auth failed, no reconnect
          return;
        }

        this.scheduleReconnect(token);
      };

      this.ws.onerror = () => {
        // onclose will fire after onerror
      };
    } catch (err) {
      void err;
      this.scheduleReconnect(token);
    }
  }

  /** Disconnect and stop reconnecting. */
  disconnect(): void {
    this.reconnectAttempts = this.maxReconnectAttempts; // Prevent reconnect
    this._status = 'disconnected';
    this.emitStatus();
    this.cleanup();
  }

  /** Subscribe to a specific event type. Returns unsubscribe function. */
  on(eventType: string, handler: EventHandler): () => void {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, new Set());
    }
    this.handlers.get(eventType)!.add(handler);

    // Return unsubscribe function
    return () => {
      this.handlers.get(eventType)?.delete(handler);
    };
  }

  /** Remove all handlers for an event type. */
  off(eventType: string): void {
    this.handlers.delete(eventType);
  }

  /** Whether the WebSocket is currently connected. */
  get connected(): boolean {
    return this._connected;
  }

  get status(): 'disconnected' | 'connecting' | 'reconnecting' | 'connected' {
    return this._status;
  }

  // ── Private ────────────────────────────────────────────────────────────

  private emit(eventType: string, data: WsEvent): void {
    const handlers = this.handlers.get(eventType);
    if (handlers) {
      handlers.forEach((handler) => {
        try {
          handler(data);
        } catch (err) {
          void err;
        }
      });
    }
  }

  private scheduleReconnect(token: string): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      return;
    }

    // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s max
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    this.reconnectAttempts++;
    this._status = 'reconnecting';
    this.emitStatus();

    this.reconnectTimeout = setTimeout(() => {
      this.connect(token);
    }, delay);
  }

  private cleanup(): void {
    this.stopPing();

    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onclose = null;
      this.ws.onerror = null;

      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close();
      }
      this.ws = null;
    }

    this._connected = false;
    this._status = 'disconnected';
    this.emitStatus();
  }

  private stopPing(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  private emitStatus(): void {
    this.emit('ws_status', {
      type: 'connected',
      timestamp: new Date().toISOString(),
      data: { ws_status: this._status },
    });
  }

  private shouldProcess(event: WsEvent): boolean {
    if (!event.event_id) return true;
    if (this.seenEventIds.has(event.event_id)) return false;
    this.seenEventIds.add(event.event_id);
    this.seenEventOrder.push(event.event_id);
    if (this.seenEventOrder.length > 1000) {
      const oldest = this.seenEventOrder.shift();
      if (oldest) this.seenEventIds.delete(oldest);
    }
    return true;
  }
}

// Module-level singleton
export const neroxWs = new NeroxWebSocket();
