import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import type { FleetNode } from '../../types';
import { api } from '../../api/client';

export function FleetStatus() {
  const [nodes, setNodes] = useState<FleetNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchNodes = useCallback(async () => {
    try {
      setError(null);
      const data = await api.fleet.nodes() as unknown as { nodes: FleetNode[] };
      setNodes(data.nodes);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load fleet status');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNodes();
  }, [fetchNodes]);

  if (loading) {
    return <div className="flex items-center justify-center py-8 text-[var(--text-tertiary)] text-sm">Loading fleet status...</div>;
  }

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-[var(--text-primary)]">GPU Fleet</h3>

      {error && (
        <div className="p-3 rounded-xl bg-red-500/15 border border-red-400/20 text-red-300 text-sm">{error}</div>
      )}

      {nodes.length === 0 && !error ? (
        <p className="text-sm text-[var(--text-tertiary)] text-center py-4">No fleet nodes configured</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {nodes.map((node) => (
            <motion.div
              key={node.name}
              className="p-4 rounded-2xl bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)]"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              whileHover={{ scale: 1.01 }}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h4 className="text-sm font-semibold text-[var(--text-primary)] truncate">{node.name}</h4>
                  <p className="text-xs text-[var(--text-tertiary)] font-mono mt-0.5">{node.host}</p>
                </div>
                <span
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium border shrink-0
                    ${node.online
                      ? 'bg-green-500/20 text-green-300 border-green-400/20'
                      : 'bg-red-500/20 text-red-300 border-red-400/20'
                    }`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${node.online ? 'bg-green-400' : 'bg-red-400'}`} />
                  {node.online ? 'Online' : 'Offline'}
                </span>
              </div>

              <div className="mt-3 flex items-center gap-2">
                <svg className="w-4 h-4 text-[var(--text-tertiary)] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
                </svg>
                <span className="text-xs text-[var(--text-secondary)]">{node.gpu}</span>
              </div>

              {node.online && (
                <div className="mt-3">
                  <div className="flex justify-between text-[10px] text-[var(--text-tertiary)] mb-1">
                    <span>GPU Utilization</span>
                    <span>--</span>
                  </div>
                  <div className="h-1 rounded-full bg-[var(--glass-bg)] overflow-hidden">
                    <div className="h-full rounded-full bg-[var(--glass-border)] w-0" />
                  </div>
                </div>
              )}
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
