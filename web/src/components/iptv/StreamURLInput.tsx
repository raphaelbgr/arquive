import { useState } from 'react';
import { motion } from 'framer-motion';
import { GlassModal } from '../ui/GlassModal';

interface StreamURLInputProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (name: string, url: string, category: string) => void;
}

const CATEGORIES = [
  'General',
  'News',
  'Sports',
  'Movies',
  'Music',
  'Kids',
  'Documentary',
  'Entertainment',
  'Other',
];

const SUPPORTED_FORMATS = [
  { name: 'HLS', ext: '.m3u8', desc: 'HTTP Live Streaming - most common for IPTV' },
  { name: 'MPEG-TS', ext: '.ts', desc: 'MPEG Transport Stream - raw transport' },
  { name: 'RTMP', ext: 'rtmp://', desc: 'Real-Time Messaging Protocol - low latency' },
  { name: 'HTTP', ext: 'http(s)://', desc: 'Direct HTTP streams - progressive download' },
];

export function StreamURLInput({ isOpen, onClose, onAdd }: StreamURLInputProps) {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [category, setCategory] = useState('General');
  const [addToFavorites, setAddToFavorites] = useState(false);

  const handleSubmit = () => {
    if (!name.trim() || !url.trim()) return;
    onAdd(name.trim(), url.trim(), category);
    setName('');
    setUrl('');
    setCategory('General');
    setAddToFavorites(false);
    onClose();
  };

  return (
    <GlassModal isOpen={isOpen} onClose={onClose}>
      <div className="space-y-4">
        {/* Header */}
        <div className="flex justify-between items-center">
          <h2 className="text-lg font-bold text-white">Add Custom Stream</h2>
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

        {/* URL Input */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-white/60">Stream URL</label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/stream.m3u8"
            className="w-full px-3 py-2.5 rounded-xl bg-white/10 border border-white/10 text-white text-sm
              placeholder:text-white/30 focus:outline-none focus:ring-2 focus:ring-cyan-400/40"
          />
        </div>

        {/* Name Input */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-white/60">Channel Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="My Stream"
            className="w-full px-3 py-2.5 rounded-xl bg-white/10 border border-white/10 text-white text-sm
              placeholder:text-white/30 focus:outline-none focus:ring-2 focus:ring-cyan-400/40"
          />
        </div>

        {/* Category Dropdown */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-white/60">Category</label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full px-3 py-2.5 rounded-xl bg-white/10 border border-white/10 text-white text-sm
              focus:outline-none focus:ring-2 focus:ring-cyan-400/40 [&>option]:bg-gray-900"
          >
            {CATEGORIES.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        </div>

        {/* Add to Favorites */}
        <label className="flex items-center gap-2.5 cursor-pointer">
          <input
            type="checkbox"
            checked={addToFavorites}
            onChange={(e) => setAddToFavorites(e.target.checked)}
            className="w-4 h-4 rounded bg-white/10 border-white/20 text-cyan-400 focus:ring-cyan-400/40"
          />
          <span className="text-sm text-white/70">Add to favorites</span>
        </label>

        {/* Supported Formats Info */}
        <div className="p-3 rounded-xl bg-white/5 border border-white/10 space-y-2">
          <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider">Supported Formats</h4>
          <div className="grid grid-cols-2 gap-2">
            {SUPPORTED_FORMATS.map((fmt) => (
              <div key={fmt.name} className="space-y-0.5">
                <span className="text-xs font-medium text-cyan-300">{fmt.name}</span>
                <p className="text-[10px] text-white/40">{fmt.desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-3 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-xl bg-white/10 hover:bg-white/15 text-white/60
              text-sm font-medium transition-colors"
          >
            Cancel
          </button>
          <motion.button
            type="button"
            onClick={handleSubmit}
            disabled={!name.trim() || !url.trim()}
            className="flex-1 px-4 py-2.5 rounded-xl bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300
              border border-cyan-400/20 text-sm font-medium transition-colors
              disabled:opacity-40 disabled:cursor-not-allowed"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            Add Stream
          </motion.button>
        </div>
      </div>
    </GlassModal>
  );
}
