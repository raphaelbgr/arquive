import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { MediaFile, SpriteMetadata } from '../../types';
import { VideoPreviewTile } from './VideoPreviewTile';
import { useIntersectionObserver } from '../../hooks/useIntersectionObserver';
import { ShimmerPlaceholder } from '../ui/ShimmerPlaceholder';
import { copyToClipboard } from '../../utils/clipboard';

interface MediaCardProps {
  file: MediaFile;
  onClick?: () => void;
  onInfo?: () => void;
  isSelected?: boolean;
  onSelect?: () => void;
  selectionMode?: boolean;
}

function isImage(file: MediaFile): boolean {
  return (file.mime_type || '').startsWith('image/');
}

function isVideo(file: MediaFile): boolean {
  return (file.mime_type || '').startsWith('video/');
}

function isAudio(file: MediaFile): boolean {
  return (file.mime_type || '').startsWith('audio/');
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function formatSize(bytes: number | null): string {
  if (!bytes) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

/** Get the image URL for a file — for images, serve the file itself */
function getImageUrl(file: MediaFile): string | null {
  // If thumbnail_path is already a URL (starts with /), use it directly
  // This is the case for face detection match thumbnails
  if (file.thumbnail_path && file.thumbnail_path.startsWith('/')) {
    return file.thumbnail_path;
  }
  if (isImage(file)) {
    return `/file?path=${encodeURIComponent(file.path)}&w=320`;
  }
  if (isVideo(file)) {
    return `/api/v1/media/${file.id}/thumbnail`;
  }
  return null;
}

const TYPE_COLORS: Record<string, string> = {
  image: 'bg-emerald-500/20 text-emerald-400',
  video: 'bg-indigo-500/20 text-indigo-400',
  audio: 'bg-amber-500/20 text-amber-400',
  document: 'bg-rose-500/20 text-rose-400',
  file: 'bg-slate-500/20 text-slate-400',
};

function getTypeInfo(file: MediaFile): { label: string; color: string } {
  if (isImage(file)) return { label: 'IMG', color: TYPE_COLORS.image };
  if (isVideo(file)) return { label: 'VID', color: TYPE_COLORS.video };
  if (isAudio(file)) return { label: 'AUD', color: TYPE_COLORS.audio };
  const ext = (file.extension || '').toLowerCase();
  if (['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt'].includes(ext))
    return { label: 'DOC', color: TYPE_COLORS.document };
  return { label: ext.replace('.', '').toUpperCase().slice(0, 3) || 'FILE', color: TYPE_COLORS.file };
}

export function MediaCard({ file, onClick, onInfo, isSelected, onSelect, selectionMode }: MediaCardProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [imgLoaded, setImgLoaded] = useState(false);
  const [spriteData, setSpriteData] = useState<SpriteMetadata | null>(null);
  const spriteRequested = useRef(false);
  const { ref, isIntersecting } = useIntersectionObserver({ triggerOnce: true, rootMargin: '200px' });

  const imageUrl = getImageUrl(file);
  const typeInfo = getTypeInfo(file);

  // Fetch sprite sheet when card becomes visible for videos — only once per card lifetime
  useEffect(() => {
    if (isIntersecting && isVideo(file) && !spriteRequested.current) {
      spriteRequested.current = true;
      // Only fetch sprite if already cached (don't trigger on-demand generation from grid)
      fetch(`/api/v1/media/${file.id}/sprite/meta?cached_only=1`, { credentials: 'include' })
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (data && data.spriteUrl) setSpriteData(data); })
        .catch(() => {});
    }
  }, [isIntersecting, file]);

  const handleMouseEnter = () => {
    setIsHovered(true);
  };

  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation();
    window.open(`/api/v1/media/${file.id}/download`, '_blank');
  };

  const handleCardClick = (e: React.MouseEvent) => {
    if (selectionMode && onSelect) {
      e.stopPropagation();
      onSelect();
      return;
    }
    if (e.ctrlKey && onSelect) {
      e.stopPropagation();
      onSelect();
      return;
    }
    onClick?.();
  };

  return (
    <motion.div
      ref={ref}
      className={`group relative glass-card overflow-hidden cursor-pointer transition-all ${
        isSelected
          ? 'ring-2 ring-[var(--accent-color)] scale-[1.03]'
          : selectionMode
            ? 'opacity-70'
            : ''
      }`}
      onClick={handleCardClick}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={() => setIsHovered(false)}
      whileHover={isSelected ? { scale: 1.03, y: -2 } : { scale: 1.02, y: -2 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
    >
      {/* Thumbnail area */}
      <div className="relative aspect-video overflow-hidden bg-black">
        {/* Sprite cycling overlay for videos — auto-plays when visible */}
        {spriteData && (
          <div className="absolute inset-0 z-10">
            <VideoPreviewTile
              sprite={spriteData}
              mode="always"
              frameIntervalMs={800}
              crossfadeDurationMs={200}
            />
          </div>
        )}

        {!isIntersecting ? (
          <ShimmerPlaceholder rounded={false} />
        ) : imageUrl && !imgError ? (
          <>
            {!imgLoaded && <div className="absolute inset-0 shimmer" />}
            <img
              src={imageUrl}
              alt={file.name}
              className={`w-full h-full object-cover transition-opacity duration-300 ${imgLoaded ? 'opacity-100' : 'opacity-0'}`}
              loading="lazy"
              onLoad={() => setImgLoaded(true)}
              onError={() => setImgError(true)}
            />
          </>
        ) : (
          <div className={`w-full h-full flex flex-col items-center justify-center gap-1 ${typeInfo.color}`}>
            <span className="text-2xl font-bold">{typeInfo.label}</span>
            <span className="text-[9px] opacity-60">{formatSize(file.size)}</span>
          </div>
        )}

        {/* Duration badge for videos */}
        {isVideo(file) && file.duration && (
          <span className="absolute bottom-2 right-2 px-1.5 py-0.5 bg-black/70 rounded text-[10px] font-medium text-white tabular-nums">
            {formatDuration(file.duration)}
          </span>
        )}

        {/* Type badge */}
        <span className={`absolute top-2 left-2 px-1.5 py-0.5 rounded text-[8px] font-bold uppercase ${typeInfo.color}`}>
          {typeInfo.label}
        </span>

        {/* iOS play button on hover for videos */}
        {isVideo(file) && isHovered && !selectionMode && (
          <motion.div
            className="absolute inset-0 z-20 flex items-center justify-center pointer-events-none"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.15 }}
          >
            <div className="w-12 h-12 rounded-full bg-white/20 backdrop-blur-md flex items-center justify-center shadow-lg">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="white" className="ml-0.5">
                <polygon points="6 3 20 12 6 21 6 3" />
              </svg>
            </div>
          </motion.div>
        )}

        {/* Selection checkbox overlay */}
        {(selectionMode || isSelected) && (
          <div className="absolute top-2 right-2 z-20 flex items-center justify-center w-6 h-6 rounded-full border-2 transition-colors"
            style={{
              borderColor: isSelected ? 'var(--accent-color)' : 'var(--text-tertiary)',
              backgroundColor: isSelected ? 'var(--accent-color)' : 'transparent',
            }}
          >
            {isSelected && (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            )}
          </div>
        )}

        {/* Hover action bar — hidden in selection mode to avoid overlap with checkbox */}
        {!selectionMode && (
          <motion.div
            className="absolute top-2 right-2 z-30 flex gap-1"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: isHovered ? 1 : 0, y: isHovered ? 0 : -4 }}
            transition={{ duration: 0.15 }}
          >
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onInfo?.(); }}
              className="w-6 h-6 rounded-md bg-black/60 backdrop-blur-sm flex items-center justify-center hover:bg-black/80 transition-colors"
              title="File info"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
            </button>
            <button
              type="button"
              onClick={handleDownload}
              className="w-6 h-6 rounded-md bg-black/60 backdrop-blur-sm flex items-center justify-center hover:bg-black/80 transition-colors"
              title="Download file"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
            </button>
          </motion.div>
        )}

        {/* Hover tooltip removed from thumbnail — moved to floating popover below card */}
      </div>

      {/* Info area */}
      <div className="p-2.5">
        <p className="text-xs font-medium text-[var(--text-primary)] truncate" title={file.name}>
          {file.name}
        </p>
        <p className="text-[10px] text-[var(--text-tertiary)] mt-0.5">
          {formatSize(file.size)}
        </p>
      </div>

      {/* iOS-style floating info popover — appears below tile on hover */}
      <AnimatePresence>
        {isHovered && !selectionMode && (
          <motion.div
            className="absolute left-0 right-0 z-40 rounded-xl p-3 text-[10px] leading-relaxed shadow-xl pointer-events-auto"
            style={{
              top: '100%',
              marginTop: '6px',
              background: 'var(--glass-bg)',
              backdropFilter: 'blur(24px)',
              WebkitBackdropFilter: 'blur(24px)',
              border: '1px solid var(--glass-border)',
              color: 'var(--text-secondary)',
            }}
            initial={{ opacity: 0, y: -4, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.97 }}
            transition={{ duration: 0.15, delay: 0.3 }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Arrow */}
            <div
              className="absolute -top-1.5 left-4 w-3 h-3 rotate-45"
              style={{ background: 'var(--glass-bg)', borderTop: '1px solid var(--glass-border)', borderLeft: '1px solid var(--glass-border)' }}
            />

            <div className="flex items-center gap-1.5 mb-1.5">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="shrink-0 opacity-40"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
              <a
                href={`/file?path=${encodeURIComponent(file.path)}`}
                target="_blank"
                rel="noopener noreferrer"
                className="truncate font-mono flex-1"
                style={{ color: 'var(--accent-color)', fontSize: '9px' }}
              >
                /file?path=.../{file.name}
              </a>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); copyToClipboard(`${window.location.origin}/file?path=${encodeURIComponent(file.path)}`); }}
                className="shrink-0 w-5 h-5 rounded-md flex items-center justify-center transition-colors"
                style={{ background: 'var(--glass-hover-bg)' }}
                title="Copy URL"
              >
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
              </button>
            </div>

            <div className="flex items-center gap-3 text-[9px]" style={{ color: 'var(--text-tertiary)' }}>
              <span>{formatSize(file.size)}</span>
              <span>{file.mime_type}</span>
              {file.extension && <span>{file.extension}</span>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
