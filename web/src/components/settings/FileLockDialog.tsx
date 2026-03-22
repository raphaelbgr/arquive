import { useState } from 'react';
import { motion } from 'framer-motion';
import { GlassModal } from '../ui/GlassModal';

interface FileLockDialogProps {
  processName: string;
  pid: number;
  filePath: string;
  command: string;
  onRetry: () => void;
  onSkip: () => void;
  onClose: () => void;
}

export function FileLockDialog({ processName, pid, filePath, command, onRetry, onSkip, onClose }: FileLockDialogProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API may fail in some contexts
    }
  };

  return (
    <GlassModal isOpen={true} onClose={onClose}>
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-start gap-3">
          <div className="p-2.5 rounded-xl bg-amber-500/20 border border-amber-400/20 shrink-0">
            <svg className="w-5 h-5 text-amber-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg font-bold text-white">File Locked</h2>
            <p className="text-sm text-white/50 mt-0.5">A process is preventing access to this file</p>
          </div>
        </div>

        {/* Process Info */}
        <div className="p-3 rounded-xl bg-white/5 border border-white/10 space-y-2">
          <div className="flex justify-between">
            <span className="text-xs text-white/40">Process</span>
            <span className="text-xs text-white/70 font-medium">{processName}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-xs text-white/40">PID</span>
            <span className="text-xs text-white/70 font-mono">{pid}</span>
          </div>
          <div>
            <span className="text-xs text-white/40">File</span>
            <p className="text-xs text-white/70 font-mono mt-0.5 break-all">{filePath}</p>
          </div>
        </div>

        {/* Kill Command */}
        <div className="space-y-1.5">
          <p className="text-xs text-white/40">To release the lock, run:</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 px-3 py-2 rounded-lg bg-black/30 border border-white/10 text-xs text-amber-300 font-mono truncate">
              {command}
            </code>
            <motion.button
              type="button"
              onClick={handleCopy}
              className="p-2 rounded-lg bg-white/10 hover:bg-white/20 text-white/60 hover:text-white transition-colors shrink-0"
              title="Copy command"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              {copied ? (
                <svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              )}
            </motion.button>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-3 pt-1">
          <button
            type="button"
            onClick={onSkip}
            className="flex-1 px-4 py-2.5 rounded-xl bg-white/10 hover:bg-white/15 text-white/60 text-sm font-medium transition-colors"
          >
            Skip
          </button>
          <motion.button
            type="button"
            onClick={onRetry}
            className="flex-1 px-4 py-2.5 rounded-xl bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300
              border border-cyan-400/20 text-sm font-medium transition-colors"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            Retry
          </motion.button>
        </div>
      </div>
    </GlassModal>
  );
}
