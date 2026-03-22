import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export interface Filters {
  mime_filter?: string;      // "image", "video", "audio"
  resolution?: string;       // "sd", "hd", "fullhd", "2k", "4k", "8k"
  orientation?: string;      // "h", "v"
  min_size?: number;
  max_size?: number;
  date_from?: string;
  date_to?: string;
  codec?: string;
}

interface FilterCounts {
  images: number;
  videos: number;
  audio: number;
  documents: number;
  horizontal: number;
  vertical: number;
  sd: number;
  hd: number;
  fullhd: number;
  '2k': number;
  '4k': number;
  '8k': number;
  small: number;
  medium: number;
  large: number;
}

interface FilterBarProps {
  filters: Filters;
  onChange: (filters: Filters) => void;
}

const CHIP_STYLE = {
  active: 'text-white',
  inactive: 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
  base: 'px-2.5 py-1 text-[10px] font-semibold rounded-lg cursor-pointer transition-all whitespace-nowrap select-none',
};

function Chip({ label, count, active, onClick, color }: {
  label: string;
  count?: number;
  active: boolean;
  onClick: () => void;
  color?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`${CHIP_STYLE.base} ${active ? CHIP_STYLE.active : CHIP_STYLE.inactive}`}
      style={active ? {
        background: color || 'var(--accent-color)',
      } : {
        background: 'var(--glass-bg)',
        border: '1px solid var(--glass-border)',
      }}
    >
      {label}
      {count !== undefined && count > 0 && (
        <span className={`ml-1 ${active ? 'opacity-70' : 'opacity-40'}`}>
          {count >= 1000 ? `${(count / 1000).toFixed(0)}k` : count}
        </span>
      )}
    </button>
  );
}

export function FilterBar({ filters, onChange }: FilterBarProps) {
  const [counts, setCounts] = useState<FilterCounts | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    fetch('/api/v1/media/filter-counts', { credentials: 'include' })
      .then(r => r.json())
      .then(setCounts)
      .catch(() => {});
  }, []);

  const toggle = useCallback((key: keyof Filters, value: string) => {
    const current = filters[key];
    if (current === value) {
      const next = { ...filters };
      delete next[key];
      onChange(next);
    } else {
      onChange({ ...filters, [key]: value });
    }
  }, [filters, onChange]);

  const clearAll = () => onChange({});
  const activeCount = Object.keys(filters).length;

  return (
    <div className="mb-4">
      {/* Main filter row */}
      <div className="flex items-center gap-1.5 flex-wrap">
        {/* Type filters */}
        <Chip label="Images" count={counts?.images} active={filters.mime_filter === 'image'} onClick={() => toggle('mime_filter', 'image')} color="#10b981" />
        <Chip label="Videos" count={counts?.videos} active={filters.mime_filter === 'video'} onClick={() => toggle('mime_filter', 'video')} color="#6366f1" />
        <Chip label="Audio" count={counts?.audio} active={filters.mime_filter === 'audio'} onClick={() => toggle('mime_filter', 'audio')} color="#f59e0b" />

        <div className="w-px h-5 bg-[var(--glass-border)] mx-1" />

        {/* Orientation */}
        <Chip label="H" count={counts?.horizontal} active={filters.orientation === 'h'} onClick={() => toggle('orientation', 'h')} color="#78909c" />
        <Chip label="V" count={counts?.vertical} active={filters.orientation === 'v'} onClick={() => toggle('orientation', 'v')} color="#78909c" />

        <div className="w-px h-5 bg-[var(--glass-border)] mx-1" />

        {/* Resolution */}
        <Chip label="SD" active={filters.resolution === 'sd'} onClick={() => toggle('resolution', 'sd')} color="#9e9e9e" />
        <Chip label="HD" count={counts?.hd} active={filters.resolution === 'hd'} onClick={() => toggle('resolution', 'hd')} color="#69f0ae" />
        <Chip label="FHD" count={counts?.fullhd} active={filters.resolution === 'fullhd'} onClick={() => toggle('resolution', 'fullhd')} color="#448aff" />
        <Chip label="2K" count={counts?.['2k']} active={filters.resolution === '2k'} onClick={() => toggle('resolution', '2k')} color="#7c4dff" />
        <Chip label="4K" count={counts?.['4k']} active={filters.resolution === '4k'} onClick={() => toggle('resolution', '4k')} color="#e040fb" />
        <Chip label="8K" count={counts?.['8k']} active={filters.resolution === '8k'} onClick={() => toggle('resolution', '8k')} color="#ff4081" />

        {/* More filters toggle */}
        <button
          type="button"
          onClick={() => setExpanded(p => !p)}
          className="px-2.5 py-1 text-[10px] font-medium rounded-lg transition-colors"
          style={{ background: 'var(--glass-bg)', color: 'var(--text-tertiary)', border: '1px solid var(--glass-border)' }}
        >
          {expanded ? 'Less' : 'More'}
        </button>

        {/* Clear all */}
        {activeCount > 0 && (
          <button
            type="button"
            onClick={clearAll}
            className="px-2.5 py-1 text-[10px] font-medium rounded-lg text-red-400 transition-colors"
            style={{ background: 'rgba(239,68,68,0.1)' }}
          >
            Clear ({activeCount})
          </button>
        )}
      </div>

      {/* Expanded filters */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            className="flex items-center gap-1.5 flex-wrap mt-2"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.15 }}
          >
            {/* Size filters */}
            <span className="text-[9px] text-[var(--text-tertiary)] mr-1">Size:</span>
            <Chip label="Small (<1MB)" count={counts?.small} active={filters.max_size === 1048576} onClick={() => {
              if (filters.max_size === 1048576) { const n = { ...filters }; delete n.max_size; delete n.min_size; onChange(n); }
              else onChange({ ...filters, max_size: 1048576, min_size: undefined });
            }} />
            <Chip label="Medium (1-100MB)" count={counts?.medium} active={filters.min_size === 1048576 && filters.max_size === 104857600} onClick={() => {
              if (filters.min_size === 1048576 && filters.max_size === 104857600) { const n = { ...filters }; delete n.max_size; delete n.min_size; onChange(n); }
              else onChange({ ...filters, min_size: 1048576, max_size: 104857600 });
            }} />
            <Chip label="Large (>100MB)" count={counts?.large} active={filters.min_size === 104857600} onClick={() => {
              if (filters.min_size === 104857600) { const n = { ...filters }; delete n.min_size; delete n.max_size; onChange(n); }
              else onChange({ ...filters, min_size: 104857600, max_size: undefined });
            }} />

            <div className="w-px h-5 bg-[var(--glass-border)] mx-1" />

            {/* Codec filters */}
            <span className="text-[9px] text-[var(--text-tertiary)] mr-1">Codec:</span>
            <Chip label="H.264" active={filters.codec === 'h264'} onClick={() => toggle('codec', 'h264')} color="#4fc3f7" />
            <Chip label="HEVC" active={filters.codec === 'hevc'} onClick={() => toggle('codec', 'hevc')} color="#81c784" />
            <Chip label="VP9" active={filters.codec === 'vp9'} onClick={() => toggle('codec', 'vp9')} color="#ffb74d" />
            <Chip label="AV1" active={filters.codec === 'av1'} onClick={() => toggle('codec', 'av1')} color="#ba68c8" />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** Convert Filters to URL query params for the media API */
export function filtersToParams(filters: Filters): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (filters.mime_filter) params.mime_filter = filters.mime_filter;
  if (filters.resolution) params.resolution = filters.resolution;
  if (filters.orientation) params.orientation = filters.orientation;
  if (filters.min_size) params.min_size = filters.min_size;
  if (filters.max_size) params.max_size = filters.max_size;
  if (filters.date_from) params.date_from = filters.date_from;
  if (filters.date_to) params.date_to = filters.date_to;
  if (filters.codec) params.codec = filters.codec;
  return params;
}
