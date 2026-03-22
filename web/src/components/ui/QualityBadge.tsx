/**
 * Quality Badge System — ported from Stream-Lens/PlaybackLab unified design system.
 *
 * Resolution badges: SD, HD, Full HD, 2K, 4K, Cinema 4K, 8K, 16K
 * Codec badges: H.264, HEVC, VP9, AV1
 * HDR badges: HDR10, HDR10+, Dolby Vision, HLG
 * Framerate badges: 24fps, 30fps, 60fps, 120fps
 * Audio badges: AAC, Dolby Digital, Dolby Atmos, Opus, FLAC
 * Channel badges: Mono, Stereo, 5.1, 7.1, Atmos 7.1.4
 */

// ============================================
// Color Palette (from Stream-Lens TAG_COLORS)
// ============================================

const BADGE_STYLES = {
  // Resolution tiers
  '16K':        { color: '#ff1744', bg: 'rgba(255, 23, 68, 0.18)' },
  '8K':         { color: '#ff4081', bg: 'rgba(255, 64, 129, 0.18)' },
  '4K':         { color: '#e040fb', bg: 'rgba(224, 64, 251, 0.18)' },
  'Cinema 4K':  { color: '#d500f9', bg: 'rgba(213, 0, 249, 0.18)' },
  '2K':         { color: '#7c4dff', bg: 'rgba(124, 77, 255, 0.18)' },
  'Full HD':    { color: '#448aff', bg: 'rgba(68, 138, 255, 0.18)' },
  'HD':         { color: '#69f0ae', bg: 'rgba(105, 240, 174, 0.18)' },
  'SD':         { color: '#9e9e9e', bg: 'rgba(158, 158, 158, 0.15)' },

  // Video codecs
  'H.264':      { color: '#4fc3f7', bg: 'rgba(79, 195, 247, 0.15)' },
  'HEVC':       { color: '#81c784', bg: 'rgba(129, 199, 132, 0.15)' },
  'VP9':        { color: '#ffb74d', bg: 'rgba(255, 183, 77, 0.15)' },
  'AV1':        { color: '#ba68c8', bg: 'rgba(186, 104, 200, 0.15)' },

  // HDR
  'HDR10':      { color: '#ffd54f', bg: 'rgba(255, 213, 79, 0.18)' },
  'HDR10+':     { color: '#ffab40', bg: 'rgba(255, 171, 64, 0.18)' },
  'DV':         { color: '#ff4081', bg: 'rgba(255, 64, 129, 0.18)' },
  'HLG':        { color: '#40c4ff', bg: 'rgba(64, 196, 255, 0.18)' },

  // Framerate
  '24fps':      { color: '#90a4ae', bg: 'rgba(144, 164, 174, 0.15)' },
  '30fps':      { color: '#a5d6a7', bg: 'rgba(165, 214, 167, 0.15)' },
  '60fps':      { color: '#ff6e40', bg: 'rgba(255, 110, 64, 0.18)' },
  '120fps':     { color: '#ff1744', bg: 'rgba(255, 23, 68, 0.18)' },

  // Audio codecs
  'AAC':        { color: '#4db6ac', bg: 'rgba(77, 182, 172, 0.15)' },
  'Dolby':      { color: '#9575cd', bg: 'rgba(149, 117, 205, 0.15)' },
  'Atmos':      { color: '#ffd740', bg: 'rgba(255, 215, 64, 0.2)' },
  'Opus':       { color: '#4dd0e1', bg: 'rgba(77, 208, 225, 0.15)' },
  'FLAC':       { color: '#26a69a', bg: 'rgba(38, 166, 154, 0.15)' },

  // Audio channels
  // 'Mono':     { color: '#90a4ae', bg: 'rgba(144, 164, 174, 0.15)' },
  // 'Stereo':   { color: '#90a4ae', bg: 'rgba(144, 164, 174, 0.15)' },
  // '5.1':      { color: '#ffab91', bg: 'rgba(255, 171, 145, 0.15)' },
  // '7.1':      { color: '#f48fb1', bg: 'rgba(244, 143, 177, 0.15)' },
  // '7.1.4':    { color: '#ffd740', bg: 'rgba(255, 215, 64, 0.2)' },

  // Features (future)
  // 'Spatial':  { color: '#b39ddb', bg: 'rgba(179, 157, 219, 0.15)' },
  // 'Lossless': { color: '#80deea', bg: 'rgba(128, 222, 234, 0.15)' },
  // 'Hi-Res':   { color: '#ffe082', bg: 'rgba(255, 224, 130, 0.15)' },
  // 'Muxed':    { color: '#a1887f', bg: 'rgba(161, 136, 127, 0.15)' },
  // 'Live':     { color: '#ff1744', bg: 'rgba(255, 23, 68, 0.2)' },
  // 'VR':       { color: '#00e5ff', bg: 'rgba(0, 229, 255, 0.15)' },
  // '3D':       { color: '#76ff03', bg: 'rgba(118, 255, 3, 0.15)' },

  // Orientation
  'H':          { color: '#78909c', bg: 'rgba(120, 144, 156, 0.15)' },
  'V':          { color: '#78909c', bg: 'rgba(120, 144, 156, 0.15)' },

  'default':    { color: '#90a4ae', bg: 'rgba(144, 164, 174, 0.12)' },
} as const;

// ============================================
// Resolution Detection
// ============================================

export function getResolutionBadge(width: number | null, height: number | null): string | null {
  if (!width || !height) return null;
  if (width >= 15360 || height >= 8640) return '16K';
  if (width >= 7680 || height >= 4320) return '8K';
  if (width >= 4096 && height >= 2160) return 'Cinema 4K';
  if (width >= 3840 || height >= 2160) return '4K';
  if (width >= 2560 || height >= 1440) return '2K';
  if (width >= 1920 || height >= 1080) return 'Full HD';
  if (width >= 1280 || height >= 720) return 'HD';
  return 'SD';
}

export function getCodecBadge(codec: string | null | undefined): string | null {
  if (!codec) return null;
  const c = codec.toLowerCase();
  if (c === 'h264' || c === 'avc' || c.startsWith('avc1')) return 'H.264';
  if (c === 'hevc' || c === 'h265' || c.startsWith('hev1') || c.startsWith('hvc1')) return 'HEVC';
  if (c.startsWith('vp9') || c.startsWith('vp09')) return 'VP9';
  if (c.startsWith('av1') || c.startsWith('av01')) return 'AV1';
  return null;
}

export function getFpsBadge(framerate: number | null | undefined): string | null {
  if (!framerate) return null;
  if (framerate >= 119) return '120fps';
  if (framerate >= 59) return '60fps';
  if (framerate >= 29) return '30fps';
  if (framerate >= 23) return '24fps';
  return null;
}

export function getOrientationBadge(width: number | null, height: number | null): string | null {
  if (!width || !height) return null;
  if (width > height) return 'H';
  if (height > width) return 'V';
  return null; // square — no badge
}

// ============================================
// Badge Component
// ============================================

interface QualityBadgeProps {
  label: string;
  size?: 'xs' | 'sm' | 'md';
}

export function QualityBadge({ label, size = 'xs' }: QualityBadgeProps) {
  const style = BADGE_STYLES[label as keyof typeof BADGE_STYLES] || BADGE_STYLES.default;

  const sizeClasses = {
    xs: 'text-[8px] px-1 py-px',
    sm: 'text-[9px] px-1.5 py-0.5',
    md: 'text-[10px] px-2 py-0.5',
  };

  return (
    <span
      className={`inline-flex items-center font-bold rounded ${sizeClasses[size]} leading-tight`}
      style={{ color: style.color, background: style.bg }}
    >
      {label}
    </span>
  );
}

/** Render all applicable badges for a media file */
export function MediaBadges({ width, height, codec, framerate, size = 'xs' }: {
  width?: number | null;
  height?: number | null;
  codec?: string | null;
  framerate?: number | null;
  size?: 'xs' | 'sm' | 'md';
}) {
  const badges: string[] = [];

  const res = getResolutionBadge(width ?? null, height ?? null);
  if (res) badges.push(res);

  const codecBadge = getCodecBadge(codec);
  if (codecBadge) badges.push(codecBadge);

  const fps = getFpsBadge(framerate);
  if (fps) badges.push(fps);

  const orient = getOrientationBadge(width ?? null, height ?? null);
  if (orient) badges.push(orient);

  if (badges.length === 0) return null;

  return (
    <div className="flex items-center gap-0.5 flex-wrap">
      {badges.map(b => <QualityBadge key={b} label={b} size={size} />)}
    </div>
  );
}
