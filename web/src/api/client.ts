/**
 * Typed API client for Arquive backend.
 *
 * All Flask endpoints return JSON objects with named wrapper keys
 * (e.g. {playlists: [...]}, {items: [...], total: N}).
 * This client returns the raw JSON — components extract what they need.
 */

import type {
  MediaFile,
  Library,
  CacheStats,
  FleetNode,
  PreviewTilesSettings,
  Theme,
} from '../types';

const BASE_URL = '/api/v1';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function apiFetch<T = any>(path: string, options?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };

  const response = await fetch(url, {
    credentials: 'include',
    headers,
    ...options,
  });

  if (!response.ok) {
    throw new Error(`API ${response.status}: ${response.statusText}`);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  media: {
    list(params?: Record<string, string | number>) {
      const qs = params ? '?' + new URLSearchParams(
        Object.entries(params).map(([k, v]) => [k, String(v)])
      ) : '';
      return apiFetch<{ items: MediaFile[]; total: number; page: number; pages: number }>(`/media${qs}`);
    },
    get(id: number) {
      return apiFetch<MediaFile>(`/media/${id}`);
    },
    delete(id: number) {
      return apiFetch<{ ok: boolean }>(`/media/${id}`, { method: 'DELETE' });
    },
    search(q: string) {
      return apiFetch<{ items: MediaFile[]; query: string }>(`/media/search?q=${encodeURIComponent(q)}`);
    },
    stats() {
      return apiFetch<{ total_files: number; total_size: number; extension_count: number }>('/media/stats');
    },
    timeline() {
      return apiFetch<{ groups: { month: string; count: number }[] }>('/media/timeline');
    },
    folders(parent?: string) {
      const qs = parent ? `?parent=${encodeURIComponent(parent)}` : '';
      return apiFetch<{ folders: { path: string; name: string; count: number }[]; file_count?: number }>(`/media/folders${qs}`);
    },
  },

  faces: {
    persons() {
      return apiFetch<{ persons: { person_name: string; match_count: number }[] }>('/faces/persons');
    },
    person(name: string) {
      return apiFetch<{ person: string; matches: Record<string, unknown>[]; total: number }>(
        `/faces/persons/${encodeURIComponent(name)}`
      );
    },
    matches(params?: Record<string, string>) {
      const qs = params ? '?' + new URLSearchParams(params) : '';
      return apiFetch<{ items: Record<string, unknown>[]; total: number }>(`/faces/matches${qs}`);
    },
    scanStatus() {
      return apiFetch('/faces/scan');
    },
    settings() {
      return apiFetch<{ model: string; threshold: number; det_size: number[] }>('/faces/settings');
    },
  },

  iptv: {
    playlists() {
      return apiFetch<{ playlists: Record<string, unknown>[] }>('/iptv/playlists');
    },
    addPlaylist(url: string, name: string) {
      return apiFetch<{ id: number }>('/iptv/playlists', {
        method: 'POST',
        body: JSON.stringify({ url, name }),
      });
    },
    deletePlaylist(id: number) {
      return apiFetch(`/iptv/playlists/${id}`, { method: 'DELETE' });
    },
    refreshPlaylist(id: number) {
      return apiFetch(`/iptv/playlists/${id}/refresh`, { method: 'POST' });
    },
    channels(params?: Record<string, string>) {
      const qs = params ? '?' + new URLSearchParams(params) : '';
      return apiFetch<{ channels: Record<string, unknown>[] }>(`/iptv/channels${qs}`);
    },
    favorites() {
      return apiFetch<{ channels: Record<string, unknown>[] }>('/iptv/channels/favorites');
    },
    toggleFavorite(id: number) {
      return apiFetch(`/iptv/channels/${id}/favorite`, { method: 'PUT' });
    },
    groups() {
      return apiFetch<{ groups: { group_title: string; count: number }[] }>('/iptv/channels/groups');
    },
    streams() {
      return apiFetch<{ streams: Record<string, unknown>[] }>('/iptv/streams');
    },
    addStream(name: string, url: string, category?: string) {
      return apiFetch<{ id: number }>('/iptv/streams', {
        method: 'POST',
        body: JSON.stringify({ name, url, category }),
      });
    },
    deleteStream(id: number) {
      return apiFetch(`/iptv/streams/${id}`, { method: 'DELETE' });
    },
    epg(params?: Record<string, string>) {
      const qs = params ? '?' + new URLSearchParams(params) : '';
      return apiFetch<{ programs: Record<string, unknown>[] }>(`/iptv/epg${qs}`);
    },
    epgNow() {
      return apiFetch<{ programs: Record<string, unknown>[] }>('/iptv/epg/now');
    },
    epgSources() {
      return apiFetch<{ sources: Record<string, unknown>[] }>('/iptv/epg/sources');
    },
    recordings() {
      return apiFetch<{ recordings: Record<string, unknown>[] }>('/iptv/recordings');
    },
    startRecording(data: Record<string, unknown>) {
      return apiFetch<{ id: number }>('/iptv/recordings', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
    stopRecording(id: number) {
      return apiFetch(`/iptv/recordings/${id}/stop`, { method: 'PUT' });
    },
  },

  cache: {
    stats() {
      return apiFetch<CacheStats>('/cache/stats');
    },
    updateSettings(data: Partial<CacheStats>) {
      return apiFetch<CacheStats>('/cache/settings', {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },
    clear() {
      return apiFetch<{ freed_bytes: number }>('/cache/clear', { method: 'POST' });
    },
    move(path: string) {
      return apiFetch<CacheStats>('/cache/move', {
        method: 'POST',
        body: JSON.stringify({ path }),
      });
    },
  },

  fleet: {
    status() {
      return apiFetch<{ nodes: FleetNode[] }>('/fleet/status');
    },
    nodes() {
      return apiFetch<{ nodes: FleetNode[] }>('/fleet/nodes');
    },
  },

  ai: {
    status() {
      return apiFetch<{ enabled: boolean; model: string; endpoint: string }>('/ai/status');
    },
    config() {
      return apiFetch('/ai/config');
    },
  },

  auth: {
    login(data: { username?: string; password: string }) {
      return apiFetch<{ ok: boolean }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
    logout() {
      return apiFetch('/auth/logout', { method: 'POST' });
    },
    me() {
      return apiFetch<{ user: string; role: string; sec_level: string }>('/auth/me');
    },
    revokeAll() {
      return apiFetch('/auth/revoke-all', { method: 'POST' });
    },
  },

  settings: {
    getAll() {
      return apiFetch<Record<string, string>>('/settings');
    },
    update(data: Record<string, unknown>) {
      return apiFetch('/settings', { method: 'PUT', body: JSON.stringify(data) });
    },
    getTheme() {
      return apiFetch<{ theme: Theme }>('/settings/theme');
    },
    setTheme(theme: Theme) {
      return apiFetch<{ theme: Theme }>('/settings/theme', {
        method: 'PUT',
        body: JSON.stringify({ theme }),
      });
    },
    getPreviewTiles() {
      return apiFetch<PreviewTilesSettings>('/settings/preview-tiles');
    },
    setPreviewTiles(data: Partial<PreviewTilesSettings>) {
      return apiFetch<PreviewTilesSettings>('/settings/preview-tiles', {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },
    libraries() {
      return apiFetch<{ libraries: Library[] }>('/settings/libraries');
    },
    addLibrary(data: { name: string; type: string; path: string }) {
      return apiFetch<{ id: number }>('/settings/libraries', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
    removeLibrary(id: number) {
      return apiFetch(`/settings/libraries/${id}`, { method: 'DELETE' });
    },
  },
};
