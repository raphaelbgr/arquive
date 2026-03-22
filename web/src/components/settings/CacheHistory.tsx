import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface CacheLocation {
  path: string;
  size: number;
  isCurrent: boolean;
  hasData: boolean;
}

interface CacheHistoryProps {
  locations?: CacheLocation[];
  currentPath: string;
}

function formatSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

const DEFAULT_LOCATIONS: CacheLocation[] = [];

export function CacheHistory({ locations = DEFAULT_LOCATIONS, currentPath }: CacheHistoryProps) {
  const [items, setItems] = useState<CacheLocation[]>(locations);

  const handleDelete = (path: string) => {
    setItems((prev) => prev.filter((loc) => loc.path !== path));
  };

  const allLocations: CacheLocation[] = [
    { path: currentPath, size: 0, isCurrent: true, hasData: true },
    ...items.filter((loc) => loc.path !== currentPath),
  ];

  return (
    <div className="space-y-3">
      <h3 className="text-lg font-semibold text-white">Cache Locations</h3>

      <AnimatePresence mode="popLayout">
        {allLocations.map((loc) => (
          <motion.div
            key={loc.path}
            layout
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className={`
              p-4 rounded-2xl backdrop-blur-xl border
              ${loc.isCurrent
                ? 'bg-cyan-500/10 border-cyan-400/20'
                : 'bg-white/10 dark:bg-white/5 border-white/20 dark:border-white/10'
              }
            `}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-mono text-white/80 truncate">{loc.path}</p>
                  {loc.isCurrent && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-cyan-500/20 text-cyan-300 border border-cyan-400/20 shrink-0">
                      Current
                    </span>
                  )}
                </div>
                {loc.size > 0 && (
                  <p className="text-xs text-white/40 mt-1">{formatSize(loc.size)}</p>
                )}
              </div>

              {!loc.isCurrent && loc.hasData && (
                <button
                  type="button"
                  onClick={() => handleDelete(loc.path)}
                  className="p-2 rounded-xl bg-white/10 hover:bg-red-500/20 text-white/60 hover:text-red-300 transition-colors shrink-0"
                  title="Delete old cache"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              )}
            </div>
          </motion.div>
        ))}
      </AnimatePresence>

      {allLocations.length <= 1 && (
        <p className="text-xs text-white/30 text-center py-2">No previous cache locations</p>
      )}
    </div>
  );
}
