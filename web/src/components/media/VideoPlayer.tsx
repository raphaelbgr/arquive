import { useState, useRef, useEffect } from 'react';
import Hls from 'hls.js';

interface VideoPlayerProps {
  src: string;
  poster?: string;
  autoplay?: boolean;
}

export function VideoPlayer({ src, poster, autoplay = false }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const hlsRef = useRef<Hls | null>(null);
  const [playbackError, setPlaybackError] = useState(false);
  const [transcoding, setTranscoding] = useState(false);

  const isHLS = src.includes('.m3u8');

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    setPlaybackError(false);
    setTranscoding(false);

    if (isHLS && Hls.isSupported()) {
      const hls = new Hls({ enableWorker: true });
      hlsRef.current = hls;
      hls.loadSource(src);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        if (autoplay) video.play().catch(() => {});
      });
      return () => { hls.destroy(); hlsRef.current = null; };
    }

    // Direct playback — let browser handle the codec
    video.src = src;
    // Restore mute preference (default: muted)
    const savedMute = localStorage.getItem('arquive-muted');
    video.muted = savedMute === null ? true : savedMute === 'true';
    // Persist mute changes
    video.addEventListener('volumechange', () => {
      localStorage.setItem('arquive-muted', String(video.muted));
    });
    if (autoplay) video.play().catch(() => {});

    return () => { video.src = ''; };
  }, [src, isHLS, autoplay]);

  // Detect truly unsupported codecs after a timeout
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const timer = setTimeout(() => {
      // If after 5s the video has no decoded frames, codec is likely unsupported
      if (video.readyState < 2 && video.currentTime === 0 && !video.paused && !video.error) {
        setPlaybackError(true);
      }
    }, 5000);

    const onError = () => {
      if (video.error?.code === MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED) {
        setPlaybackError(true);
      }
    };
    video.addEventListener('error', onError);

    return () => {
      clearTimeout(timer);
      video.removeEventListener('error', onError);
    };
  }, [src]);

  return (
    <div className="relative flex h-full w-full items-center justify-center bg-black">
      {/* Native video element with browser controls — zero React overhead */}
      <video
        ref={videoRef}
        className="h-full w-full object-contain"
        poster={poster}
        controls
        playsInline
        loop
      />

      {/* Codec error fallback */}
      {playbackError && !transcoding && (
        <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-4 bg-black/90">
          <p className="text-sm text-white/60">This video codec is not supported by your browser</p>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => {
                setPlaybackError(false);
                setTranscoding(true);
                if (videoRef.current) {
                  videoRef.current.src = src + (src.includes('?') ? '&' : '?') + 'transcode=1';
                  videoRef.current.play().catch(() => {});
                }
              }}
              className="px-4 py-2 rounded-xl text-xs font-medium text-white bg-blue-600 hover:bg-blue-700"
            >
              Transcode to H.264 (GPU)
            </button>
            <a
              href={src}
              download
              className="px-4 py-2 rounded-xl text-xs font-medium text-white/60 bg-white/10 hover:bg-white/20"
            >
              Download Original
            </a>
          </div>
        </div>
      )}

      {transcoding && (
        <div className="absolute top-4 left-4 z-30 px-3 py-1.5 rounded-lg text-[10px] font-medium text-white bg-amber-500/80">
          Transcoding via GPU...
        </div>
      )}
    </div>
  );
}
