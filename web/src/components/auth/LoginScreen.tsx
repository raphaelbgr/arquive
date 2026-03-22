import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { api } from '../../api/client';
import { GlassCard } from '../ui/GlassCard';

type AuthMode = 'forever' | 'simple-password' | 'user-account' | 'loading';

export function LoginScreen() {
  const [authMode, setAuthMode] = useState<AuthMode>('loading');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    // Check current auth mode
    api.auth
      .me()
      .then((info) => {
        const mode = info.sec_level ?? '';
        if (mode === 'forever') {
          navigate('/browse', { replace: true });
          return;
        }
        if (mode === 'simple-password') {
          setAuthMode('simple-password');
        } else {
          setAuthMode('user-account');
        }
      })
      .catch(() => {
        // If we get an error, assume user-account mode
        setAuthMode('user-account');
      });
  }, [navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const data: { username?: string; password: string } = { password };
      if (authMode === 'user-account') {
        data.username = username;
      }
      await api.auth.login(data);
      navigate('/browse', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setSubmitting(false);
    }
  };

  if (authMode === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="shimmer w-80 h-64 rounded-3xl" />
      </div>
    );
  }

  if (authMode === 'forever') {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <GlassCard className="p-8 text-center max-w-sm w-full" hover={false}>
          <h1 className="text-lg font-semibold text-[var(--text-primary)] mb-2">Arquive</h1>
          <p className="text-sm text-[var(--text-tertiary)]">No authentication required</p>
          <button
            type="button"
            onClick={() => navigate('/browse')}
            className="mt-4 px-6 h-10 bg-[#007AFF]/20 text-[#007AFF] text-sm font-medium rounded-xl hover:bg-[#007AFF]/30 transition-colors"
          >
            Continue
          </button>
        </GlassCard>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.4, ease: [0.32, 0.72, 0, 1] }}
        className="w-full max-w-sm"
      >
        <GlassCard className="p-8" hover={false}>
          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold text-[var(--text-primary)] mb-1">Arquive</h1>
            <p className="text-xs text-[var(--text-tertiary)]">Sign in to continue</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {authMode === 'user-account' && (
              <div>
                <label className="block text-xs font-medium text-[var(--text-tertiary)] mb-1.5">Username</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  className="
                    w-full h-10 px-4
                    bg-[var(--glass-bg)] border border-[var(--glass-border)]
                    rounded-xl text-sm text-[var(--text-primary)]
                    placeholder:text-[var(--text-tertiary)]
                    outline-none focus:border-[var(--glass-border)]
                    transition-colors
                  "
                  placeholder="Enter username"
                />
              </div>
            )}

            <div>
              <label className="block text-xs font-medium text-[var(--text-tertiary)] mb-1.5">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                className="
                  w-full h-10 px-4
                  bg-white/6 border border-white/10
                  rounded-xl text-sm text-white/80
                  placeholder:text-white/20
                  outline-none focus:border-white/25
                  transition-colors
                "
                placeholder="Enter password"
              />
            </div>

            {error && (
              <motion.p
                className="text-xs text-red-400/70 text-center"
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
              >
                {error}
              </motion.p>
            )}

            <button
              type="submit"
              disabled={submitting || !password}
              className="
                w-full h-10
                bg-[#007AFF] hover:bg-[#0056CC]
                disabled:opacity-40 disabled:cursor-not-allowed
                text-white text-sm font-semibold
                rounded-xl
                transition-colors
              "
            >
              {submitting ? 'Signing in...' : 'Sign In'}
            </button>
          </form>
        </GlassCard>
      </motion.div>
    </div>
  );
}
