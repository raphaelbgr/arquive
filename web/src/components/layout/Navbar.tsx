import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ThemeToggle } from '../ui/ThemeToggle';

export function Navbar() {
  const [searchQuery, setSearchQuery] = useState('');
  const navigate = useNavigate();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      navigate(`/browse?q=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  return (
    <motion.header
      className="glass-panel sticky top-0 z-40 h-16 px-6 flex items-center justify-between gap-4"
      initial={{ y: -64 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
    >
      <div className="flex items-center gap-3 shrink-0">
        <span className="text-xl font-bold tracking-tight text-adaptive">Arquive</span>
      </div>

      <form onSubmit={handleSearch} className="flex-1 max-w-md mx-auto">
        <div className="relative">
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 text-adaptive-tertiary"
            width="16" height="16" viewBox="0 0 24 24"
            fill="none" stroke="currentColor" strokeWidth="2"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search files, people, channels..."
            className="w-full h-9 pl-10 pr-4 glass-card text-sm text-adaptive placeholder:text-adaptive-tertiary outline-none focus:ring-1 focus:ring-[var(--accent-color)] transition-colors"
            style={{ borderRadius: '9999px' }}
          />
        </div>
      </form>

      <div className="flex items-center gap-3 shrink-0">
        <ThemeToggle />
        <button
          type="button"
          className="w-8 h-8 rounded-full glass-card flex items-center justify-center text-adaptive-secondary text-sm font-medium hover:opacity-80 transition-opacity"
          title="Account"
        >
          U
        </button>
      </div>
    </motion.header>
  );
}
