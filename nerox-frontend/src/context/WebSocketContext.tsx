/**
 * src/context/WebSocketContext.tsx
 * ==================================
 * Phase 2.6 — WebSocket React Context + Provider.
 *
 * Auto-connects when the user is authenticated.
 * Provides:
 *   - useWebSocket() hook for accessing WS state
 *   - Event subscription via useWsEvent() custom hook
 *   - Live toast notifications for high-priority events
 *   - Connection status indicator
 */

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { neroxWs, type WsEvent } from '../services/wsService';
import { useAuth } from './AuthContext';
import { toast } from 'sonner';

// ── Context ──────────────────────────────────────────────────────────────────

interface WebSocketContextType {
  connected: boolean;
  wsStatus: 'disconnected' | 'connecting' | 'reconnecting' | 'connected';
  lastEvent: WsEvent | null;
  recentEvents: WsEvent[];
}

const WebSocketContext = createContext<WebSocketContextType>({
  connected: false,
  wsStatus: 'disconnected',
  lastEvent: null,
  recentEvents: [],
});

// ── Provider ─────────────────────────────────────────────────────────────────

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [connected, setConnected] = useState(false);
  const [wsStatus, setWsStatus] = useState<WebSocketContextType['wsStatus']>('disconnected');
  const [lastEvent, setLastEvent] = useState<WsEvent | null>(null);
  const [recentEvents, setRecentEvents] = useState<WsEvent[]>([]);
  const pendingRef = useRef<WsEvent[]>([]);
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seenIdsRef = useRef<Set<string>>(new Set());
  const seenOrderRef = useRef<string[]>([]);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem('nerox_ws_recent_events');
      if (!raw) return;
      const parsed = JSON.parse(raw) as WsEvent[];
      setRecentEvents(parsed.slice(0, 50));
      if (parsed.length) setLastEvent(parsed[0]);
      parsed.forEach((evt) => {
        if (evt.event_id) {
          seenIdsRef.current.add(evt.event_id);
          seenOrderRef.current.push(evt.event_id);
        }
      });
    } catch {
      // no-op
    }
  }, []);

  useEffect(() => {
    sessionStorage.setItem('nerox_ws_recent_events', JSON.stringify(recentEvents.slice(0, 50)));
  }, [recentEvents]);

  useEffect(() => {
    if (!isAuthenticated) {
      neroxWs.disconnect();
      setConnected(false);
      setWsStatus('disconnected');
      return;
    }

    const token = localStorage.getItem('nerox_token');
    if (!token) return;

    // Connect to WebSocket
    neroxWs.connect(token);

    // Track connection state
    const unsubConnected = neroxWs.on('connected', () => {
      setConnected(true);
      setWsStatus('connected');
    });
    const unsubWsStatus = neroxWs.on('ws_status', (event) => {
      const status = String(event.data?.ws_status || 'disconnected') as WebSocketContextType['wsStatus'];
      setWsStatus(status);
      setConnected(status === 'connected');
    });

    // Track all events
    const unsubAll = neroxWs.on('*', (event) => {
      pendingRef.current.push(event);
      if (!flushTimerRef.current) {
        flushTimerRef.current = setTimeout(() => {
          const batch = pendingRef.current.splice(0, pendingRef.current.length);
          if (batch.length > 0) {
            const unique = batch.filter((evt) => {
              const id = evt.event_id;
              if (!id) return true;
              if (seenIdsRef.current.has(id)) return false;
              seenIdsRef.current.add(id);
              seenOrderRef.current.push(id);
              if (seenOrderRef.current.length > 500) {
                const dropped = seenOrderRef.current.shift();
                if (dropped) seenIdsRef.current.delete(dropped);
              }
              return true;
            });
            if (!unique.length) {
              flushTimerRef.current = null;
              return;
            }
            const newest = unique[unique.length - 1];
            setLastEvent(newest);
            setRecentEvents((prev) => [...unique, ...prev].slice(0, 50));
          }
          flushTimerRef.current = null;
        }, 120);
      }

      // Update connection state on pong
      if (event.type === 'pong') {
        setConnected(true);
      }
    });

    // ── Live toast notifications for important events ──────────────────

    const unsubDetection = neroxWs.on('detection_found', (event) => {
      const sim = Math.round(((event.data?.similarity as number) || 0) * 100);
      toast.warning(
        `🔍 Match detected! ${sim}% similarity found on ${String(event.data?.platform || 'source')}`,
        { duration: 6000 },
      );
    });

    const unsubAlert = neroxWs.on('alert_created', (event) => {
      const severity = String(event.data?.severity || 'medium');
      const toastFn = severity === 'critical' ? toast.error : toast.warning;
      toastFn(
        `🚨 ${severity.toUpperCase()} Alert: ${String(event.data?.message || 'New alert')}`,
        { duration: 8000 },
      );
    });

    const unsubJobCompleted = neroxWs.on('job_completed', (event) => {
      const matches = Number(event.data?.matches_found || 0);
      const status = String(event.data?.status || 'completed');
      if (status === 'completed') {
        if (matches > 0) {
          toast.warning(
            `📡 Scan complete: ${matches} match${matches !== 1 ? 'es' : ''} found`,
            { duration: 5000 },
          );
        } else {
          toast.success('✅ Scan complete: No matches found — assets are safe', {
            duration: 4000,
          });
        }
      } else if (status === 'failed') {
        toast.error('❌ Detection scan failed. Check job details.', { duration: 5000 });
      }
    });
    const unsubJobFailed = neroxWs.on('job_failed', (event) => {
      toast.error(`❌ Scan failed: ${String(event.data?.reason || 'Unknown error')}`, {
        duration: 7000,
      });
    });

    return () => {
      unsubConnected();
      unsubWsStatus();
      unsubAll();
      unsubDetection();
      unsubAlert();
      unsubJobCompleted();
      unsubJobFailed();
      if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
      neroxWs.disconnect();
      setConnected(false);
    };
  }, [isAuthenticated]);

  return (
    <WebSocketContext.Provider value={{ connected, wsStatus, lastEvent, recentEvents }}>
      {children}
    </WebSocketContext.Provider>
  );
}

// ── Hooks ────────────────────────────────────────────────────────────────────

/** Access WebSocket connection state and last event. */
export function useWebSocket() {
  const ctx = useContext(WebSocketContext);
  if (!ctx) throw new Error('useWebSocket must be used within <WebSocketProvider>');
  return ctx;
}

/**
 * Subscribe to a specific WebSocket event type.
 * Re-runs the callback whenever a matching event arrives.
 */
export function useWsEvent(eventType: string, handler: (event: WsEvent) => void) {
  useEffect(() => {
    const unsub = neroxWs.on(eventType, handler);
    return unsub;
  }, [eventType, handler]);
}
