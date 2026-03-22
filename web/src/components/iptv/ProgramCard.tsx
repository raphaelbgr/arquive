import { useMemo } from 'react';
import { motion } from 'framer-motion';
import type { EPGProgram } from '../../types';

interface ProgramCardProps {
  program: EPGProgram;
  isNowPlaying?: boolean;
  onClick?: (program: EPGProgram) => void;
}

const CATEGORY_COLORS: Record<string, string> = {
  news: 'bg-blue-500/30 text-blue-300 border-blue-400/30',
  sports: 'bg-green-500/30 text-green-300 border-green-400/30',
  movies: 'bg-purple-500/30 text-purple-300 border-purple-400/30',
  series: 'bg-amber-500/30 text-amber-300 border-amber-400/30',
  music: 'bg-pink-500/30 text-pink-300 border-pink-400/30',
  kids: 'bg-orange-500/30 text-orange-300 border-orange-400/30',
  documentary: 'bg-teal-500/30 text-teal-300 border-teal-400/30',
};

function getCategoryStyle(category: string | null): string {
  if (!category) return 'bg-gray-500/30 text-gray-300 border-gray-400/30';
  const key = category.toLowerCase();
  for (const [k, v] of Object.entries(CATEGORY_COLORS)) {
    if (key.includes(k)) return v;
  }
  return 'bg-gray-500/30 text-gray-300 border-gray-400/30';
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function ProgramCard({ program, isNowPlaying = false, onClick }: ProgramCardProps) {
  const progress = useMemo(() => {
    if (!isNowPlaying) return 0;
    const now = Date.now();
    const start = new Date(program.start_time).getTime();
    const end = new Date(program.end_time).getTime();
    if (end <= start) return 0;
    return Math.min(100, Math.max(0, ((now - start) / (end - start)) * 100));
  }, [isNowPlaying, program.start_time, program.end_time]);

  return (
    <motion.button
      type="button"
      onClick={() => onClick?.(program)}
      className={`
        w-full text-left rounded-2xl p-4 transition-colors
        bg-[var(--glass-bg)] backdrop-blur-xl
        border border-[var(--glass-border)]
        hover:bg-[var(--glass-hover-bg)]
        ${isNowPlaying ? 'ring-2 ring-cyan-400/50' : ''}
      `}
      whileHover={{ scale: 1.01 }}
      whileTap={{ scale: 0.99 }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-[var(--text-primary)] truncate">{program.title}</h3>
          <p className="text-xs text-[var(--text-secondary)] mt-0.5">
            {formatTime(program.start_time)} - {formatTime(program.end_time)}
          </p>
        </div>

        {program.category && (
          <span
            className={`
              inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium
              border shrink-0 ${getCategoryStyle(program.category)}
            `}
          >
            {program.category}
          </span>
        )}
      </div>

      {isNowPlaying && (
        <div className="mt-3">
          <div className="h-1 rounded-full bg-[var(--glass-bg)] overflow-hidden">
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-blue-500"
              initial={{ width: 0 }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.5 }}
            />
          </div>
          <p className="text-[10px] text-cyan-400 mt-1">{Math.round(progress)}% complete</p>
        </div>
      )}
    </motion.button>
  );
}
