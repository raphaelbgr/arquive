import { motion } from 'framer-motion';
import type { ReactNode } from 'react';

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}

export function GlassCard({ children, className = '', hover = true }: GlassCardProps) {
  return (
    <motion.div
      className={`
        bg-[var(--glass-bg)]
        backdrop-blur-xl
        border border-[var(--glass-border)]
        rounded-2xl
        shadow-lg shadow-black/5
        ${className}
      `}
      whileHover={hover ? { scale: 1.01, backgroundColor: 'rgba(255, 255, 255, 0.14)' } : undefined}
      transition={{ duration: 0.2, ease: 'easeOut' }}
    >
      {children}
    </motion.div>
  );
}
