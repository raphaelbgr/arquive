import { useState } from 'react';
import { motion } from 'framer-motion';
import { GlassModal } from '../ui/GlassModal';
import { api } from '../../api/client';

interface CacheLocationDialogProps {
  isOpen: boolean;
  onClose: () => void;
  currentPath: string;
}

type MoveOption = 'move' | 'delete' | 'clean';

export function CacheLocationDialog({ isOpen, onClose, currentPath }: CacheLocationDialogProps) {
  const [newPath, setNewPath] = useState('');
  const [selectedOption, setSelectedOption] = useState<MoveOption>('move');
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const options: { id: MoveOption; title: string; description: string; icon: string }[] = [
    {
      id: 'move',
      title: 'Move Cache',
      description: 'Move all cached data to the new location. Existing cache will be preserved.',
      icon: 'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4',
    },
    {
      id: 'delete',
      title: 'Delete Cache',
      description: 'Delete all cached data from the current location and start fresh at the new path.',
      icon: 'M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16',
    },
    {
      id: 'clean',
      title: 'Start Clean',
      description: 'Use the new location with an empty cache. Old cache remains at the previous path.',
      icon: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15',
    },
  ];

  const handleApply = async () => {
    if (!newPath.trim()) return;
    setProcessing(true);
    setError(null);
    try {
      await api.cache.move(newPath.trim());
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to change cache location');
    } finally {
      setProcessing(false);
    }
  };

  return (
    <GlassModal isOpen={isOpen} onClose={onClose}>
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <h2 className="text-lg font-bold text-white">Change Cache Location</h2>
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

        {/* Current Path */}
        <div className="p-3 rounded-xl bg-white/5 border border-white/10">
          <p className="text-xs text-white/40">Current location</p>
          <p className="text-sm text-white/70 mt-0.5 font-mono truncate">{currentPath}</p>
        </div>

        {/* New Path Input */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-white/60">New location</label>
          <input
            type="text"
            value={newPath}
            onChange={(e) => setNewPath(e.target.value)}
            placeholder="/path/to/new/cache"
            className="w-full px-3 py-2.5 rounded-xl bg-white/10 border border-white/10 text-white text-sm font-mono
              placeholder:text-white/30 focus:outline-none focus:ring-2 focus:ring-cyan-400/40"
          />
        </div>

        {/* Options */}
        <div className="space-y-2">
          {options.map((opt) => (
            <button
              key={opt.id}
              type="button"
              onClick={() => setSelectedOption(opt.id)}
              className={`
                w-full flex items-start gap-3 p-3 rounded-xl text-left transition-colors
                ${selectedOption === opt.id
                  ? 'bg-cyan-500/15 border border-cyan-400/30'
                  : 'bg-white/5 border border-white/10 hover:bg-white/10'
                }
              `}
            >
              <svg className={`w-5 h-5 shrink-0 mt-0.5 ${selectedOption === opt.id ? 'text-cyan-300' : 'text-white/40'}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d={opt.icon} />
              </svg>
              <div>
                <p className={`text-sm font-medium ${selectedOption === opt.id ? 'text-cyan-300' : 'text-white/70'}`}>
                  {opt.title}
                </p>
                <p className="text-xs text-white/40 mt-0.5">{opt.description}</p>
              </div>
            </button>
          ))}
        </div>

        {error && (
          <div className="p-3 rounded-xl bg-red-500/15 border border-red-400/20 text-red-300 text-sm">{error}</div>
        )}

        {/* Actions */}
        <div className="flex gap-3 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-xl bg-white/10 hover:bg-white/15 text-white/60 text-sm font-medium transition-colors"
          >
            Cancel
          </button>
          <motion.button
            type="button"
            onClick={handleApply}
            disabled={processing || !newPath.trim()}
            className="flex-1 px-4 py-2.5 rounded-xl bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300
              border border-cyan-400/20 text-sm font-medium transition-colors
              disabled:opacity-40 disabled:cursor-not-allowed"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            {processing ? 'Processing...' : 'Apply'}
          </motion.button>
        </div>
      </div>
    </GlassModal>
  );
}
