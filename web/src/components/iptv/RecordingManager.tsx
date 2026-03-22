import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { Recording } from '../../types';
import { api } from '../../api/client';

function formatSize(bytes: number | null): string {
  if (bytes === null || bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}



function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function RecordingManager() {
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRecordings = useCallback(async () => {
    try {
      setError(null);
      const data = await api.iptv.recordings() as unknown as { recordings: Recording[] };
      setRecordings(data.recordings);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load recordings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRecordings();
  }, [fetchRecordings]);

  const handleStop = async (id: number) => {
    try {
      const updated = await api.iptv.stopRecording(id);
      setRecordings((prev) => prev.map((r) => (r.id === id ? updated : r)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop recording');
    }
  };

  const active = recordings.filter((r) => r.status === 'recording');
  const scheduled = recordings.filter((r) => r.status === 'scheduled');
  const completed = recordings.filter((r) => r.status === 'completed');

  const renderSection = (title: string, items: Recording[], type: 'active' | 'scheduled' | 'completed') => (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold text-[var(--text-secondary)] flex items-center gap-2">
        {title}
        <span className="px-1.5 py-0.5 rounded-md bg-[var(--glass-bg)] text-[10px] text-[var(--text-tertiary)]">{items.length}</span>
      </h4>
      {items.length === 0 ? (
        <p className="text-xs text-[var(--text-tertiary)] py-2">No {title.toLowerCase()}</p>
      ) : (
        <AnimatePresence mode="popLayout">
          {items.map((rec) => (
            <motion.div
              key={rec.id}
              layout
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="p-3 rounded-xl bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)]"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <h5 className="text-sm font-medium text-[var(--text-primary)] truncate">{rec.program_title}</h5>
                  <div className="flex gap-3 mt-1 text-xs text-[var(--text-tertiary)]">
                    <span>{formatTime(rec.scheduled_start)} - {formatTime(rec.scheduled_end)}</span>
                    {type === 'completed' && rec.file_size && (
                      <span>{formatSize(rec.file_size)}</span>
                    )}
                  </div>
                  {type === 'active' && (
                    <div className="mt-2">
                      <div className="h-1 rounded-full bg-[var(--glass-bg)] overflow-hidden">
                        <motion.div
                          className="h-full rounded-full bg-gradient-to-r from-red-400 to-red-500"
                          initial={{ width: '0%' }}
                          animate={{ width: '60%' }}
                          transition={{ duration: 1 }}
                        />
                      </div>
                      <p className="text-[10px] text-red-400 mt-0.5 animate-pulse">Recording...</p>
                    </div>
                  )}
                  {type === 'completed' && (
                    <p className="text-[10px] text-[var(--text-tertiary)] mt-1 truncate">{rec.output_path}</p>
                  )}
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  {type === 'active' && (
                    <button
                      type="button"
                      onClick={() => handleStop(rec.id)}
                      className="px-3 py-1.5 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-300
                        text-xs font-medium transition-colors"
                    >
                      Stop
                    </button>
                  )}
                  {type === 'scheduled' && (
                    <button
                      type="button"
                      onClick={() => handleStop(rec.id)}
                      className="px-3 py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-300
                        text-xs font-medium transition-colors"
                    >
                      Cancel
                    </button>
                  )}
                  {type === 'completed' && (
                    <>
                      <button
                        type="button"
                        className="p-2 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 transition-colors"
                        title="Play"
                      >
                        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M8 5v14l11-7z" />
                        </svg>
                      </button>
                      <button
                        type="button"
                        className="p-2 rounded-lg bg-[var(--glass-bg)] hover:bg-red-500/20 text-[var(--text-secondary)] hover:text-red-300 transition-colors"
                        title="Delete"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </>
                  )}
                </div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      )}
    </div>
  );

  if (loading) {
    return <div className="flex items-center justify-center py-8 text-[var(--text-tertiary)] text-sm">Loading recordings...</div>;
  }

  return (
    <div className="space-y-6">
      <h3 className="text-lg font-semibold text-[var(--text-primary)]">Recordings</h3>

      {error && (
        <div className="p-3 rounded-xl bg-red-500/15 border border-red-400/20 text-red-300 text-sm">
          {error}
        </div>
      )}

      {renderSection('Active', active, 'active')}
      {renderSection('Scheduled', scheduled, 'scheduled')}
      {renderSection('Completed', completed, 'completed')}

      {recordings.length > 0 && completed.length > 0 && (
        <p className="text-xs text-[var(--text-tertiary)]">
          Storage: {completed[0]?.output_path?.split('/').slice(0, -1).join('/')}
        </p>
      )}
    </div>
  );
}
