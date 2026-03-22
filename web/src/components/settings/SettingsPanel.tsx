import { useState } from 'react';
import { motion } from 'framer-motion';
import { GlassCard } from '../ui/GlassCard';
import { ThemeToggle } from '../ui/ThemeToggle';
import { PreviewTileSettings } from './PreviewTileSettings';
import { CacheSettings } from './CacheSettings';
import { FleetStatus } from './FleetStatus';
import { SecuritySettings } from './SecuritySettings';
import { MediaSources } from './MediaSources';
import { IPTVSettings } from './IPTVSettings';
import { FaceDetectionSettings } from './FaceDetectionSettings';

type SettingsTab = 'general' | 'cache' | 'iptv' | 'fleet' | 'security' | 'preview' | 'faces';

const tabs: { id: SettingsTab; label: string }[] = [
  { id: 'general', label: 'General' },
  { id: 'cache', label: 'Cache' },
  { id: 'iptv', label: 'IPTV' },
  { id: 'fleet', label: 'Fleet' },
  { id: 'security', label: 'Security' },
  { id: 'faces', label: 'Face Detection' },
  { id: 'preview', label: 'Preview Tiles' },
];

function GeneralSection() {
  return (
    <div className="space-y-6">
      <GlassCard className="p-5" hover={false}>
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">Theme</h3>
        <ThemeToggle />
      </GlassCard>
      <MediaSources />
    </div>
  );
}

export function SettingsPanel() {
  const [activeTab, setActiveTab] = useState<SettingsTab>('general');

  const renderSection = () => {
    switch (activeTab) {
      case 'general':
        return <GeneralSection />;
      case 'cache':
        return <CacheSettings />;
      case 'iptv':
        return <IPTVSettings />;
      case 'fleet':
        return <FleetStatus />;
      case 'security':
        return <SecuritySettings />;
      case 'faces':
        return <FaceDetectionSettings />;
      case 'preview':
        return <PreviewTileSettings />;
    }
  };

  return (
    <motion.div
      className="p-6 max-w-3xl mx-auto"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      <h1 className="text-xl font-semibold text-[var(--text-primary)] mb-6">Settings</h1>

      <div className="flex gap-1 mb-6 p-1 bg-[var(--glass-bg)] rounded-xl overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`
              relative px-4 py-2 text-xs font-medium rounded-lg whitespace-nowrap transition-colors
              ${activeTab === tab.id ? 'text-[var(--text-primary)]' : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'}
            `}
          >
            {activeTab === tab.id && (
              <motion.div
                className="absolute inset-0 bg-[var(--glass-bg)] rounded-lg"
                layoutId="settings-tab"
                transition={{ duration: 0.2 }}
              />
            )}
            <span className="relative z-10">{tab.label}</span>
          </button>
        ))}
      </div>

      {renderSection()}
    </motion.div>
  );
}
