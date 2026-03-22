export interface MediaFile {
  id: number;
  path: string;
  name: string;
  extension: string | null;
  size: number | null;
  mime_type: string | null;
  width: number | null;
  height: number | null;
  duration: number | null;
  thumbnail_path: string | null;
  sprite_path: string | null;
  ai_description: string | null;
  metadata_json: string | null;
  library_id: number | null;
  created_at: string | null;
  modified_at: string | null;
  indexed_at?: string | null;
}

export interface Library {
  id: number;
  name: string;
  type: string;
  path: string;
  file_count: number;
  total_size: number;
  enabled: boolean;
  last_scanned: string | null;
}

export interface Person {
  person_name: string;
  match_count: number;
}

export interface FaceMatch {
  id: number;
  person_name: string;
  file_path: string;
  file_type: string;
  confidence: number;
  timestamp_start: number | null;
  timestamp_end: number | null;
  thumbnail_path: string | null;
  description: string | null;
}

export interface Channel {
  id: number;
  playlist_id: number;
  name: string;
  url: string;
  logo_url: string | null;
  group_title: string | null;
  tvg_id: string | null;
  is_favorite: boolean;
  last_watched: string | null;
}

export interface Playlist {
  id: number;
  name: string;
  url: string;
  epg_url: string | null;
  channel_count: number;
  status: string;
  last_refreshed: string | null;
  error_message: string | null;
}

export interface EPGProgram {
  id: number;
  channel_id: string;
  title: string;
  subtitle: string | null;
  description: string | null;
  category: string | null;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  poster_url: string | null;
}

export interface Recording {
  id: number;
  channel_id: number;
  program_title: string;
  stream_url: string;
  output_path: string;
  status: string;
  scheduled_start: string;
  scheduled_end: string;
  file_size: number | null;
}

export interface CacheStats {
  cache_dir: string;
  enabled: boolean;
  limit_bytes: number;
  used_bytes: number;
  used_pct: number;
  segment_count: number;
}

export interface FleetNode {
  name: string;
  host: string;
  gpu: string;
  ssh_alias: string;
  online: boolean;
}

export interface PreviewTilesSettings {
  mediaLibrary: PreviewMode;
  liveTV: PreviewMode;
  frameIntervalMs: number;
  crossfadeDurationMs: number;
  spriteFrameCount: number;
}

export interface SpriteMetadata {
  spriteUrl: string;
  posterUrl: string;
  frameWidth: number;
  frameHeight: number;
  columns: number;
  rows: number;
  totalFrames: number;
  intervalSeconds: number;
  duration: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

export type PreviewMode = 'always' | 'hover' | 'off';

export type Theme = 'dark' | 'light' | 'system';
