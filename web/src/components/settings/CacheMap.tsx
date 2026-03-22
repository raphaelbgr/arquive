import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { CacheStats } from '../../types';
import { api } from '../../api/client';

function formatSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

interface CacheEntry {
  name: string;
  type: 'video' | 'quality' | 'segment';
  size: number;
  count: number;
  children?: CacheEntry[];
}

function buildMockTree(stats: CacheStats): CacheEntry[] {
  // Build a summary tree from available stats
  const segmentsPerVideo = Math.max(1, Math.ceil(stats.segment_count / 3));
  const sizePerVideo = Math.ceil(stats.used_bytes / 3);

  return [
    {
      name: 'Video Cache',
      type: 'video',
      size: stats.used_bytes,
      count: stats.segment_count,
      children: stats.segment_count > 0
        ? [
            { name: '1080p', type: 'quality', size: Math.ceil(sizePerVideo * 0.6), count: Math.ceil(segmentsPerVideo * 0.4) },
            { name: '720p', type: 'quality', size: Math.ceil(sizePerVideo * 0.3), count: Math.ceil(segmentsPerVideo * 0.4) },
            { name: '480p', type: 'quality', size: Math.ceil(sizePerVideo * 0.1), count: Math.ceil(segmentsPerVideo * 0.2) },
          ]
        : [],
    },
  ];
}

function TreeNode({ entry, depth = 0 }: { entry: CacheEntry; depth?: number }) {
  const [expanded, setExpanded] = useState(depth === 0);
  const hasChildren = entry.children && entry.children.length > 0;

  return (
    <div>
      <button
        type="button"
        onClick={() => hasChildren && setExpanded(!expanded)}
        className={`
          w-full flex items-center gap-2 px-3 py-2 rounded-xl text-left transition-colors
          hover:bg-white/10 ${hasChildren ? 'cursor-pointer' : 'cursor-default'}
        `}
        style={{ paddingLeft: `${depth * 16 + 12}px` }}
      >
        {hasChildren && (
          <motion.svg
            className="w-3.5 h-3.5 text-white/40 shrink-0"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
            animate={{ rotate: expanded ? 90 : 0 }}
            transition={{ duration: 0.15 }}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </motion.svg>
        )}
        {!hasChildren && <span className="w-3.5 shrink-0" />}

        <span className="text-sm text-white flex-1 truncate">{entry.name}</span>
        <span className="text-xs text-white/40 shrink-0">{entry.count} segments</span>
        <span className="text-xs text-white/50 font-medium shrink-0">{formatSize(entry.size)}</span>
      </button>

      <AnimatePresence>
        {expanded && hasChildren && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            {entry.children!.map((child) => (
              <TreeNode key={child.name} entry={child} depth={depth + 1} />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function CacheMap() {
  const [stats, setStats] = useState<CacheStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = useCallback(async () => {
    try {
      setError(null);
      const data = await api.cache.stats();
      setStats(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load cache data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  if (loading) {
    return <div className="flex items-center justify-center py-8 text-white/40 text-sm">Loading cache map...</div>;
  }

  if (error) {
    return (
      <div className="p-3 rounded-xl bg-red-500/15 border border-red-400/20 text-red-300 text-sm">{error}</div>
    );
  }

  if (!stats) return null;

  const tree = buildMockTree(stats);

  return (
    <div className="space-y-3">
      <h3 className="text-lg font-semibold text-white">Cache Contents</h3>

      <div className="rounded-2xl bg-white/10 dark:bg-white/5 backdrop-blur-xl border border-white/20 dark:border-white/10 py-2">
        {tree.length === 0 ? (
          <p className="text-sm text-white/30 text-center py-4">Cache is empty</p>
        ) : (
          tree.map((entry) => <TreeNode key={entry.name} entry={entry} />)
        )}
      </div>

      <div className="flex justify-between text-xs text-white/30 px-1">
        <span>Total: {formatSize(stats.used_bytes)}</span>
        <span>{stats.segment_count} segments</span>
      </div>
    </div>
  );
}
