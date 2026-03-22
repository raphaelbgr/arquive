import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { api } from '../../api/client';

interface FaceConfig {
  model: string;
  threshold: number;
  det_size: number;
  reference_dir: string;
}

interface ScanStats {
  files_processed: number;
  matches_found: number;
  is_running: boolean;
}

const THRESHOLD_PRESETS = [
  { label: 'High Precision', value: 0.7, description: 'Fewer false positives, may miss some matches' },
  { label: 'Balanced', value: 0.5, description: 'Good balance of precision and recall' },
  { label: 'High Recall', value: 0.3, description: 'Catches more matches, may include false positives' },
];

export function FaceDetectionSettings() {
  const [config, setConfig] = useState<FaceConfig>({
    model: 'buffalo_l',
    threshold: 0.5,
    det_size: 640,
    reference_dir: '',
  });
  const [scanStats, setScanStats] = useState<ScanStats>({
    files_processed: 0,
    matches_found: 0,
    is_running: false,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [aiConfig, status] = await Promise.all([
        api.ai.config(),
        api.faces.scanStatus(),
      ]);
      setConfig({
        model: (aiConfig.model as string) ?? 'buffalo_l',
        threshold: (aiConfig.threshold as number) ?? 0.5,
        det_size: (aiConfig.det_size as number) ?? 640,
        reference_dir: (aiConfig.reference_dir as string) ?? '',
      });
      setScanStats({
        files_processed: (status.files_processed as number) ?? 0,
        matches_found: (status.matches_found as number) ?? 0,
        is_running: (status.is_running as boolean) ?? false,
      });
      setScanning((status.is_running as boolean) ?? false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load face detection settings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleThresholdChange = async (value: number) => {
    setConfig((prev) => ({ ...prev, threshold: value }));
    try {
      await api.settings.update({ face_threshold: value });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update threshold');
    }
  };

  const handleStartScan = async () => {
    setScanning(true);
    try {
      // Trigger scan via the API
      await api.settings.update({ trigger_face_scan: true });
      setScanStats((prev) => ({ ...prev, is_running: true }));
    } catch (err) {
      setScanning(false);
      setError(err instanceof Error ? err.message : 'Failed to start scan');
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-8 text-[var(--text-tertiary)] text-sm">Loading face detection settings...</div>;
  }

  return (
    <div className="space-y-5">
      <h3 className="text-lg font-semibold text-[var(--text-primary)]">Face Detection</h3>

      {error && (
        <div className="p-3 rounded-xl bg-red-500/15 border border-red-400/20 text-red-300 text-sm">{error}</div>
      )}

      {/* Current Model */}
      <div className="p-4 rounded-2xl bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)] space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-[var(--text-primary)]">Model</span>
          <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-500/20 text-purple-300 border border-purple-400/20">
            {config.model}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-[var(--text-primary)]">Detection Size</span>
          <span className="text-sm text-[var(--text-secondary)]">{config.det_size}px</span>
        </div>
      </div>

      {/* Threshold */}
      <div className="p-4 rounded-2xl bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)] space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-[var(--text-primary)]">Confidence Threshold</label>
          <span className="text-sm text-cyan-300 font-medium">{config.threshold.toFixed(2)}</span>
        </div>

        <input
          type="range"
          value={config.threshold}
          onChange={(e) => handleThresholdChange(parseFloat(e.target.value))}
          min={0.1}
          max={0.9}
          step={0.01}
          className="w-full h-1.5 rounded-full appearance-none bg-[var(--glass-bg)] accent-cyan-400
            [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full
            [&::-webkit-slider-thumb]:bg-cyan-400 [&::-webkit-slider-thumb]:appearance-none"
        />

        <div className="flex gap-2">
          {THRESHOLD_PRESETS.map((preset) => (
            <button
              key={preset.label}
              type="button"
              onClick={() => handleThresholdChange(preset.value)}
              className={`flex-1 px-2 py-2 rounded-xl text-center transition-colors border
                ${Math.abs(config.threshold - preset.value) < 0.05
                  ? 'bg-cyan-500/15 border-cyan-400/20'
                  : 'bg-[var(--glass-bg)] border-[var(--glass-border)] hover:bg-[var(--glass-hover-bg)]'
                }`}
            >
              <p className={`text-xs font-medium ${
                Math.abs(config.threshold - preset.value) < 0.05 ? 'text-cyan-300' : 'text-[var(--text-secondary)]'
              }`}>
                {preset.label}
              </p>
              <p className="text-[10px] text-[var(--text-tertiary)] mt-0.5">{preset.description}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Reference Faces Directory */}
      <div className="p-4 rounded-2xl bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)]">
        <p className="text-sm font-medium text-[var(--text-primary)]">Reference Faces Directory</p>
        <p className="text-xs text-[var(--text-tertiary)] font-mono mt-1 truncate">
          {config.reference_dir || 'Not configured'}
        </p>
      </div>

      {/* Scan Statistics */}
      <div className="p-4 rounded-2xl bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)] space-y-3">
        <h4 className="text-sm font-semibold text-[var(--text-primary)]">Scan Statistics</h4>
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] text-center">
            <p className="text-2xl font-bold text-[var(--text-primary)]">{scanStats.files_processed.toLocaleString()}</p>
            <p className="text-xs text-[var(--text-tertiary)] mt-0.5">Files Processed</p>
          </div>
          <div className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] text-center">
            <p className="text-2xl font-bold text-[var(--text-primary)]">{scanStats.matches_found.toLocaleString()}</p>
            <p className="text-xs text-[var(--text-tertiary)] mt-0.5">Matches Found</p>
          </div>
        </div>
      </div>

      {/* Start Scan */}
      <motion.button
        type="button"
        onClick={handleStartScan}
        disabled={scanning}
        className={`w-full px-4 py-3 rounded-xl text-sm font-medium transition-colors
          ${scanning
            ? 'bg-amber-500/20 text-amber-300 border border-amber-400/20'
            : 'bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-400/20'
          }
          disabled:cursor-not-allowed`}
        whileHover={scanning ? {} : { scale: 1.01 }}
        whileTap={scanning ? {} : { scale: 0.99 }}
      >
        {scanning ? 'Scan in Progress...' : 'Start Scan'}
      </motion.button>
    </div>
  );
}
