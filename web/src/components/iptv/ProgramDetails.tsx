import { motion } from 'framer-motion';
import type { EPGProgram } from '../../types';
import { GlassModal } from '../ui/GlassModal';

interface ProgramDetailsProps {
  program: EPGProgram | null;
  isOpen: boolean;
  onClose: () => void;
  onRecord?: (program: EPGProgram) => void;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString([], {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });
}

export function ProgramDetails({ program, isOpen, onClose, onRecord }: ProgramDetailsProps) {
  if (!program) return null;

  const isCurrentlyAiring = (() => {
    const now = Date.now();
    return now >= new Date(program.start_time).getTime() && now <= new Date(program.end_time).getTime();
  })();

  return (
    <GlassModal isOpen={isOpen} onClose={onClose} className="max-w-xl">
      <div className="space-y-4">
        {/* Header */}
        <div className="flex justify-between items-start">
          <div>
            <h2 className="text-xl font-bold text-white">{program.title}</h2>
            {program.subtitle && (
              <p className="text-sm text-white/60 mt-0.5">{program.subtitle}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-xl bg-white/10 hover:bg-white/20 text-white/60 hover:text-white transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Poster */}
        {program.poster_url && (
          <div className="rounded-xl overflow-hidden">
            <img
              src={program.poster_url}
              alt={program.title}
              className="w-full h-48 object-cover"
            />
          </div>
        )}

        {/* Time + Category */}
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="px-2.5 py-1 rounded-lg bg-white/10 text-white/80 border border-white/10">
            {formatDate(program.start_time)}
          </span>
          <span className="px-2.5 py-1 rounded-lg bg-white/10 text-white/80 border border-white/10">
            {formatTime(program.start_time)} - {formatTime(program.end_time)}
          </span>
          <span className="px-2.5 py-1 rounded-lg bg-white/10 text-white/80 border border-white/10">
            {program.duration_minutes} min
          </span>
          {program.category && (
            <span className="px-2.5 py-1 rounded-lg bg-blue-500/20 text-blue-300 border border-blue-400/20">
              {program.category}
            </span>
          )}
          {isCurrentlyAiring && (
            <span className="px-2.5 py-1 rounded-lg bg-red-500/20 text-red-300 border border-red-400/20 animate-pulse">
              LIVE
            </span>
          )}
        </div>

        {/* Description */}
        {program.description && (
          <p className="text-sm text-white/70 leading-relaxed">{program.description}</p>
        )}

        {/* Actions */}
        <div className="flex gap-3 pt-2">
          {onRecord && (
            <motion.button
              type="button"
              onClick={() => onRecord(program)}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl
                bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-400/20
                text-sm font-medium transition-colors"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="8" />
              </svg>
              Record
            </motion.button>
          )}
          <motion.button
            type="button"
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl
              bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-400/20
              text-sm font-medium transition-colors"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Set Reminder
          </motion.button>
        </div>
      </div>
    </GlassModal>
  );
}
