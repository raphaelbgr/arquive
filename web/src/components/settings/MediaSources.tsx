import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { Library } from '../../types';
import { api } from '../../api/client';

/** Server-side folder browser dialog */
function FolderBrowser({ isOpen, onSelect, onClose }: {
  isOpen: boolean;
  onSelect: (path: string) => void;
  onClose: () => void;
}) {
  const [items, setItems] = useState<{ name: string; path: string; type: string }[]>([]);
  const [currentPath, setCurrentPath] = useState('');
  const [loading, setLoading] = useState(false);

  const browse = useCallback((path: string) => {
    setLoading(true);
    fetch(`/api/v1/system/browse-folder?path=${encodeURIComponent(path)}`, { credentials: 'include' })
      .then(r => r.json())
      .then(data => {
        setItems(data.items ?? []);
        setCurrentPath(data.current ?? path);
      })
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (isOpen) browse('');
  }, [isOpen, browse]);

  if (!isOpen) return null;

  const parentPath = currentPath ? currentPath.replace(/[\\/][^\\/]*$/, '') : '';

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed inset-x-4 top-[10vh] bottom-[10vh] z-50 max-w-lg mx-auto flex flex-col rounded-2xl overflow-hidden"
        style={{ background: 'var(--surface-gradient)', border: '1px solid var(--glass-border)' }}>

        <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: 'var(--glass-border)' }}>
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Select Folder</h3>
          <button type="button" onClick={onClose} className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Cancel</button>
        </div>

        {currentPath && (
          <div className="px-4 py-2 border-b flex items-center gap-2" style={{ borderColor: 'var(--glass-border)' }}>
            <button
              type="button"
              onClick={() => browse(parentPath)}
              className="text-xs px-2 py-1 rounded-lg" style={{ background: 'var(--glass-bg)', color: 'var(--text-secondary)' }}
            >
              Up
            </button>
            <span className="text-xs font-mono truncate" style={{ color: 'var(--text-tertiary)' }}>{currentPath}</span>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-2">
          {loading ? (
            <div className="flex justify-center py-8">
              <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Loading...</span>
            </div>
          ) : items.length === 0 ? (
            <div className="flex justify-center py-8">
              <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Empty directory</span>
            </div>
          ) : (
            items.map(item => (
              <button
                key={item.path}
                type="button"
                onClick={() => browse(item.path)}
                className="w-full flex items-center gap-2 px-3 py-2 text-left rounded-lg transition-colors"
                style={{ color: 'var(--text-secondary)' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--glass-hover-bg)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  {item.type === 'drive'
                    ? <><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/></>
                    : <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                  }
                </svg>
                <span className="text-xs truncate">{item.name}</span>
              </button>
            ))
          )}
        </div>

        {currentPath && (
          <div className="px-4 py-3 border-t" style={{ borderColor: 'var(--glass-border)' }}>
            <button
              type="button"
              onClick={() => { onSelect(currentPath); onClose(); }}
              className="w-full py-2.5 rounded-xl text-xs font-medium transition-colors"
              style={{ background: 'var(--accent-color)', color: 'white' }}
            >
              Select This Folder
            </button>
          </div>
        )}
      </div>
    </>
  );
}

function formatSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

function formatDate(iso: string | null): string {
  if (!iso) return 'Never';
  return new Date(iso).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const SOURCE_TYPES = ['Local', 'SMB', 'SSH', 'FTP'];

const DISABLED_TYPES = [
  { name: 'iCloud', tooltip: 'Coming in v2 - iCloud Photos integration' },
  { name: 'Google Photos', tooltip: 'Coming in v2 - Google Photos integration' },
];

const TYPE_STYLES: Record<string, string> = {
  local: 'bg-blue-500/20 text-blue-300 border-blue-400/20',
  smb: 'bg-purple-500/20 text-purple-300 border-purple-400/20',
  ssh: 'bg-green-500/20 text-green-300 border-green-400/20',
  ftp: 'bg-amber-500/20 text-amber-300 border-amber-400/20',
};

export function MediaSources() {
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newName, setNewName] = useState('');
  const [newType, setNewType] = useState('Local');
  const [newPath, setNewPath] = useState('');
  const [adding, setAdding] = useState(false);
  const [browsingFolder, setBrowsingFolder] = useState(false);

  const fetchLibraries = useCallback(async () => {
    try {
      setError(null);
      const data = await api.settings.libraries();
      setLibraries(data.libraries ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load libraries');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLibraries();
  }, [fetchLibraries]);

  const handleAdd = async () => {
    if (!newName.trim() || !newPath.trim()) return;
    setAdding(true);
    try {
      await api.settings.addLibrary({
        name: newName.trim(),
        type: newType.toLowerCase(),
        path: newPath.trim(),
      });
      // Refresh the full list
      const data = await api.settings.libraries();
      setLibraries(data.libraries ?? []);
      setNewName('');
      setNewPath('');
      setNewType('Local');
      setShowAddForm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add library');
    } finally {
      setAdding(false);
    }
  };

  const handleRemove = async (id: number) => {
    try {
      await api.settings.removeLibrary(id);
      setLibraries((prev) => prev.filter((l) => l.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove library');
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-8 text-[var(--text-tertiary)] text-sm">Loading media sources...</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-[var(--text-primary)]">Media Sources</h3>
        <motion.button
          type="button"
          onClick={() => setShowAddForm(!showAddForm)}
          className="px-3 py-1.5 rounded-xl bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300
            border border-cyan-400/20 text-xs font-medium transition-colors"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          {showAddForm ? 'Cancel' : 'Add Source'}
        </motion.button>
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-red-500/15 border border-red-400/20 text-red-300 text-sm">{error}</div>
      )}

      {/* Add Form */}
      <AnimatePresence>
        {showAddForm && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="p-4 rounded-2xl bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)] space-y-3">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Library name"
                className="w-full px-3 py-2 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] text-[var(--text-primary)] text-sm
                  placeholder:text-[var(--text-tertiary)] focus:outline-none focus:ring-2 focus:ring-cyan-400/40"
              />

              <div className="flex gap-2">
                {SOURCE_TYPES.map((type) => (
                  <button
                    key={type}
                    type="button"
                    onClick={() => setNewType(type)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border
                      ${newType === type
                        ? 'bg-cyan-500/20 text-cyan-300 border-cyan-400/20'
                        : 'bg-[var(--glass-bg)] text-[var(--text-tertiary)] border-[var(--glass-border)] hover:bg-[var(--glass-hover-bg)]'
                      }`}
                  >
                    {type}
                  </button>
                ))}
                {DISABLED_TYPES.map((dt) => (
                  <div key={dt.name} className="relative group">
                    <button
                      type="button"
                      disabled
                      className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[var(--glass-bg)] text-[var(--text-tertiary)]
                        border border-[var(--glass-border)] cursor-not-allowed"
                    >
                      {dt.name}
                    </button>
                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 rounded-lg
                      bg-gray-900 text-[10px] text-[var(--text-secondary)] whitespace-nowrap opacity-0 group-hover:opacity-100
                      transition-opacity pointer-events-none">
                      {dt.tooltip}
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex gap-2">
                <input
                  type="text"
                  value={newPath}
                  onChange={(e) => setNewPath(e.target.value)}
                  placeholder={newType === 'SMB' ? '//server/share' : newType === 'SSH' ? 'user@host:/path' : '/path/to/media'}
                  className="flex-1 px-3 py-2 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] text-[var(--text-primary)] text-sm font-mono
                    placeholder:text-[var(--text-tertiary)] focus:outline-none focus:ring-2 focus:ring-cyan-400/40"
                />
                {newType === 'Local' && (
                  <button
                    type="button"
                    onClick={() => setBrowsingFolder(true)}
                    className="px-3 py-2 rounded-xl bg-[var(--glass-bg)] hover:bg-[var(--glass-hover-bg)] border border-[var(--glass-border)] text-[var(--text-secondary)] text-xs font-medium transition-colors shrink-0"
                  >
                    Browse
                  </button>
                )}
              </div>

              <motion.button
                type="button"
                onClick={handleAdd}
                disabled={adding || !newName.trim() || !newPath.trim()}
                className="w-full px-4 py-2.5 rounded-xl bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300
                  border border-cyan-400/20 text-sm font-medium transition-colors
                  disabled:opacity-40 disabled:cursor-not-allowed"
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.99 }}
              >
                {adding ? 'Adding...' : 'Add Source'}
              </motion.button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Libraries List */}
      <AnimatePresence mode="popLayout">
        {libraries.map((lib) => (
          <motion.div
            key={lib.id}
            layout
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="p-4 rounded-2xl bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)]"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h4 className="text-sm font-semibold text-[var(--text-primary)] truncate">{lib.name}</h4>
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-medium border
                    ${TYPE_STYLES[lib.type.toLowerCase()] ?? 'bg-gray-500/20 text-gray-300 border-gray-400/20'}`}>
                    {lib.type}
                  </span>
                </div>
                <p className="text-xs text-[var(--text-tertiary)] font-mono mt-1 truncate">{lib.path}</p>
                <div className="flex gap-4 mt-1.5 text-xs text-[var(--text-tertiary)]">
                  <span>{lib.file_count} files</span>
                  <span>{formatSize(lib.total_size)}</span>
                  <span>Scanned: {formatDate(lib.last_scanned)}</span>
                </div>
              </div>

              <button
                type="button"
                onClick={() => handleRemove(lib.id)}
                className="p-2 rounded-xl bg-[var(--glass-bg)] hover:bg-red-500/20 text-[var(--text-secondary)] hover:text-red-300 transition-colors shrink-0"
                title="Remove"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>

      {libraries.length === 0 && !error && (
        <p className="text-sm text-[var(--text-tertiary)] text-center py-4">No media sources configured</p>
      )}

      <FolderBrowser
        isOpen={browsingFolder}
        onSelect={(path) => setNewPath(path)}
        onClose={() => setBrowsingFolder(false)}
      />
    </div>
  );
}
