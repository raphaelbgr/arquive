import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import type { Person, FaceMatch, MediaFile } from '../../types';
import { api } from '../../api/client';
import { GlassCard } from '../ui/GlassCard';
import { MediaCard } from '../media/MediaCard';
import { MediaViewer } from '../media/MediaViewer';
import { FileInfoPanel } from '../media/FileInfoPanel';

/** Convert a face match to a MediaFile so we can reuse MediaCard */
function matchToMediaFile(match: FaceMatch): MediaFile {
  const ext = (match.file_path || '').split('.').pop()?.toLowerCase() || '';
  const mime = match.file_type === 'image' ? `image/${ext === 'jpg' ? 'jpeg' : ext}`
    : match.file_type === 'video' ? `video/${ext}` : 'application/octet-stream';

  // Build thumbnail URL from match data
  let thumbnail_path: string | null = null;
  if (match.thumbnail_path) {
    const tp = String(match.thumbnail_path).replace(/\\/g, '/');
    const fname = tp.split('/').pop() || '';
    thumbnail_path = tp.includes('video_thumbs') ? `/vthumb/${fname}` : `/thumb/${fname}`;
  }

  return {
    id: match.id,
    path: match.file_path,
    name: (match.file_path || '').replace(/\\/g, '/').split('/').pop() || 'Unknown',
    extension: `.${ext}`,
    size: 0,
    mime_type: mime,
    width: null,
    height: null,
    duration: match.timestamp_end && match.timestamp_start
      ? match.timestamp_end - match.timestamp_start : null,
    thumbnail_path,
    sprite_path: null,
    ai_description: match.description || `${match.person_name} - ${Math.round(match.confidence * 100)}% confidence`,
    metadata_json: null,
    library_id: null,
    created_at: null,
    modified_at: null,
  };
}

function PersonCard({ person, onClick, onDelete }: { person: Person; onClick: () => void; onDelete: () => void }) {
  return (
    <GlassCard className="cursor-pointer overflow-hidden relative group" hover>
      <button type="button" onClick={onClick} className="w-full text-left">
        <div className="aspect-square bg-[var(--glass-bg)] flex items-center justify-center">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-[var(--text-tertiary)]">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
        </div>
        <div className="p-3">
          <p className="text-sm font-medium text-[var(--text-primary)] truncate">{person.person_name}</p>
          <p className="text-xs text-[var(--text-tertiary)] mt-0.5">
            {person.match_count.toLocaleString()} {person.match_count === 1 ? 'match' : 'matches'}
          </p>
        </div>
      </button>
      {/* Delete button on hover */}
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onDelete(); }}
        className="absolute top-2 right-2 w-6 h-6 rounded-full bg-red-500/80 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
        title="Remove person"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
      </button>
    </GlassCard>
  );
}

function PersonDetail({ personName, onBack }: { personName: string; onBack: () => void }) {
  const [matches, setMatches] = useState<FaceMatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const [infoFile, setInfoFile] = useState<MediaFile | null>(null);

  useEffect(() => {
    setLoading(true);
    api.faces
      .person(personName)
      .then((data) => setMatches((data.matches ?? []) as unknown as FaceMatch[]))
      .catch(() => setMatches([]))
      .finally(() => setLoading(false));
  }, [personName]);

  const mediaFiles = matches.map(matchToMediaFile);

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <button
          type="button"
          onClick={onBack}
          className="w-8 h-8 rounded-lg bg-[var(--glass-bg)] hover:bg-[var(--glass-hover-bg)] flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">{personName}</h2>
        <span className="text-xs text-[var(--text-tertiary)]">{matches.length.toLocaleString()} matches</span>
      </div>

      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="shimmer aspect-video rounded-2xl" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
          {mediaFiles.map((file, idx) => (
            <MediaCard
              key={file.id}
              file={file}
              onClick={() => setViewerIndex(idx)}
              onInfo={() => setInfoFile(file)}
            />
          ))}
        </div>
      )}

      {viewerIndex !== null && mediaFiles[viewerIndex] && (
        <MediaViewer
          file={mediaFiles[viewerIndex]}
          isOpen={true}
          onClose={() => setViewerIndex(null)}
          onPrev={viewerIndex > 0 ? () => setViewerIndex(viewerIndex - 1) : undefined}
          onNext={viewerIndex < mediaFiles.length - 1 ? () => setViewerIndex(viewerIndex + 1) : undefined}
        />
      )}

      {infoFile && <FileInfoPanel file={infoFile} isOpen={true} onClose={() => setInfoFile(null)} />}
    </div>
  );
}

export function PeopleView() {
  const [persons, setPersons] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedPerson, setSelectedPerson] = useState<string | null>(null);
  const [newName, setNewName] = useState('');

  const loadPersons = () => {
    setLoading(true);
    api.faces
      .persons()
      .then((data) => setPersons((data.persons ?? []) as Person[]))
      .catch(() => setPersons([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadPersons(); }, []);

  const handleDelete = async (name: string) => {
    if (!window.confirm(`Remove "${name}" and all their face matches?`)) return;
    await fetch(`/api/v1/faces/persons/${encodeURIComponent(name)}`, { method: 'DELETE', credentials: 'include' });
    setPersons(prev => prev.filter(p => p.person_name !== name));
  };

  const handleAdd = async () => {
    const name = newName.trim();
    if (!name) return;
    await fetch('/api/v1/faces/persons', {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    setNewName('');
    loadPersons();
  };

  return (
    <motion.div className="p-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      {selectedPerson ? (
        <PersonDetail personName={selectedPerson} onBack={() => setSelectedPerson(null)} />
      ) : (
        <>
          <div className="flex items-center justify-between mb-6">
            <h1 className="text-xl font-semibold text-[var(--text-primary)]">People</h1>
            <div className="flex gap-2">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Add person..."
                onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
                className="h-8 px-3 text-xs rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] outline-none"
              />
              <button
                type="button"
                onClick={handleAdd}
                className="h-8 px-3 text-xs font-medium rounded-lg transition-colors"
                style={{ background: 'var(--accent-color)', color: 'white' }}
              >
                Add
              </button>
            </div>
          </div>
          {loading ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
              {Array.from({ length: 12 }).map((_, i) => (
                <div key={i} className="shimmer aspect-square rounded-2xl" />
              ))}
            </div>
          ) : persons.length === 0 ? (
            <div className="flex items-center justify-center h-64 text-[var(--text-tertiary)] text-sm">
              No people detected yet. Run a face scan from Settings.
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
              {persons.map((person) => (
                <PersonCard key={person.person_name} person={person} onClick={() => setSelectedPerson(person.person_name)} onDelete={() => handleDelete(person.person_name)} />
              ))}
            </div>
          )}
        </>
      )}
    </motion.div>
  );
}
