import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import type { Channel } from '../../types';
import { api } from '../../api/client';
import { ChannelList } from '../iptv/ChannelList';
import { EPGGrid } from '../iptv/EPGGrid';

export function LiveTVView() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [selectedChannel, setSelectedChannel] = useState<Channel | null>(null);

  useEffect(() => {
    api.iptv
      .channels({})
      .then((data) => setChannels((data.channels ?? []) as unknown as Channel[]))
      .catch(() => {});
  }, []);

  return (
    <motion.div
      className="flex h-full"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* Left: Channel list */}
      <div className="w-72 shrink-0 border-r border-[var(--glass-border)] overflow-hidden flex flex-col">
        <ChannelList />
      </div>

      {/* Right: Player + EPG */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Video player area */}
        <div className="relative aspect-video max-h-[50vh] bg-black/30 flex items-center justify-center border-b border-[var(--glass-border)]">
          {selectedChannel ? (
            <div className="text-center">
              <p className="text-sm text-[var(--text-secondary)] font-medium">{selectedChannel.name}</p>
              <p className="text-xs text-[var(--text-tertiary)] mt-1">Stream loading...</p>
            </div>
          ) : (
            <div className="text-center">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="mx-auto mb-3 text-[var(--text-tertiary)]">
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              <p className="text-sm text-[var(--text-tertiary)]">Select a channel to start watching</p>
              <span className="inline-block mt-2 text-[10px] px-3 py-1 rounded-full" style={{ background: 'var(--glass-bg)', color: 'var(--text-tertiary)', border: '1px solid var(--glass-border)' }}>Coming Soon</span>
            </div>
          )}
        </div>

        {/* EPG area */}
        <div className="flex-1 overflow-y-auto p-4">
          <EPGGrid
            channels={channels}
            onChannelClick={(ch) => setSelectedChannel(ch)}
          />
        </div>
      </div>
    </motion.div>
  );
}
