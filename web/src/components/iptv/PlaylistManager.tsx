import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { Playlist } from '../../types';
import { api } from '../../api/client';

function formatDate(iso: string | null): string {
  if (!iso) return 'Never';
  return new Date(iso).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const STATUS_STYLES: Record<string, string> = {
  active: 'bg-green-500/20 text-green-300 border-green-400/20',
  error: 'bg-red-500/20 text-red-300 border-red-400/20',
  refreshing: 'bg-amber-500/20 text-amber-300 border-amber-400/20',
  pending: 'bg-gray-500/20 text-gray-300 border-gray-400/20',
};

export function PlaylistManager() {
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState('');
  const [newUrl, setNewUrl] = useState('');
  const [adding, setAdding] = useState(false);

  const fetchPlaylists = useCallback(async () => {
    try {
      setError(null);
      const data = await api.iptv.playlists() as unknown as { playlists: Playlist[] };
      setPlaylists(data.playlists);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load playlists');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPlaylists();
  }, [fetchPlaylists]);

  const handleAdd = async () => {
    if (!newUrl.trim() || !newName.trim()) return;
    setAdding(true);
    try {
      await api.iptv.addPlaylist(newUrl.trim(), newName.trim());
      await fetchPlaylists();
      setNewName('');
      setNewUrl('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add playlist');
    } finally {
      setAdding(false);
    }
  };

  const handleRefresh = async (id: number) => {
    try {
      const updated = await api.iptv.refreshPlaylist(id);
      setPlaylists((prev) => prev.map((p) => (p.id === id ? updated : p)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh playlist');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await api.iptv.deletePlaylist(id);
      setPlaylists((prev) => prev.filter((p) => p.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete playlist');
    }
  };

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-[var(--text-primary)]">Playlists</h3>

      {error && (
        <div className="p-3 rounded-xl bg-red-500/15 border border-red-400/20 text-red-300 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-8 text-[var(--text-tertiary)] text-sm">Loading playlists...</div>
      ) : (
        <AnimatePresence mode="popLayout">
          {playlists.map((playlist) => (
            <motion.div
              key={playlist.id}
              layout
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="p-4 rounded-2xl bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)]"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-semibold text-[var(--text-primary)] truncate">{playlist.name}</h4>
                    <span
                      className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-medium border
                        ${STATUS_STYLES[playlist.status] ?? STATUS_STYLES.pending}`}
                    >
                      {playlist.status}
                    </span>
                  </div>
                  <p className="text-xs text-[var(--text-secondary)] mt-1 truncate">{playlist.url}</p>
                  <div className="flex gap-4 mt-1.5 text-xs text-[var(--text-tertiary)]">
                    <span>{playlist.channel_count} channels</span>
                    <span>Refreshed: {formatDate(playlist.last_refreshed)}</span>
                  </div>
                  {playlist.error_message && (
                    <p className="mt-2 text-xs text-red-400 bg-red-500/10 rounded-lg px-2 py-1">
                      {playlist.error_message}
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  <button
                    type="button"
                    onClick={() => handleRefresh(playlist.id)}
                    className="p-2 rounded-xl bg-[var(--glass-bg)] hover:bg-[var(--glass-hover-bg)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                    title="Refresh"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(playlist.id)}
                    className="p-2 rounded-xl bg-[var(--glass-bg)] hover:bg-red-500/20 text-[var(--text-secondary)] hover:text-red-300 transition-colors"
                    title="Delete"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      )}

      {/* Add Playlist Form */}
      <div className="p-4 rounded-2xl bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)] space-y-3">
        <h4 className="text-sm font-semibold text-[var(--text-primary)]">Add Playlist</h4>
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="Playlist name"
          className="w-full px-3 py-2 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] text-[var(--text-primary)] text-sm
            placeholder:text-[var(--text-tertiary)] focus:outline-none focus:ring-2 focus:ring-cyan-400/40"
        />
        <input
          type="url"
          value={newUrl}
          onChange={(e) => setNewUrl(e.target.value)}
          placeholder="M3U playlist URL"
          className="w-full px-3 py-2 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] text-[var(--text-primary)] text-sm
            placeholder:text-[var(--text-tertiary)] focus:outline-none focus:ring-2 focus:ring-cyan-400/40"
        />
        <motion.button
          type="button"
          onClick={handleAdd}
          disabled={adding || !newName.trim() || !newUrl.trim()}
          className="w-full px-4 py-2.5 rounded-xl bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300
            border border-cyan-400/20 text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.99 }}
        >
          {adding ? 'Adding...' : 'Add Playlist'}
        </motion.button>
      </div>
    </div>
  );
}
