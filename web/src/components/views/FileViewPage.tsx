import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import type { MediaFile } from '../../types';
import { api } from '../../api/client';
import { MediaViewer } from '../media/MediaViewer';

/**
 * Standalone file view page — accessed via /view/:id
 * Gives each file a unique URL in the browser bar.
 */
export function FileViewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [file, setFile] = useState<MediaFile | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!id) return;
    api.media.get(parseInt(id))
      .then(setFile)
      .catch(() => setError('File not found'));
  }, [id]);

  if (error) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--text-tertiary)]">
        {error}
      </div>
    );
  }

  if (!file) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="shimmer w-16 h-16 rounded-full" />
      </div>
    );
  }

  return (
    <MediaViewer
      file={file}
      isOpen={true}
      onClose={() => navigate(-1)}
    />
  );
}
