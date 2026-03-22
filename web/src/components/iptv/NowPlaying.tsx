import { motion } from 'framer-motion';

interface NowPlayingProps {
  channelName: string;
  programTitle: string;
  nextProgram?: string;
  nextTime?: string;
  onRecord?: () => void;
  onTimeshift?: () => void;
  onInfo?: () => void;
}

export function NowPlaying({
  channelName,
  programTitle,
  nextProgram,
  nextTime,
  onRecord,
  onTimeshift,
  onInfo,
}: NowPlayingProps) {
  return (
    <motion.div
      className="w-full rounded-2xl p-4 bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)]"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className="flex items-center justify-between gap-4">
        {/* Program Info */}
        <div className="flex-1 min-w-0">
          <p className="text-xs text-[var(--text-tertiary)] font-medium uppercase tracking-wider">{channelName}</p>
          <p className="text-sm font-semibold text-[var(--text-primary)] mt-0.5 truncate">Now: {programTitle}</p>
          {nextProgram && (
            <p className="text-xs text-[var(--text-secondary)] mt-0.5 truncate">
              Next: {nextProgram}
              {nextTime && <span className="text-[var(--text-tertiary)]"> ({nextTime})</span>}
            </p>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-1.5 shrink-0">
          {onRecord && (
            <motion.button
              type="button"
              onClick={onRecord}
              className="p-2.5 rounded-xl bg-red-500/20 hover:bg-red-500/30 text-red-300 transition-colors"
              title="Record"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="8" />
              </svg>
            </motion.button>
          )}

          {onTimeshift && (
            <motion.button
              type="button"
              onClick={onTimeshift}
              className="p-2.5 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 transition-colors"
              title="Timeshift"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </motion.button>
          )}

          {onInfo && (
            <motion.button
              type="button"
              onClick={onInfo}
              className="p-2.5 rounded-xl bg-[var(--glass-bg)] hover:bg-[var(--glass-hover-bg)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              title="Program Info"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </motion.button>
          )}
        </div>
      </div>
    </motion.div>
  );
}
