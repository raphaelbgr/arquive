import { useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { MediaFile } from '../../types';
import { MediaBadges } from '../ui/QualityBadge';

interface FileInfoPanelProps {
  file: MediaFile;
  isOpen: boolean;
  onClose: () => void;
}

function formatBytes(bytes: number | null): string {
  if (!bytes) return '-';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatDate(iso: string | null): string {
  if (!iso) return '-';
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '-';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function Row({ label, value, mono }: { label: string; value: string | number | null | undefined; mono?: boolean }) {
  if (value === null || value === undefined || value === '') return null;
  return (
    <div className="flex justify-between gap-4 py-2 border-b border-[var(--glass-border)]">
      <span className="text-xs text-[var(--text-tertiary)] shrink-0">{label}</span>
      <span className={`text-xs text-[var(--text-primary)] text-right break-all ${mono ? 'font-mono' : ''}`}>{String(value)}</span>
    </div>
  );
}

function SectionWrap(props: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <h4 className="text-[10px] font-semibold uppercase tracking-widest text-[var(--accent-color)] mb-1 px-1">{props.title}</h4>
      <div className="glass-card p-3">
        {props.children}
      </div>
    </div>
  );
}

export function FileInfoPanel({ file, isOpen, onClose }: FileInfoPanelProps) {
  interface Meta {
    color_space?: string;
    camera_model?: string;
    lens?: string;
    exposure?: string;
    iso?: number;
    codec?: string;
    container?: string;
    framerate?: number;
    bitrate?: number;
    hdr_format?: string;
    audio_codec?: string;
    audio_channels?: number;
    audio_sample_rate?: number;
    [key: string]: string | number | undefined;
  }
  const metadata = useMemo<Meta>(() => {
    if (!file.metadata_json) return {};
    try {
      return JSON.parse(file.metadata_json) as Meta;
    } catch {
      return {};
    }
  }, [file.metadata_json]);

  const mime = (file.mime_type || '').toLowerCase();
  const isImage = mime.startsWith('image/');
  const isVideo = mime.startsWith('video/');
  const isAudio = mime.startsWith('audio/');

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />

          <motion.div
            className="fixed inset-x-0 bottom-0 z-50 max-h-[80vh] overflow-y-auto rounded-t-2xl px-5 pb-8 pt-3"
            style={{ background: 'var(--surface-gradient)', borderTop: '1px solid var(--glass-border)' }}
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', damping: 28, stiffness: 280 }}
          >
            {/* Drag handle */}
            <div className="flex justify-center mb-4">
              <div className="h-1 w-10 rounded-full bg-[var(--text-tertiary)]" />
            </div>

            {/* Header */}
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-base font-semibold text-[var(--text-primary)]">File Info</h3>
              <button
                onClick={onClose}
                className="w-8 h-8 rounded-full glass-card flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>

            {/* AI Description */}
            {file.ai_description && (
              <SectionWrap title="AI Description">
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{file.ai_description}</p>
                <button className="mt-2 px-3 py-1.5 rounded-lg glass-card text-[10px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors">
                  Regenerate
                </button>
              </SectionWrap>
            )}

            {/* General */}
            {/* Quality badges */}
            {(file.width || metadata.codec || metadata.framerate) && (
              <div className="mb-4 flex gap-1 flex-wrap">
                <MediaBadges width={file.width} height={file.height} codec={metadata.codec} framerate={metadata.framerate} size="sm" />
              </div>
            )}

            <SectionWrap title="General">
              <Row label="Name" value={file.name} />
              <Row label="Type" value={file.mime_type} />
              <Row label="Size" value={formatBytes(file.size)} />
              <Row label="Extension" value={file.extension} />
              <Row label="Local Path" value={file.path} mono />
              <Row label="Remote URL" value={`${window.location.origin}/file?path=${encodeURIComponent(file.path)}`} mono />
              <Row label="Created" value={formatDate(file.created_at)} />
              <Row label="Modified" value={formatDate(file.modified_at)} />
            </SectionWrap>

            {/* Image */}
            {isImage && (file.width || file.height) && (
              <SectionWrap title="Image Details">
                <Row label="Dimensions" value={file.width && file.height ? `${file.width} x ${file.height} px` : null} />
                <Row label="Megapixels" value={file.width && file.height ? `${((file.width * file.height) / 1e6).toFixed(1)} MP` : null} />
                <Row label="Color Space" value={metadata.color_space} />
                <Row label="Camera" value={metadata.camera_model} />
                <Row label="Lens" value={metadata.lens} />
                <Row label="Exposure" value={metadata.exposure} />
                <Row label="ISO" value={metadata.iso ? String(metadata.iso) : null} />
              </SectionWrap>
            )}

            {/* Video */}
            {isVideo && (
              <SectionWrap title="Video Details">
                <Row label="Duration" value={formatDuration(file.duration)} />
                <Row label="Resolution" value={file.width && file.height ? `${file.width} x ${file.height}` : null} />
                <Row label="Codec" value={metadata.codec} />
                <Row label="Container" value={metadata.container} />
                <Row label="Framerate" value={metadata.framerate ? `${metadata.framerate} fps` : null} />
                <Row label="Bitrate" value={metadata.bitrate ? formatBytes(metadata.bitrate) + '/s' : null} />
                <Row label="HDR" value={metadata.hdr_format} />
              </SectionWrap>
            )}

            {/* Audio */}
            {(isAudio || isVideo) && metadata.audio_codec && (
              <SectionWrap title="Audio">
                <Row label="Codec" value={metadata.audio_codec} />
                <Row label="Channels" value={metadata.audio_channels ? String(metadata.audio_channels) : null} />
                <Row label="Sample Rate" value={metadata.audio_sample_rate ? `${metadata.audio_sample_rate} Hz` : null} />
              </SectionWrap>
            )}

            {/* Download link */}
            <div className="mt-4 flex gap-2">
              <a
                href={`/api/v1/media/${file.id}/download`}
                className="flex-1 py-2.5 rounded-xl glass-card text-center text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              >
                Download Original
              </a>
              <a
                href={`/file?path=${encodeURIComponent(file.path)}`}
                target="_blank"
                rel="noopener"
                className="flex-1 py-2.5 rounded-xl glass-card text-center text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              >
                Open in New Tab
              </a>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
