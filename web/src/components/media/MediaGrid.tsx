import { useState } from 'react';
import type { MediaFile } from '../../types';
import { MediaCard } from './MediaCard';
import { MediaViewer } from './MediaViewer';
import { FileInfoPanel } from './FileInfoPanel';

interface MediaGridProps {
  items: MediaFile[];
  loading?: boolean;
}

export function MediaGrid({ items, loading = false }: MediaGridProps) {
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const [infoFile, setInfoFile] = useState<MediaFile | null>(null);

  if (loading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
        {Array.from({ length: 18 }).map((_, i) => (
          <div key={i} className="aspect-video rounded-2xl shimmer" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-[var(--text-tertiary)] text-sm">
        No media files found
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
        {items.map((file, index) => (
          <MediaCard
            key={file.id}
            file={file}
            onClick={() => setViewerIndex(index)}
            onInfo={() => setInfoFile(file)}
          />
        ))}
      </div>

      {viewerIndex !== null && items[viewerIndex] && (
        <MediaViewer
          file={items[viewerIndex]}
          isOpen={true}
          onClose={() => setViewerIndex(null)}
          onPrev={viewerIndex > 0 ? () => setViewerIndex(viewerIndex - 1) : undefined}
          onNext={viewerIndex < items.length - 1 ? () => setViewerIndex(viewerIndex + 1) : undefined}
        />
      )}

      {infoFile && (
        <FileInfoPanel file={infoFile} isOpen={true} onClose={() => setInfoFile(null)} />
      )}
    </>
  );
}
