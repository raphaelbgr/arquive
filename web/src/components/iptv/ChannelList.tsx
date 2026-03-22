import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import type { Channel } from '../../types';
import { api } from '../../api/client';

export function ChannelList() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [favorites, setFavorites] = useState<Channel[]>([]);
  const [groups, setGroups] = useState<string[]>([]);
  const [selectedGroup, setSelectedGroup] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.iptv.channels().then((res) => (res.channels ?? []) as unknown as Channel[]),
      api.iptv.favorites().then((res) => (res.channels ?? []) as unknown as Channel[]),
      api.iptv.groups().then((res) => (res.groups ?? []).map((g: { group_title: string }) => g.group_title)),
    ])
      .then(([ch, fav, grp]) => {
        setChannels(ch);
        setFavorites(fav);
        setGroups(grp);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleToggleFavorite = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.iptv.toggleFavorite(id);
      const updated = await api.iptv.favorites();
      setFavorites((updated.channels ?? []) as unknown as Channel[]);
    } catch {
      // Silently fail
    }
  };

  const filteredChannels = channels.filter((ch) => {
    const matchesGroup = selectedGroup === 'all' || ch.group_title === selectedGroup;
    const matchesSearch =
      !searchQuery || ch.name.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesGroup && matchesSearch;
  });

  const isFavorite = (id: number) => favorites.some((f) => f.id === id);

  return (
    <div className="flex flex-col h-full">
      {/* Search */}
      <div className="p-3 border-b border-[var(--glass-border)]">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search channels..."
          className="
            w-full h-8 px-3
            bg-[var(--glass-bg)] border border-[var(--glass-border)]
            rounded-lg text-xs text-[var(--text-primary)]
            placeholder:text-[var(--text-tertiary)]
            outline-none focus:border-[var(--glass-border)]
            transition-colors
          "
        />
      </div>

      {/* Group filter */}
      <div className="px-3 py-2 border-b border-[var(--glass-border)] overflow-x-auto">
        <div className="flex gap-1.5">
          <button
            type="button"
            onClick={() => setSelectedGroup('all')}
            className={`
              px-2.5 py-1 rounded-full text-[10px] font-medium whitespace-nowrap transition-colors
              ${selectedGroup === 'all' ? 'bg-[#007AFF]/20 text-[#007AFF]' : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'}
            `}
          >
            All
          </button>
          {groups.map((group) => (
            <button
              key={group}
              type="button"
              onClick={() => setSelectedGroup(group)}
              className={`
                px-2.5 py-1 rounded-full text-[10px] font-medium whitespace-nowrap transition-colors
                ${selectedGroup === group ? 'bg-[#007AFF]/20 text-[#007AFF]' : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'}
              `}
            >
              {group}
            </button>
          ))}
        </div>
      </div>

      {/* Favorites section */}
      {favorites.length > 0 && (
        <div className="border-b border-[var(--glass-border)]">
          <div className="px-3 pt-2 pb-1">
            <span className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-tertiary)]">
              Favorites
            </span>
          </div>
          {favorites.map((ch) => (
            <ChannelItem
              key={ch.id}
              channel={ch}
              isSelected={selectedId === ch.id}
              isFavorite={true}
              onSelect={() => setSelectedId(ch.id)}
              onToggleFavorite={(e) => handleToggleFavorite(ch.id, e)}
            />
          ))}
        </div>
      )}

      {/* All channels */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-3 space-y-2">
            {Array.from({ length: 10 }).map((_, i) => (
              <div key={i} className="shimmer h-10 rounded-lg" />
            ))}
          </div>
        ) : filteredChannels.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-[var(--text-tertiary)] text-xs">
            No channels found
          </div>
        ) : (
          filteredChannels.map((ch) => (
            <ChannelItem
              key={ch.id}
              channel={ch}
              isSelected={selectedId === ch.id}
              isFavorite={isFavorite(ch.id)}
              onSelect={() => setSelectedId(ch.id)}
              onToggleFavorite={(e) => handleToggleFavorite(ch.id, e)}
            />
          ))
        )}
      </div>
    </div>
  );
}

function ChannelItem({
  channel,
  isSelected,
  isFavorite,
  onSelect,
  onToggleFavorite,
}: {
  channel: Channel;
  isSelected: boolean;
  isFavorite: boolean;
  onSelect: () => void;
  onToggleFavorite: (e: React.MouseEvent) => void;
}) {
  return (
    <motion.button
      type="button"
      onClick={onSelect}
      className={`
        w-full flex items-center gap-2.5 px-3 py-2 text-left
        transition-colors
        ${isSelected ? 'bg-[var(--glass-bg)]' : 'hover:bg-[var(--glass-hover-bg)]'}
      `}
      whileTap={{ scale: 0.98 }}
    >
      {/* Channel logo */}
      <div className="w-8 h-8 rounded-lg bg-[var(--glass-bg)] flex items-center justify-center shrink-0 overflow-hidden">
        {channel.logo_url ? (
          <img src={channel.logo_url} alt="" className="w-full h-full object-contain" />
        ) : (
          <span className="text-[10px] font-bold text-[var(--text-tertiary)]">TV</span>
        )}
      </div>

      <span className="flex-1 text-xs font-medium text-[var(--text-secondary)] truncate">{channel.name}</span>

      <button
        type="button"
        onClick={onToggleFavorite}
        className={`
          shrink-0 text-xs transition-colors
          ${isFavorite ? 'text-yellow-400' : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'}
        `}
        title={isFavorite ? 'Remove from favorites' : 'Add to favorites'}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill={isFavorite ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2">
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
        </svg>
      </button>
    </motion.button>
  );
}
