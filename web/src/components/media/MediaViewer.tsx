import { useEffect, useCallback, useState, useRef } from 'react';
import type { MediaFile } from '../../types';
import { VideoPlayer } from './VideoPlayer';
import { ImageViewer } from './ImageViewer';
import { DocumentViewer } from './DocumentViewer';
import { AudioPlayer } from './AudioPlayer';
import { FileInfoPanel } from './FileInfoPanel';

interface MediaViewerProps {
  file: MediaFile | null;
  isOpen: boolean;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
}

function getViewerType(file: MediaFile): string {
  const mime = (file.mime_type || '').toLowerCase();
  if (mime.startsWith('video/')) return 'video';
  if (mime.startsWith('image/')) return 'image';
  if (mime.startsWith('audio/')) return 'audio';
  if (mime === 'application/pdf') return 'document';
  const ext = (file.extension || '').toLowerCase().replace('.', '');
  if ('mp4 mkv avi mov webm flv wmv 3gp mts'.includes(ext)) return 'video';
  if ('jpg jpeg png gif webp bmp svg avif heic heif tiff tif'.includes(ext)) return 'image';
  if ('mp3 wav flac aac ogg wma m4a opus'.includes(ext)) return 'audio';
  if (ext === 'pdf') return 'document';
  return 'unknown';
}

export function MediaViewer({ file, isOpen, onClose, onPrev, onNext }: MediaViewerProps) {
  const [showInfo, setShowInfo] = useState(false);
  const prevPathRef = useRef(window.location.pathname);

  // Update browser URL when file opens/changes
  useEffect(() => {
    if (file && isOpen) {
      // Only save the previous path if we're not already on a /view/ URL
      if (!window.location.pathname.startsWith('/view/')) {
        prevPathRef.current = window.location.pathname + window.location.search;
      }
      window.history.replaceState(null, '', `/view/${file.id}`);
    }
  }, [file, isOpen]);

  const close = useCallback(() => {
    window.history.replaceState(null, '', prevPathRef.current || '/timeline');
    setShowInfo(false);
    onClose();
  }, [onClose]);

  // Keyboard
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { showInfo ? setShowInfo(false) : close(); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); onPrev?.(); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); onNext?.(); }
      else if (e.key === 'i') { e.preventDefault(); setShowInfo(p => !p); }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, showInfo, close, onPrev, onNext]);

  // Lock scroll
  useEffect(() => {
    if (isOpen) document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, [isOpen]);

  if (!isOpen || !file) return null;

  const viewerType = getViewerType(file);
  const fileUrl = `/file?path=${encodeURIComponent(file.path)}`;

  return (
    // No backdrop-blur, no Framer Motion — plain CSS for max performance
    <div className="fixed inset-0 z-40 bg-black/95" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
      {/* Top bar */}
      <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between px-4 h-12">
        <button onClick={close} className="w-9 h-9 rounded-full bg-white/10 flex items-center justify-center text-white/80 hover:bg-white/20 transition-colors">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
        <span className="text-sm text-white/70 truncate max-w-[50%]">{file.name}</span>
        <button onClick={() => setShowInfo(p => !p)} className={`w-9 h-9 rounded-full flex items-center justify-center transition-colors ${showInfo ? 'bg-white/30 text-white' : 'bg-white/10 text-white/80 hover:bg-white/20'}`}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>
        </button>
      </div>

      {/* Prev/Next arrows */}
      {onPrev && (
        <button onClick={onPrev} className="absolute left-3 top-1/2 -translate-y-1/2 z-10 w-10 h-10 rounded-full bg-white/10 flex items-center justify-center text-white/80 hover:bg-white/20">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/></svg>
        </button>
      )}
      {onNext && (
        <button onClick={onNext} className="absolute right-3 top-1/2 -translate-y-1/2 z-10 w-10 h-10 rounded-full bg-white/10 flex items-center justify-center text-white/80 hover:bg-white/20">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/></svg>
        </button>
      )}

      {/* Content — key forces remount on file change for clean transitions */}
      <div className="h-full w-full pt-12 pb-2" key={file.id}>
        {viewerType === 'video' && <VideoPlayer src={fileUrl} autoplay />}
        {viewerType === 'image' && <ImageViewer src={fileUrl} alt={file.name} />}
        {viewerType === 'document' && <DocumentViewer src={fileUrl} />}
        {viewerType === 'audio' && <AudioPlayer src={fileUrl} title={file.name} duration={file.duration ?? undefined} />}
        {viewerType === 'unknown' && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-white/50">
            <p className="text-sm">Preview not available</p>
            <a href={fileUrl} download className="px-4 py-2 rounded-xl bg-white/10 text-xs text-white/70 hover:bg-white/20">Download</a>
          </div>
        )}
      </div>

      {/* Info panel */}
      {showInfo && <FileInfoPanel file={file} isOpen={true} onClose={() => setShowInfo(false)} />}
    </div>
  );
}
