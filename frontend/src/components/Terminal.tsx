import { useEffect, useRef, useState, useCallback } from 'react';
import type { CycleLogEntry } from '../lib/api';

const MAX_LINES = 200;

const LOG_COLORS: Record<string, string> = {
  info: 'text-alive',
  warn: 'text-yellow-400',
  error: 'text-cost',
  debug: 'text-white/30',
};

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', { hour12: false });
  } catch {
    return iso;
  }
}

/**
 * Live terminal consuming SSE from /current-cycle.
 * Styled as a retro terminal with timestamps and colored log levels.
 */
export default function Terminal() {
  const [lines, setLines] = useState<CycleLogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const connect = useCallback(() => {
    if (typeof window === 'undefined' || typeof EventSource === 'undefined') return;

    const apiUrl =
      (import.meta as unknown as { env?: Record<string, string> }).env?.PUBLIC_API_URL ??
      'http://localhost:8000';

    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    try {
      const es = new EventSource(`${apiUrl}/current-cycle`);
      eventSourceRef.current = es;

      es.onopen = () => {
        setConnected(true);
        setError(null);
      };

      es.onmessage = (event: MessageEvent) => {
        try {
          const entry = JSON.parse(event.data as string) as CycleLogEntry;
          setLines((prev) => {
            const next = [...prev, entry];
            return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next;
          });
        } catch {
          // Non-JSON message, treat as plain text
          const entry: CycleLogEntry = {
            timestamp: new Date().toISOString(),
            level: 'info',
            message: String(event.data),
          };
          setLines((prev) => {
            const next = [...prev, entry];
            return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next;
          });
        }
      };

      es.onerror = () => {
        setConnected(false);
        setError('Connection lost');
        es.close();
        eventSourceRef.current = null;
        // Attempt reconnect after 5s
        setTimeout(connect, 5000);
      };
    } catch {
      setConnected(false);
      setError('Failed to connect');
    }
  }, []);

  // Auto-scroll when new lines arrive
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines, autoScroll]);

  // Connect on mount
  useEffect(() => {
    connect();
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [connect]);

  // Handle scroll to detect user scroll
  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 40;
    setAutoScroll(isAtBottom);
  }, []);

  const clearTerminal = useCallback(() => {
    setLines([]);
  }, []);

  return (
    <div className="rounded-lg border border-white/5 overflow-hidden bg-[#06060a] font-mono">
      {/* Terminal header */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-white/[0.03] border-b border-white/5">
        <div className="flex items-center gap-3">
          {/* Traffic light dots */}
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-cost/60" />
            <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/60" />
            <div className="w-2.5 h-2.5 rounded-full bg-alive/60" />
          </div>
          <span className="text-[10px] text-white/30 uppercase tracking-[0.2em]">
            Live Terminal
          </span>
        </div>
        <div className="flex items-center gap-3">
          {/* Connection status */}
          <div className="flex items-center gap-1.5">
            <div
              className={`w-1.5 h-1.5 rounded-full ${
                connected ? 'bg-alive animate-pulse' : 'bg-cost'
              }`}
            />
            <span className="text-[10px] text-white/20">
              {connected ? 'LIVE' : error ?? 'OFFLINE'}
            </span>
          </div>
          {/* Clear button */}
          <button
            onClick={clearTerminal}
            className="text-[10px] text-white/20 hover:text-white/50 transition-colors uppercase tracking-wider"
            title="Clear terminal"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Terminal body */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="h-64 overflow-y-auto p-4 space-y-0.5"
      >
        {lines.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <div className="text-white/10 text-sm">
              {connected
                ? 'Waiting for cycle activity...'
                : 'Connecting to backend...'}
            </div>
            <div className="flex items-center gap-1">
              <span className="text-alive text-xs">$</span>
              <span className="text-white/20 text-xs">_</span>
              <span className="inline-block w-1.5 h-3.5 bg-alive/70 animate-terminal-blink" />
            </div>
          </div>
        ) : (
          lines.map((line, i) => (
            <div key={i} className="flex items-start gap-2 text-xs leading-relaxed">
              {/* Timestamp */}
              <span className="text-white/15 flex-shrink-0 select-none">
                {formatTimestamp(line.timestamp)}
              </span>
              {/* Level badge */}
              <span
                className={`flex-shrink-0 uppercase w-12 text-right ${
                  LOG_COLORS[line.level] ?? 'text-white/30'
                }`}
              >
                [{line.level}]
              </span>
              {/* Step indicator */}
              {line.step && (
                <span className="text-creative/50 flex-shrink-0">
                  {line.step}:
                </span>
              )}
              {/* Message */}
              <span className="text-white/60 break-all">{line.message}</span>
            </div>
          ))
        )}
      </div>

      {/* Input line (decorative) */}
      <div className="px-4 py-2 border-t border-white/5 flex items-center gap-2">
        <span className="text-alive text-xs">$</span>
        <span className="text-white/20 text-xs">watching cycle...</span>
        <span className="inline-block w-1.5 h-3.5 bg-alive/70 animate-terminal-blink" />
      </div>
    </div>
  );
}
