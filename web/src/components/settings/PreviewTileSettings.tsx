import { useState, useEffect } from 'react';
import type { PreviewTilesSettings, PreviewMode } from '../../types';
import { api } from '../../api/client';
import { GlassCard } from '../ui/GlassCard';

const modeOptions: { value: PreviewMode; label: string; description: string }[] = [
  { value: 'always', label: 'Always', description: 'Tiles cycle automatically on load' },
  { value: 'hover', label: 'On Hover', description: 'Tiles cycle when mouse hovers over them' },
  { value: 'off', label: 'Off', description: 'Show static poster image only' },
];

function ModeRadioGroup({
  label,
  value,
  onChange,
}: {
  label: string;
  value: PreviewMode;
  onChange: (v: PreviewMode) => void;
}) {
  return (
    <div className="space-y-2">
      <span className="text-xs font-medium text-[var(--text-secondary)]">{label}</span>
      <div className="space-y-1.5">
        {modeOptions.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={`
              w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-colors
              ${value === option.value
                ? 'bg-[#007AFF]/15 border border-[#007AFF]/30'
                : 'bg-[var(--glass-bg)] border border-[var(--glass-border)] hover:bg-[var(--glass-hover-bg)]'
              }
            `}
          >
            <div
              className={`
                w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0
                ${value === option.value ? 'border-[#007AFF]' : 'border-[var(--glass-border)]'}
              `}
            >
              {value === option.value && (
                <div className="w-2 h-2 rounded-full bg-[#007AFF]" />
              )}
            </div>
            <div>
              <p className="text-sm font-medium text-[var(--text-primary)]">{option.label}</p>
              <p className="text-[10px] text-[var(--text-tertiary)]">{option.description}</p>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

export function PreviewTileSettings() {
  const [settings, setSettings] = useState<PreviewTilesSettings>({
    mediaLibrary: 'hover',
    liveTV: 'always',
    frameIntervalMs: 1000,
    crossfadeDurationMs: 200,
    spriteFrameCount: 100,
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.settings
      .getPreviewTiles()
      .then(setSettings)
      .catch(() => {});
  }, []);

  const save = async (updated: PreviewTilesSettings) => {
    setSettings(updated);
    setSaving(true);
    try {
      await api.settings.setPreviewTiles(updated);
    } catch {
      // Silently fail
    } finally {
      setSaving(false);
    }
  };

  return (
    <GlassCard className="p-5" hover={false}>
      <div className="flex items-center justify-between mb-5">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Preview Tiles</h3>
        {saving && <span className="text-[10px] text-[#007AFF]">Saving...</span>}
      </div>

      <div className="space-y-6">
        {/* Media Library mode */}
        <ModeRadioGroup
          label="Media Library"
          value={settings.mediaLibrary}
          onChange={(v) => save({ ...settings, mediaLibrary: v })}
        />

        {/* Live TV mode */}
        <ModeRadioGroup
          label="Live TV"
          value={settings.liveTV}
          onChange={(v) => save({ ...settings, liveTV: v })}
        />

        {/* Frame interval slider */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[var(--text-secondary)]">Cycling Speed</span>
            <span className="text-xs text-[var(--text-tertiary)] tabular-nums">
              {(settings.frameIntervalMs / 1000).toFixed(1)}s
            </span>
          </div>
          <input
            type="range"
            min={500}
            max={3000}
            step={100}
            value={settings.frameIntervalMs}
            onChange={(e) =>
              save({ ...settings, frameIntervalMs: parseInt(e.target.value, 10) })
            }
            className="w-full h-1 bg-[var(--glass-bg)] rounded-full appearance-none cursor-pointer accent-[#007AFF]"
          />
          <div className="flex justify-between text-[9px] text-[var(--text-tertiary)]">
            <span>0.5s (fast)</span>
            <span>3.0s (slow)</span>
          </div>
        </div>

        {/* Crossfade slider */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[var(--text-secondary)]">Crossfade Duration</span>
            <span className="text-xs text-[var(--text-tertiary)] tabular-nums">
              {settings.crossfadeDurationMs}ms
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={500}
            step={25}
            value={settings.crossfadeDurationMs}
            onChange={(e) =>
              save({ ...settings, crossfadeDurationMs: parseInt(e.target.value, 10) })
            }
            className="w-full h-1 bg-[var(--glass-bg)] rounded-full appearance-none cursor-pointer accent-[#007AFF]"
          />
          <div className="flex justify-between text-[9px] text-[var(--text-tertiary)]">
            <span>0ms (instant)</span>
            <span>500ms (smooth)</span>
          </div>
        </div>
      </div>
    </GlassCard>
  );
}
