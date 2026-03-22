import { useState, useEffect, useCallback, useRef } from 'react';
import type { SpriteMetadata, PreviewMode } from '../../types';

interface VideoPreviewTileProps {
  sprite: SpriteMetadata;
  mode: PreviewMode;
  frameIntervalMs?: number;
  crossfadeDurationMs?: number;
  className?: string;
  alt?: string;
}

export function VideoPreviewTile({
  sprite,
  mode,
  frameIntervalMs = 1000,
  crossfadeDurationMs = 200,
  className = '',
  alt = '',
}: VideoPreviewTileProps) {
  const [currentFrame, setCurrentFrame] = useState(0);
  const [isAnimating, setIsAnimating] = useState(mode === 'always');
  const [spriteLoaded, setSpriteLoaded] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const stopAnimation = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsAnimating(false);
    setCurrentFrame(0);
  }, []);

  const startAnimation = useCallback(() => {
    if (!spriteLoaded || sprite.totalFrames <= 1) return;
    setIsAnimating(true);
    intervalRef.current = setInterval(() => {
      setCurrentFrame((prev) => (prev + 1) % sprite.totalFrames);
    }, frameIntervalMs);
  }, [spriteLoaded, sprite.totalFrames, frameIntervalMs]);

  // Auto-start for 'always' mode
  useEffect(() => {
    if (mode === 'always' && spriteLoaded) {
      startAnimation();
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [mode, spriteLoaded, startAnimation]);

  const handleMouseEnter = () => {
    if (mode === 'hover') {
      startAnimation();
    }
  };

  const handleMouseLeave = () => {
    if (mode === 'hover') {
      stopAnimation();
    }
  };

  // Preload sprite sheet
  useEffect(() => {
    const img = new Image();
    img.onload = () => setSpriteLoaded(true);
    img.src = sprite.spriteUrl;
  }, [sprite.spriteUrl]);

  // Calculate background position for current frame
  const col = currentFrame % sprite.columns;
  const row = Math.floor(currentFrame / sprite.columns);
  const bgX = -(col * sprite.frameWidth);
  const bgY = -(row * sprite.frameHeight);
  const totalWidth = sprite.columns * sprite.frameWidth;
  const totalHeight = sprite.rows * sprite.frameHeight;

  return (
    <div
      ref={containerRef}
      className={`relative overflow-hidden ${className}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      style={{ aspectRatio: `${sprite.frameWidth} / ${sprite.frameHeight}` }}
    >
      {/* Poster image (shown when not animating) */}
      <img
        src={sprite.posterUrl}
        alt={alt}
        className="absolute inset-0 w-full h-full object-cover"
        style={{
          opacity: isAnimating && spriteLoaded ? 0 : 1,
          transition: `opacity ${crossfadeDurationMs}ms ease`,
        }}
      />

      {/* Sprite frame (shown when animating) */}
      {spriteLoaded && (
        <div
          className="absolute inset-0 w-full h-full"
          style={{
            backgroundImage: `url(${sprite.spriteUrl})`,
            backgroundPosition: `${bgX}px ${bgY}px`,
            backgroundSize: `${totalWidth}px ${totalHeight}px`,
            backgroundRepeat: 'no-repeat',
            opacity: isAnimating ? 1 : 0,
            transition: `opacity ${crossfadeDurationMs}ms ease`,
          }}
        />
      )}
    </div>
  );
}
