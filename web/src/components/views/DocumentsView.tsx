import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import type { MediaFile } from '../../types';
import { api } from '../../api/client';
import { MediaGrid } from '../media/MediaGrid';

const DOC_EXTENSIONS = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.rtf', '.odt', '.ods', '.odp'];
const PDF_ONLY = ['.pdf'];

type DocFilter = 'all' | 'pdf' | 'office' | 'text';

const FILTERS: { id: DocFilter; label: string; extensions: string[] }[] = [
  { id: 'all', label: 'All Documents', extensions: DOC_EXTENSIONS },
  { id: 'pdf', label: 'PDFs', extensions: PDF_ONLY },
  { id: 'office', label: 'Office', extensions: ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'] },
  { id: 'text', label: 'Text', extensions: ['.txt', '.rtf', '.odt', '.ods', '.odp'] },
];

const PAGE_SIZE = 60;

export function DocumentsView() {
  const [files, setFiles] = useState<MediaFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<DocFilter>('all');
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [total, setTotal] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  const loadDocuments = useCallback((filterType: DocFilter, pageNum: number, append: boolean) => {
    setLoading(true);
    const exts = FILTERS.find(f => f.id === filterType)?.extensions ?? DOC_EXTENSIONS;
    // Fetch from the API with type=documents param
    const params: Record<string, string | number> = { limit: PAGE_SIZE, page: pageNum, type: 'documents' };
    if (filterType === 'pdf') params.extension = '.pdf';
    else if (filterType === 'office') params.type = 'office';
    else if (filterType === 'text') params.type = 'text';

    api.media
      .list(params)
      .then(res => {
        const items = (res.items ?? []).filter(f => {
          const ext = (f.extension || '').toLowerCase();
          return exts.includes(ext);
        });
        setFiles(prev => append ? [...prev, ...items] : items);
        setTotal(res.total);
        setHasMore(items.length > 0 && pageNum * PAGE_SIZE < res.total);
      })
      .catch(() => { if (!append) setFiles([]); })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    setPage(1);
    setFiles([]);
    loadDocuments(filter, 1, false);
  }, [filter, loadDocuments]);

  const loadMore = useCallback(() => {
    if (loading || !hasMore) return;
    const nextPage = page + 1;
    setPage(nextPage);
    loadDocuments(filter, nextPage, true);
  }, [loading, hasMore, page, filter, loadDocuments]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el || loading || !hasMore) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 400) loadMore();
  }, [loadMore, loading, hasMore]);

  return (
    <motion.div
      className="flex h-full"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* Filter sidebar */}
      <div className="w-48 shrink-0 border-r border-[var(--glass-border)] overflow-y-auto py-3">
        <div className="px-3 mb-2">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-tertiary)]">Documents</span>
        </div>
        {FILTERS.map(f => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFilter(f.id)}
            className={`w-full flex items-center justify-between px-3 py-2 text-sm rounded-lg transition-colors ${
              filter === f.id
                ? 'bg-[var(--glass-bg)] text-[var(--text-primary)]'
                : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--glass-hover-bg)]'
            }`}
          >
            <span>{f.label}</span>
          </button>
        ))}
      </div>

      {/* Content */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4" onScroll={handleScroll}>
        <div className="flex items-baseline gap-3 mb-4">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">
            {FILTERS.find(f => f.id === filter)?.label}
          </h2>
          <span className="text-sm text-[var(--text-tertiary)]">{total} files</span>
        </div>

        <MediaGrid items={files} loading={loading && files.length === 0} />

        {hasMore && !loading && (
          <div className="flex justify-center py-6">
            <button type="button" onClick={loadMore} className="px-4 py-2 text-xs text-[var(--text-secondary)] bg-[var(--glass-bg)] rounded-xl hover:bg-[var(--glass-hover-bg)] transition-colors">
              Load more
            </button>
          </div>
        )}
      </div>
    </motion.div>
  );
}
