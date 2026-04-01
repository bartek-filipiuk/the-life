/**
 * Typed API client for The Life backend.
 *
 * All functions gracefully return null or empty arrays when the backend
 * is unreachable, so the frontend works standalone with placeholder states.
 */

// ── Types ──────────────────────────────────────────────────────────────

export interface Room {
  id: string;
  cycle_number: number;
  created_at: string;
  title: string;
  content: string;
  content_type: 'poem' | 'essay' | 'haiku' | 'reflection' | 'story';
  mood: string;
  tags: string[];
  image_url: string | null;
  image_prompt: string | null;
  music_url: string | null;
  music_prompt: string | null;
  intention: string;
  reasoning: string;
  decision_prompt: string;
  creation_prompt: string;
  search_queries: string[];
  search_results: SearchResult[];
  next_hint: string;
  connections: string[];
  model: string;
  llm_tokens: number;
  llm_cost: number;
  image_cost: number;
  music_cost: number;
  search_cost: number;
  total_cost: number;
  duration_ms: number;
}

export interface SearchResult {
  title: string;
  url: string;
  snippet: string;
}

export interface GraphNode {
  id: string;
  label: string;
  content_type: string;
  mood: string;
  cycle_number: number;
  connections_count: number;
  is_latest: boolean;
  image_url: string | null;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Stats {
  total_cost: number;
  total_tokens: number;
  total_rooms: number;
  model: string;
  cost_per_day: DayStat[];
  top_tags: TagCount[];
  avg_cost_per_room: number;
  status: 'alive' | 'paused' | 'error';
  next_cycle_at: string | null;
  uptime_seconds: number;
}

export interface DayStat {
  day: string;
  cost: number;
  tokens: number;
  rooms: number;
}

export interface TagCount {
  tag: string;
  count: number;
}

export interface TimelineDay {
  date: string;
  rooms: Room[];
}

export interface HealthResponse {
  status: string;
  cycle_count: number;
  uptime: number;
}

export interface CycleLogEntry {
  timestamp: string;
  level: 'info' | 'warn' | 'error' | 'debug';
  message: string;
  step?: string;
}

// ── API Client ─────────────────────────────────────────────────────────

const BASE_URL: string =
  typeof import.meta !== 'undefined' && (import.meta as Record<string, unknown>).env
    ? ((import.meta as unknown as { env: Record<string, string> }).env.PUBLIC_API_URL ?? 'http://localhost:8765')
    : 'http://localhost:8765';

const TIMEOUT_MS = 10_000;

class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly statusText: string,
    message?: string,
  ) {
    super(message ?? `API Error ${status}: ${statusText}`);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        'Accept': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      throw new ApiError(response.status, response.statusText);
    }

    const data = (await response.json()) as T;
    return data;
  } catch (error: unknown) {
    if (error instanceof ApiError) {
      console.error(`[api] ${error.message}`);
    } else if (error instanceof DOMException && error.name === 'AbortError') {
      console.error(`[api] Request to ${path} timed out after ${TIMEOUT_MS}ms`);
    } else {
      console.error(`[api] Request to ${path} failed:`, error);
    }
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

// ── Endpoints ──────────────────────────────────────────────────────────

export async function getHealth(): Promise<HealthResponse | null> {
  return request<HealthResponse>('/health');
}

export async function getRooms(page = 1, perPage = 20): Promise<Room[]> {
  const data = await request<{ rooms: Room[]; total: number }>(`/rooms?page=${page}&per_page=${perPage}`);
  return data?.rooms ?? [];
}

export async function getRoom(id: string): Promise<Room | null> {
  return request<Room>(`/rooms/${encodeURIComponent(id)}`);
}

export async function getGraph(): Promise<GraphData | null> {
  return request<GraphData>('/graph');
}

export async function getStats(): Promise<Stats | null> {
  return request<Stats>('/stats');
}

export async function getTimeline(): Promise<TimelineDay[]> {
  const data = await request<{ days: TimelineDay[] }>('/timeline');
  return data?.days ?? [];
}

export async function triggerCycle(): Promise<boolean> {
  const data = await request<{ status: string }>('/trigger', { method: 'POST' });
  return data !== null;
}

/**
 * Subscribe to the current cycle SSE stream.
 * Returns an EventSource that emits CycleLogEntry JSON on 'message'.
 * Returns null if we're in a non-browser environment.
 */
export function subscribeToCycle(): EventSource | null {
  if (typeof window === 'undefined' || typeof EventSource === 'undefined') {
    return null;
  }

  try {
    return new EventSource(`${BASE_URL}/current-cycle`);
  } catch {
    console.error('[api] Failed to create EventSource for /current-cycle');
    return null;
  }
}

/** Resolve an asset URL (image/music) against the API base. */
export function assetUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  return `${BASE_URL}${path.startsWith('/') ? '' : '/'}${path}`;
}

/** Format a cost value to display string. */
export function formatCost(cost: number | undefined | null): string {
  if (cost == null) return '$0.0000';
  return `$${cost.toFixed(4)}`;
}

/** Format large numbers with commas. */
export function formatNumber(n: number): string {
  return n.toLocaleString('en-US');
}

/** Format duration in ms to human readable. */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${remainingSeconds}s`;
}

/** Map content_type to a display color class. */
export function contentTypeColor(type: string): string {
  switch (type) {
    case 'poem': return 'text-creative';
    case 'essay': return 'text-info';
    case 'haiku': return 'text-alive';
    case 'reflection': return 'text-cost';
    case 'story': return 'text-white';
    default: return 'text-white';
  }
}

/** Map content_type to hex color for graph rendering. */
export function contentTypeHex(type: string): string {
  switch (type) {
    case 'poem': return '#c084fc';
    case 'essay': return '#6b9fff';
    case 'haiku': return '#00ff88';
    case 'reflection': return '#ff6b6b';
    case 'story': return '#ffffff';
    default: return '#ffffff';
  }
}
