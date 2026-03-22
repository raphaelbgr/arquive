import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { MediaFile } from '../../types';
import { api } from '../../api/client';
import { MediaCard } from '../media/MediaCard';
import { MediaViewer } from '../media/MediaViewer';
import { FileInfoPanel } from '../media/FileInfoPanel';
import { FilterBar, filtersToParams } from '../media/FilterBar';
import type { Filters } from '../media/FilterBar';

interface MonthGroup {
  month: string;
  count: number;
}

interface MonthSection {
  month: string;
  totalCount: number;
  files: MediaFile[];
  page: number;
  loadingMore: boolean;
  fullyLoaded: boolean;
}

const INITIAL_PER_MONTH = 30;
const LOAD_MORE_BATCH = 40;

function formatMonth(m: string): string {
  try {
    const [year, month] = m.split('-');
    const date = new Date(parseInt(year), parseInt(month) - 1);
    return date.toLocaleDateString(undefined, { year: 'numeric', month: 'long' });
  } catch {
    return m;
  }
}

export function TimelineView() {
  const [groups, setGroups] = useState<MonthGroup[]>([]);
  const [sections, setSections] = useState<Map<string, MonthSection>>(new Map());
  const [loadingMonths, setLoadingMonths] = useState(true);
  const [loadingBatch, setLoadingBatch] = useState(false);
  const [viewerFile, setViewerFile] = useState<{ file: MediaFile; allFiles: MediaFile[]; index: number } | null>(null);
  const [infoFile, setInfoFile] = useState<MediaFile | null>(null);
  const [activeFilters, setActiveFilters] = useState<Filters>({});
  const scrollRef = useRef<HTMLDivElement>(null);

  // Multi-select state
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [selectionMode, setSelectionMode] = useState(false);

  const toggleSelection = useCallback((id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      // Exit selection mode if nothing selected
      if (next.size === 0) setSelectionMode(false);
      else setSelectionMode(true);
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
    setSelectionMode(false);
  }, []);

  const handleDeleteSelected = useCallback(async () => {
    if (selectedIds.size === 0) return;
    const confirmed = window.confirm(
      `Delete ${selectedIds.size} selected file(s) from the index? This does not remove the actual files from disk.`
    );
    if (!confirmed) return;

    const idsToDelete = Array.from(selectedIds);
    await Promise.allSettled(
      idsToDelete.map(id =>
        api.media.delete(id)
      )
    );

    // Remove deleted files from local state
    setSections(prev => {
      const next = new Map(prev);
      for (const [month, section] of next) {
        const filtered = section.files.filter(f => !selectedIds.has(f.id));
        if (filtered.length !== section.files.length) {
          next.set(month, { ...section, files: filtered, totalCount: section.totalCount - (section.files.length - filtered.length) });
        }
      }
      return next;
    });
    clearSelection();
  }, [selectedIds, clearSelection]);

  const handleDownloadSelected = useCallback(() => {
    for (const id of selectedIds) {
      window.open(`/api/v1/media/${id}/download`, '_blank');
    }
  }, [selectedIds]);

  useEffect(() => {
    api.media.timeline()
      .then(data => {
        const g = data.groups ?? [];
        setGroups(g);
        if (g.length > 0) {
          loadMonthsBatch(g.slice(0, 3).map(x => x.month));
        }
      })
      .catch(() => setGroups([]))
      .finally(() => setLoadingMonths(false));
  }, []);

  const activeFiltersRef = useRef(activeFilters);
  activeFiltersRef.current = activeFilters;

  const loadMonthsBatch = useCallback((months: string[]) => {
    const toLoad = months.filter(m => !sections.has(m));
    if (toLoad.length === 0) return;
    setLoadingBatch(true);

    const filterParams = filtersToParams(activeFiltersRef.current);

    // Use individual API calls so filters work (batch API doesn't support filters yet)
    Promise.all(toLoad.map(month =>
      api.media.list({ month, limit: INITIAL_PER_MONTH, page: 1, ...filterParams })
        .then(res => ({ month, items: res.items ?? [], total: res.total }))
        .catch(() => ({ month, items: [] as MediaFile[], total: 0 }))
    ))
      .then(results => {
        setSections(prev => {
          const next = new Map(prev);
          for (const data of results) {
            next.set(data.month, {
              month: data.month,
              totalCount: data.total,
              files: data.items,
              page: 1,
              loadingMore: false,
              fullyLoaded: data.items.length >= data.total,
            });
          }
          return next;
        });
      })
      .catch(() => {})
      .finally(() => setLoadingBatch(false));
  }, [sections]);

  // Load more files within a month — uses ref to avoid stale closure
  const sectionsRef = useRef(sections);
  sectionsRef.current = sections;

  const loadMoreInMonth = useCallback((month: string) => {
    const section = sectionsRef.current.get(month);
    if (!section || section.loadingMore || section.fullyLoaded) return;

    // Use current file count as offset — avoids page/limit mismatch
    const currentOffset = section.files.length;

    setSections(prev => {
      const next = new Map(prev);
      const s = next.get(month);
      if (s) next.set(month, { ...s, loadingMore: true });
      return next;
    });

    // Call API with explicit offset and active filters
    const fp = new URLSearchParams({
      month, limit: String(LOAD_MORE_BATCH), page: '1', offset: String(currentOffset),
      ...Object.fromEntries(Object.entries(filtersToParams(activeFiltersRef.current)).map(([k, v]) => [k, String(v)])),
    });
    fetch(`/api/v1/media?${fp}`, { credentials: 'include' })
      .then(r => r.json())
      .then((res: { items?: MediaFile[]; total?: number }) => {
        const newFiles = res.items ?? [];
        setSections(prev => {
          const next = new Map(prev);
          const current = next.get(month);
          if (!current) return next;
          const allFiles = [...current.files, ...newFiles];
          next.set(month, {
            ...current,
            files: allFiles,
            page: current.page + 1,
            loadingMore: false,
            fullyLoaded: allFiles.length >= current.totalCount || newFiles.length === 0,
          });
          return next;
        });
      })
      .catch(() => {
        setSections(prev => {
          const next = new Map(prev);
          const current = next.get(month);
          if (current) next.set(month, { ...current, loadingMore: false });
          return next;
        });
      });
  }, []);

  // Auto-load next months on scroll
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el || loadingBatch) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 800) {
      // Find next unloaded months
      const loaded = new Set(sections.keys());
      const nextBatch = groups
        .filter(g => !loaded.has(g.month))
        .slice(0, 2)
        .map(g => g.month);
      if (nextBatch.length > 0) {
        loadMonthsBatch(nextBatch);
      }
    }
  }, [loadingBatch, groups, sections, loadMonthsBatch]);

  // Jump to a specific month — only load THAT month, not everything in between
  const jumpToMonth = useCallback((month: string) => {
    const el = document.getElementById(`month-${month}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    // Not loaded yet — load just this month (single batch request)
    loadMonthsBatch([month]);
    setTimeout(() => {
      document.getElementById(`month-${month}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 500);
  }, [loadMonthsBatch]);

  // Sort sections by month descending for rendering
  const sortedSections = Array.from(sections.values()).sort((a, b) => b.month.localeCompare(a.month));

  if (loadingMonths) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--text-tertiary)] text-sm">
        Loading timeline...
      </div>
    );
  }

  return (
    <motion.div className="flex h-full" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      {/* Month sidebar */}
      <div className="w-40 shrink-0 border-r border-[var(--glass-border)] overflow-y-auto py-3">
        <div className="px-3 mb-2">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-tertiary)]">Timeline</span>
        </div>
        {groups.map(g => {
          const isLoaded = sections.has(g.month);
          return (
            <button
              key={g.month}
              type="button"
              onClick={() => jumpToMonth(g.month)}
              className={`w-full flex items-center justify-between px-3 py-1.5 text-[11px] rounded-lg transition-colors ${
                isLoaded
                  ? 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                  : 'text-[var(--text-tertiary)]'
              } hover:bg-[var(--glass-hover-bg)]`}
            >
              <span>{formatMonth(g.month)}</span>
              <span className="text-[9px] tabular-nums text-[var(--text-tertiary)]">{g.count.toLocaleString()}</span>
            </button>
          );
        })}
      </div>

      {/* Continuous scroll content */}
      <div ref={scrollRef} className="relative flex-1 overflow-y-auto p-4" onScroll={handleScroll}>
        {/* Filter bar */}
        <FilterBar
          filters={activeFilters}
          onChange={(f) => {
            setActiveFilters(f);
            // Reset and reload with filters
            setSections(new Map());
            // Reload first 3 months with new filters
            if (groups.length > 0) {
              loadMonthsBatch(groups.slice(0, 3).map(g => g.month));
            }
          }}
        />

        {/* Floating selection action bar */}
        <AnimatePresence>
          {selectionMode && selectedIds.size > 0 && (
            <motion.div
              className="sticky top-0 z-20 mb-4 flex items-center justify-between rounded-2xl px-4 py-2.5 backdrop-blur-xl"
              style={{
                background: 'var(--glass-bg)',
                borderColor: 'var(--glass-border)',
                borderWidth: '1px',
                borderStyle: 'solid',
              }}
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.2 }}
            >
              <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                {selectedIds.size} selected
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleDownloadSelected}
                  className="rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
                  style={{ color: 'var(--text-primary)', background: 'var(--glass-hover-bg)' }}
                >
                  Download
                </button>
                <button
                  type="button"
                  onClick={handleDeleteSelected}
                  className="rounded-lg bg-red-500/20 px-3 py-1.5 text-xs font-medium text-red-400 transition-colors hover:bg-red-500/30"
                >
                  Delete
                </button>
                <button
                  type="button"
                  onClick={clearSelection}
                  className="rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
                  style={{ color: 'var(--text-secondary)', background: 'var(--glass-hover-bg)' }}
                >
                  Cancel
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {sortedSections.map(section => {
          const remaining = section.totalCount - section.files.length;
          return (
            <section key={section.month} id={`month-${section.month}`} className="mb-10">
              <div className="flex items-baseline gap-3 mb-3 sticky top-0 py-2 z-10" style={{ background: 'var(--surface-gradient)' }}>
                <h2 className="text-lg font-semibold text-[var(--text-primary)]">{formatMonth(section.month)}</h2>
                <span className="text-xs text-[var(--text-tertiary)]">
                  {section.files.length.toLocaleString()} of {section.totalCount.toLocaleString()}
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
                {section.files.map((file, idx) => (
                  <MediaCard
                    key={file.id}
                    file={file}
                    onClick={() => setViewerFile({ file, allFiles: section.files, index: idx })}
                    onInfo={() => setInfoFile(file)}
                    isSelected={selectedIds.has(file.id)}
                    onSelect={() => toggleSelection(file.id)}
                    selectionMode={selectionMode}
                  />
                ))}

                {/* Shimmer placeholders while loading more */}
                <AnimatePresence>
                  {section.loadingMore && Array.from({ length: 6 }).map((_, i) => (
                    <motion.div
                      key={`shim-${i}`}
                      className="aspect-video rounded-2xl shimmer"
                      initial={{ opacity: 0, scale: 0.9 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ delay: i * 0.04, duration: 0.2 }}
                    />
                  ))}
                </AnimatePresence>

                {/* Load more button as last grid item */}
                {remaining > 0 && !section.loadingMore && (
                  <motion.button
                    type="button"
                    onClick={() => loadMoreInMonth(section.month)}
                    className="aspect-video rounded-2xl glass-card flex flex-col items-center justify-center gap-2 cursor-pointer group"
                    whileHover={{ scale: 1.03, y: -2 }}
                    whileTap={{ scale: 0.97 }}
                  >
                    <motion.div
                      className="w-10 h-10 rounded-full glass-card flex items-center justify-center group-hover:bg-[var(--accent-color)] transition-colors"
                      whileHover={{ rotate: 90 }}
                      transition={{ duration: 0.2 }}
                    >
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-[var(--text-tertiary)] group-hover:text-white transition-colors">
                        <line x1="12" y1="5" x2="12" y2="19" />
                        <line x1="5" y1="12" x2="19" y2="12" />
                      </svg>
                    </motion.div>
                    <span className="text-[10px] font-medium text-[var(--text-tertiary)] group-hover:text-[var(--text-secondary)] transition-colors">
                      {remaining.toLocaleString()} more
                    </span>
                  </motion.button>
                )}
              </div>
            </section>
          );
        })}

        {loadingBatch && (
          <div className="flex justify-center py-8">
            <span className="text-sm text-[var(--text-tertiary)]">Loading...</span>
          </div>
        )}
      </div>

      {viewerFile && (
        <MediaViewer
          file={viewerFile.file}
          isOpen={true}
          onClose={() => setViewerFile(null)}
          onPrev={viewerFile.index > 0 ? () => setViewerFile({
            file: viewerFile.allFiles[viewerFile.index - 1],
            allFiles: viewerFile.allFiles,
            index: viewerFile.index - 1,
          }) : undefined}
          onNext={viewerFile.index < viewerFile.allFiles.length - 1 ? () => setViewerFile({
            file: viewerFile.allFiles[viewerFile.index + 1],
            allFiles: viewerFile.allFiles,
            index: viewerFile.index + 1,
          }) : undefined}
        />
      )}

      {infoFile && <FileInfoPanel file={infoFile} isOpen={true} onClose={() => setInfoFile(null)} />}
    </motion.div>
  );
}
