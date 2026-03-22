import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import type { CacheStats } from '../../types';
import { api } from '../../api/client';

function formatSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

const GB = 1024 * 1024 * 1024;

export function CacheSettings() {
  const [stats, setStats] = useState<CacheStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [limitGB, setLimitGB] = useState(10);
  const [enabled, setEnabled] = useState(true);
  const [clearing, setClearing] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);

  const fetchStats = useCallback(async () => {
    try {
      setError(null);
      const data = await api.cache.stats();
      setStats(data);
      setLimitGB(Math.round(data.limit_bytes / GB));
      setEnabled(data.enabled);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load cache stats');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  const handleToggle = async () => {
    const newEnabled = !enabled;
    setEnabled(newEnabled);
    try {
      await api.cache.updateSettings({ enabled: newEnabled });
    } catch (err) {
      setEnabled(!newEnabled);
      setError(err instanceof Error ? err.message : 'Failed to update setting');
    }
  };

  const handleLimitChange = async (value: number) => {
    setLimitGB(value);
    try {
      await api.cache.updateSettings({ limit_bytes: value * GB });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update limit');
    }
  };

  const handleClear = async () => {
    if (!confirmClear) {
      setConfirmClear(true);
      return;
    }
    setClearing(true);
    try {
      await api.cache.clear();
      await fetchStats();
      setConfirmClear(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clear cache');
    } finally {
      setClearing(false);
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-8 text-[var(--text-tertiary)] text-sm">Loading cache stats...</div>;
  }

  return (
    <div className="space-y-5">
      <h3 className="text-lg font-semibold text-[var(--text-primary)]">Cache</h3>

      {error && (
        <div className="p-3 rounded-xl bg-red-500/15 border border-red-400/20 text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Enable Toggle */}
      <div className="flex items-center justify-between p-4 rounded-2xl bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)]">
        <div>
          <p className="text-sm font-medium text-[var(--text-primary)]">Enable Cache</p>
          <p className="text-xs text-[var(--text-tertiary)] mt-0.5">Cache video segments for offline playback</p>
        </div>
        <button
          type="button"
          onClick={handleToggle}
          className={`relative w-11 h-6 rounded-full transition-colors ${
            enabled ? 'bg-cyan-500' : 'bg-[var(--glass-border)]'
          }`}
        >
          <motion.div
            className="absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow"
            animate={{ x: enabled ? 20 : 0 }}
            transition={{ type: 'spring', stiffness: 500, damping: 30 }}
          />
        </button>
      </div>

      {/* Usage Progress */}
      {stats && (
        <div className="p-4 rounded-2xl bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)] space-y-3">
          <div className="flex justify-between text-sm">
            <span className="text-[var(--text-secondary)]">Used</span>
            <span className="text-[var(--text-primary)] font-medium">
              {formatSize(stats.used_bytes)} / {formatSize(stats.limit_bytes)}
            </span>
          </div>
          <div className="h-2 rounded-full bg-[var(--glass-bg)] overflow-hidden">
            <motion.div
              className={`h-full rounded-full ${
                stats.used_pct > 90
                  ? 'bg-gradient-to-r from-red-400 to-red-500'
                  : stats.used_pct > 70
                    ? 'bg-gradient-to-r from-amber-400 to-amber-500'
                    : 'bg-gradient-to-r from-cyan-400 to-blue-500'
              }`}
              initial={{ width: 0 }}
              animate={{ width: `${stats.used_pct}%` }}
              transition={{ duration: 0.5 }}
            />
          </div>
          <p className="text-xs text-[var(--text-tertiary)]">{stats.segment_count} cached segments</p>
        </div>
      )}

      {/* Cache Limit */}
      <div className="p-4 rounded-2xl bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)] space-y-3">
        <div className="flex justify-between items-center">
          <label className="text-sm font-medium text-[var(--text-primary)]">Cache Limit</label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              value={limitGB}
              onChange={(e) => {
                const val = Math.max(1, parseInt(e.target.value) || 1);
                handleLimitChange(val);
              }}
              min={1}
              max={500}
              className="w-16 px-2 py-1 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)] text-[var(--text-primary)] text-sm text-center
                focus:outline-none focus:ring-2 focus:ring-cyan-400/40"
            />
            <span className="text-sm text-[var(--text-tertiary)]">GB</span>
          </div>
        </div>
        <input
          type="range"
          value={limitGB}
          onChange={(e) => handleLimitChange(parseInt(e.target.value))}
          min={1}
          max={100}
          className="w-full h-1.5 rounded-full appearance-none bg-[var(--glass-bg)] accent-cyan-400
            [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full
            [&::-webkit-slider-thumb]:bg-cyan-400 [&::-webkit-slider-thumb]:appearance-none"
        />
        <div className="flex justify-between text-[10px] text-[var(--text-tertiary)]">
          <span>1 GB</span>
          <span>50 GB</span>
          <span>100 GB</span>
        </div>
      </div>

      {/* Location */}
      {stats && (
        <div className="flex items-center justify-between p-4 rounded-2xl bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)]">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-[var(--text-primary)]">Location</p>
            <p className="text-xs text-[var(--text-tertiary)] mt-0.5 truncate">{stats.cache_dir}</p>
          </div>
          <button
            type="button"
            className="px-3 py-1.5 rounded-lg bg-[var(--glass-bg)] hover:bg-[var(--glass-hover-bg)] text-[var(--text-secondary)] text-xs font-medium transition-colors shrink-0"
          >
            Change
          </button>
        </div>
      )}

      {/* Clear Cache */}
      <motion.button
        type="button"
        onClick={handleClear}
        disabled={clearing}
        className={`w-full px-4 py-2.5 rounded-xl text-sm font-medium transition-colors
          ${confirmClear
            ? 'bg-red-500/30 hover:bg-red-500/40 text-red-200 border border-red-400/30'
            : 'bg-[var(--glass-bg)] hover:bg-[var(--glass-hover-bg)] text-[var(--text-secondary)] border border-[var(--glass-border)]'
          }
          disabled:opacity-40 disabled:cursor-not-allowed`}
        whileHover={{ scale: 1.01 }}
        whileTap={{ scale: 0.99 }}
      >
        {clearing ? 'Clearing...' : confirmClear ? 'Confirm Clear Cache' : 'Clear Cache'}
      </motion.button>
      {confirmClear && (
        <p className="text-xs text-red-300/60 text-center -mt-2">
          This will remove all cached segments. Click again to confirm.
        </p>
      )}
    </div>
  );
}
