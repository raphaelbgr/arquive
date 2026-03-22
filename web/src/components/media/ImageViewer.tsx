import { useState, useRef, useCallback, useEffect } from 'react';

interface ImageViewerProps {
  src: string;
  alt?: string;
  onClose?: () => void;
  onPrev?: () => void;
  onNext?: () => void;
}

const MIN_SCALE = 1;
const MAX_SCALE = 8;
const ZOOM_STEP = 0.25;

export function ImageViewer({ src, alt, onClose, onPrev, onNext }: ImageViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [translate, setTranslate] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const dragStart = useRef({ x: 0, y: 0 });
  const translateStart = useRef({ x: 0, y: 0 });

  // Pinch-to-zoom state
  const lastPinchDistance = useRef<number | null>(null);

  const resetView = useCallback(() => {
    setScale(1);
    setTranslate({ x: 0, y: 0 });
  }, []);

  // Reset when source changes
  useEffect(() => {
    resetView();
    setLoaded(false);
  }, [src, resetView]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'Escape':
          onClose?.();
          break;
        case 'ArrowLeft':
          e.preventDefault();
          onPrev?.();
          break;
        case 'ArrowRight':
          e.preventDefault();
          onNext?.();
          break;
        case '+':
        case '=':
          e.preventDefault();
          setScale((s) => Math.min(MAX_SCALE, s + ZOOM_STEP));
          break;
        case '-':
          e.preventDefault();
          setScale((s) => {
            const next = Math.max(MIN_SCALE, s - ZOOM_STEP);
            if (next <= 1) setTranslate({ x: 0, y: 0 });
            return next;
          });
          break;
        case '0':
          e.preventDefault();
          resetView();
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose, onPrev, onNext, resetView]);

  // Mouse wheel zoom
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP;
    setScale((s) => {
      const next = Math.max(MIN_SCALE, Math.min(MAX_SCALE, s + delta));
      if (next <= 1) setTranslate({ x: 0, y: 0 });
      return next;
    });
  }, []);

  // Touch handlers for pinch-to-zoom
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      lastPinchDistance.current = Math.sqrt(dx * dx + dy * dy);
    }
  }, []);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2 && lastPinchDistance.current !== null) {
      e.preventDefault();
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      const distance = Math.sqrt(dx * dx + dy * dy);
      const delta = (distance - lastPinchDistance.current) * 0.01;
      lastPinchDistance.current = distance;

      setScale((s) => {
        const next = Math.max(MIN_SCALE, Math.min(MAX_SCALE, s + delta));
        if (next <= 1) setTranslate({ x: 0, y: 0 });
        return next;
      });
    }
  }, []);

  const handleTouchEnd = useCallback(() => {
    lastPinchDistance.current = null;
  }, []);

  // Mouse drag for panning when zoomed
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (scale <= 1) return;
      e.preventDefault();
      setIsDragging(true);
      dragStart.current = { x: e.clientX, y: e.clientY };
      translateStart.current = { ...translate };
    },
    [scale, translate],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isDragging) return;
      const dx = e.clientX - dragStart.current.x;
      const dy = e.clientY - dragStart.current.y;
      setTranslate({
        x: translateStart.current.x + dx,
        y: translateStart.current.y + dy,
      });
    },
    [isDragging],
  );

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Double-click to toggle zoom
  const handleDoubleClick = useCallback(() => {
    if (scale > 1) {
      resetView();
    } else {
      setScale(3);
    }
  }, [scale, resetView]);

  const zoomPercentage = Math.round(scale * 100);

  return (
    <div
      ref={containerRef}
      className="relative flex h-full w-full items-center justify-center overflow-hidden font-[Inter]"
      onWheel={handleWheel}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onDoubleClick={handleDoubleClick}
    >
      {/* Loading spinner */}
      {!loaded && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div
            className="h-10 w-10 rounded-full border-2 border-transparent animate-spin"
            style={{
              borderTopColor: 'var(--accent-color)',
              borderRightColor: 'var(--accent-color)',
            }}
          />
        </div>
      )}

      <img
        src={src}
        alt={alt ?? ''}
        className={`max-h-full max-w-full select-none object-contain transition-transform ${
          isDragging ? 'duration-0' : 'duration-200'
        } ${loaded ? 'opacity-100' : 'opacity-0'}`}
        style={{
          transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`,
          transition: isDragging
            ? 'transform 0s'
            : 'transform 0.2s, opacity 0.3s ease-in',
        }}
        draggable={false}
        onLoad={() => setLoaded(true)}
      />

      {/* Bottom toolbar */}
      <div className="absolute inset-x-0 bottom-0 flex items-center justify-center pb-6">
        <div className="flex items-center gap-1 rounded-2xl bg-white/10 px-2 py-1.5 backdrop-blur-xl">
          {onPrev && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onPrev();
              }}
              className="flex h-8 w-8 items-center justify-center rounded-full text-white transition-colors hover:bg-white/20"
              aria-label="Previous"
            >
              <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z" />
              </svg>
            </button>
          )}

          <button
            onClick={(e) => {
              e.stopPropagation();
              setScale((s) => {
                const next = Math.max(MIN_SCALE, s - ZOOM_STEP);
                if (next <= 1) setTranslate({ x: 0, y: 0 });
                return next;
              });
            }}
            className="flex h-8 w-8 items-center justify-center rounded-full text-white transition-colors hover:bg-white/20"
            aria-label="Zoom out"
          >
            <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M19 13H5v-2h14v2z" />
            </svg>
          </button>

          <button
            onClick={(e) => {
              e.stopPropagation();
              resetView();
            }}
            className="min-w-[48px] rounded-lg px-2 py-1 text-xs text-white/80 transition-colors hover:bg-white/20"
            aria-label="Reset zoom"
          >
            {zoomPercentage}%
          </button>

          <button
            onClick={(e) => {
              e.stopPropagation();
              setScale((s) => Math.min(MAX_SCALE, s + ZOOM_STEP));
            }}
            className="flex h-8 w-8 items-center justify-center rounded-full text-white transition-colors hover:bg-white/20"
            aria-label="Zoom in"
          >
            <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" />
            </svg>
          </button>

          {onNext && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onNext();
              }}
              className="flex h-8 w-8 items-center justify-center rounded-full text-white transition-colors hover:bg-white/20"
              aria-label="Next"
            >
              <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
