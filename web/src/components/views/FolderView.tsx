import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import type { MediaFile } from '../../types';
import { api } from '../../api/client';
import { MediaGrid } from '../media/MediaGrid';

interface FolderInfo {
  name: string;
  path: string;
  count: number;
}

const PAGE_SIZE = 60;

export function FolderView() {
  const [rootFolders, setRootFolders] = useState<FolderInfo[]>([]);
  const [subFolders, setSubFolders] = useState<FolderInfo[]>([]);
  const [selectedPath, setSelectedPath] = useState('');
  const [files, setFiles] = useState<MediaFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [page, setPage] = useState(1);
  const [breadcrumbs, setBreadcrumbs] = useState<{ name: string; path: string }[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.media
      .folders()
      .then((data) => setRootFolders(data.folders ?? []))
      .catch(() => setRootFolders([]));
  }, []);

  const loadFiles = useCallback((path: string, pageNum: number, append: boolean) => {
    if (!path) return;
    setLoading(true);
    api.media
      .list({ folder: path, limit: PAGE_SIZE, page: pageNum })
      .then((res) => {
        const items = res.items ?? [];
        setFiles(prev => append ? [...prev, ...items] : items);
        setHasMore(items.length === PAGE_SIZE && pageNum * PAGE_SIZE < res.total);
      })
      .catch(() => { if (!append) setFiles([]); })
      .finally(() => setLoading(false));
  }, []);

  const navigateTo = useCallback((path: string, name: string) => {
    setSelectedPath(path);
    setPage(1);
    setFiles([]);

    setBreadcrumbs(prev => {
      const idx = prev.findIndex(b => b.path === path);
      if (idx >= 0) return prev.slice(0, idx + 1);
      return [...prev, { name, path }];
    });

    fetch(`/api/v1/media/folders?parent=${encodeURIComponent(path)}`, { credentials: 'include' })
      .then(r => r.json())
      .then((data: { folders: FolderInfo[] }) => setSubFolders(data.folders ?? []))
      .catch(() => setSubFolders([]));

    loadFiles(path, 1, false);
  }, [loadFiles]);

  const loadMore = useCallback(() => {
    if (loading || !hasMore) return;
    const nextPage = page + 1;
    setPage(nextPage);
    loadFiles(selectedPath, nextPage, true);
  }, [loading, hasMore, page, selectedPath, loadFiles]);

  // Infinite scroll detection
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el || loading || !hasMore) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 400) {
      loadMore();
    }
  }, [loadMore, loading, hasMore]);

  return (
    <motion.div
      className="flex h-full"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      <div className="w-60 shrink-0 border-r border-[var(--glass-border)] overflow-y-auto py-3">
        <div className="px-3 mb-2">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-tertiary)]">Libraries</span>
        </div>
        {rootFolders.length === 0 && <p className="px-3 text-xs text-[var(--text-tertiary)]">No libraries configured</p>}
        {rootFolders.map(folder => (
          <button
            key={folder.path}
            type="button"
            onClick={() => navigateTo(folder.path, folder.name)}
            className={`w-full flex items-center gap-2 px-3 py-2 text-left text-sm rounded-lg transition-colors ${
              selectedPath.startsWith(folder.path)
                ? 'bg-[var(--glass-bg)] text-[var(--text-primary)]'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--glass-hover-bg)]'
            }`}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
            </svg>
            <span className="truncate flex-1">{folder.name}</span>
            <span className="text-[10px] text-[var(--text-tertiary)] tabular-nums">{folder.count}</span>
          </button>
        ))}

        {subFolders.length > 0 && (
          <>
            <div className="px-3 mt-4 mb-2">
              <span className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-tertiary)]">Subfolders</span>
            </div>
            {subFolders.map(folder => (
              <button
                key={folder.path}
                type="button"
                onClick={() => navigateTo(folder.path, folder.name)}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--glass-hover-bg)] rounded-lg transition-colors"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                </svg>
                <span className="truncate flex-1">{folder.name}</span>
                <span className="text-[10px] text-[var(--text-tertiary)] tabular-nums">{folder.count}</span>
              </button>
            ))}
          </>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4" onScroll={handleScroll}>
        {breadcrumbs.length > 0 && (
          <div className="flex items-center gap-1.5 mb-4 text-sm flex-wrap">
            {breadcrumbs.map((crumb, i) => (
              <span key={crumb.path} className="flex items-center gap-1.5">
                {i > 0 && <span className="text-[var(--text-tertiary)]">/</span>}
                <button
                  type="button"
                  onClick={() => navigateTo(crumb.path, crumb.name)}
                  className={i === breadcrumbs.length - 1
                    ? 'text-[var(--text-primary)] font-medium'
                    : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'}
                >
                  {crumb.name}
                </button>
              </span>
            ))}
          </div>
        )}

        {!selectedPath && (
          <div className="flex items-center justify-center h-64 text-[var(--text-tertiary)] text-sm">
            Select a library to browse files
          </div>
        )}

        {selectedPath && <MediaGrid items={files} loading={loading && files.length === 0} />}

        {hasMore && !loading && (
          <div className="flex justify-center py-6">
            <button type="button" onClick={loadMore} className="px-4 py-2 text-xs text-[var(--text-secondary)] bg-[var(--glass-bg)] rounded-xl hover:bg-[var(--glass-hover-bg)] transition-colors">
              Load more
            </button>
          </div>
        )}
        {loading && files.length > 0 && (
          <div className="flex justify-center py-6">
            <span className="text-xs text-[var(--text-tertiary)]">Loading...</span>
          </div>
        )}
      </div>
    </motion.div>
  );
}
