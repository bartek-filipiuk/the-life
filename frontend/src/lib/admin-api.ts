/**
 * Typed admin API client for The Life backend.
 * Auth token stored in sessionStorage after login.
 */

import { BASE_URL } from './api';

// ── Types ──────────────────────────────────────────────────────────────

export interface AdminRoom {
  id: string;
  cycle_number: number;
  created_at: string;
  title: string;
  content_type: string;
  mood: string;
  tags: string[];
  total_cost: number;
  has_image: boolean;
  has_music: boolean;
  status: string;
}

export interface AdminRoomList {
  rooms: AdminRoom[];
  total: number;
  page: number;
  per_page: number;
}

export interface RuntimeConfig {
  heartbeat_interval: number;
  model: string;
  budget_per_cycle: number;
  budget_daily: number;
  budget_monthly: number;
  temperature_min: number;
  temperature_max: number;
  novelty_threshold: number;
  meta_reflection_every: number;
  search_provider: string;
  scheduler_running: boolean;
}

// ── Auth ───────────────────────────────────────────────────────────────

const TOKEN_KEY = 'thelife_admin_token';

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

// ── API Client ─────────────────────────────────────────────────────────

const TIMEOUT_MS = 15_000;

export async function adminRequest<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const token = getToken();
  if (!token) throw new Error('Not authenticated');

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        ...options?.headers,
      },
    });

    if (response.status === 401) {
      clearToken();
      throw new Error('Unauthorized');
    }

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `API Error ${response.status}`);
    }

    return (await response.json()) as T;
  } finally {
    clearTimeout(timeout);
  }
}

// ── Auth check ─────────────────────────────────────────────────────────

export async function verifyToken(token: string): Promise<boolean> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const resp = await fetch(`${BASE_URL}/admin/config`, {
      signal: controller.signal,
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/json',
      },
    });
    return resp.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

// ── Rooms ──────────────────────────────────────────────────────────────

export async function listRooms(
  page = 1,
  perPage = 20,
  status?: string,
): Promise<AdminRoomList> {
  let url = `/admin/rooms?page=${page}&per_page=${perPage}`;
  if (status) url += `&status=${encodeURIComponent(status)}`;
  return adminRequest<AdminRoomList>(url);
}

export async function updateRoom(
  id: string,
  updates: Record<string, unknown>,
): Promise<AdminRoom> {
  return adminRequest<AdminRoom>(`/admin/rooms/${id}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  });
}

export async function updateRoomStatus(
  id: string,
  status: string,
): Promise<AdminRoom> {
  return adminRequest<AdminRoom>(`/admin/rooms/${id}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
}

export async function deleteRoom(id: string): Promise<void> {
  await adminRequest(`/admin/rooms/${id}`, { method: 'DELETE' });
}

// ── Config ─────────────────────────────────────────────────────────────

export async function getConfig(): Promise<RuntimeConfig> {
  return adminRequest<RuntimeConfig>('/admin/config');
}

export async function updateConfig(
  updates: Partial<RuntimeConfig>,
): Promise<RuntimeConfig> {
  return adminRequest<RuntimeConfig>('/admin/config', {
    method: 'PUT',
    body: JSON.stringify(updates),
  });
}

// ── Scheduler ──────────────────────────────────────────────────────────

export async function pauseScheduler(): Promise<{ status: string; message: string }> {
  return adminRequest('/admin/scheduler/pause', { method: 'POST' });
}

export async function resumeScheduler(): Promise<{ status: string; message: string }> {
  return adminRequest('/admin/scheduler/resume', { method: 'POST' });
}

// ── Trigger ────────────────────────────────────────────────────────────

export async function triggerCycle(): Promise<{
  status: string;
  message: string;
  room_id?: string;
}> {
  return adminRequest('/admin/trigger', { method: 'POST' });
}
