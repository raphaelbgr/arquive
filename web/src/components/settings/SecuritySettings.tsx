import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { api } from '../../api/client';

type AuthMode = 'none' | 'simple-password' | 'user-account';

interface AuthConfig {
  mode: AuthMode;
  users?: { username: string; role: string; last_login: string | null }[];
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

const MODE_INFO: Record<AuthMode, { title: string; description: string }> = {
  none: {
    title: 'No Authentication',
    description: 'Anyone on the network can access the application. Suitable for trusted home networks only.',
  },
  'simple-password': {
    title: 'Simple Password',
    description: 'A single shared password protects access. No individual user accounts.',
  },
  'user-account': {
    title: 'User Accounts',
    description: 'Individual user accounts with roles and permissions. Supports admin and viewer roles.',
  },
};

export function SecuritySettings() {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revoking, setRevoking] = useState(false);

  const fetchConfig = useCallback(async () => {
    try {
      setError(null);
      const data = await api.settings.getAll();
      setConfig({
        mode: (data.auth_mode as AuthMode) ?? 'none',
        users: (data.users ? JSON.parse(data.users) : []) as AuthConfig['users'],
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load security settings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleRevokeAll = async () => {
    setRevoking(true);
    try {
      await api.auth.revokeAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to revoke sessions');
    } finally {
      setRevoking(false);
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-8 text-[var(--text-tertiary)] text-sm">Loading security settings...</div>;
  }

  const mode = config?.mode ?? 'none';
  const modeInfo = MODE_INFO[mode];

  return (
    <div className="space-y-5">
      <h3 className="text-lg font-semibold text-[var(--text-primary)]">Security</h3>

      {error && (
        <div className="p-3 rounded-xl bg-red-500/15 border border-red-400/20 text-red-300 text-sm">{error}</div>
      )}

      {/* Current Mode */}
      <div className="p-4 rounded-2xl bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)] space-y-2">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">Authentication Mode</h4>
          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-medium bg-cyan-500/20 text-cyan-300 border border-cyan-400/20">
            {modeInfo.title}
          </span>
        </div>
        <p className="text-xs text-[var(--text-tertiary)]">{modeInfo.description}</p>
      </div>

      {/* Mode Info Cards */}
      <div className="space-y-2">
        {(Object.entries(MODE_INFO) as [AuthMode, typeof modeInfo][]).map(([key, info]) => (
          <div
            key={key}
            className={`p-3 rounded-xl border transition-colors
              ${key === mode
                ? 'bg-cyan-500/10 border-cyan-400/20'
                : 'bg-[var(--glass-bg)] border-[var(--glass-border)]'
              }`}
          >
            <p className={`text-sm font-medium ${key === mode ? 'text-cyan-300' : 'text-[var(--text-secondary)]'}`}>
              {info.title}
            </p>
            <p className="text-xs text-[var(--text-tertiary)] mt-0.5">{info.description}</p>
          </div>
        ))}
      </div>

      {/* Change Password (simple-password mode) */}
      {mode === 'simple-password' && (
        <motion.button
          type="button"
          className="w-full px-4 py-2.5 rounded-xl bg-[var(--glass-bg)] hover:bg-[var(--glass-hover-bg)] text-[var(--text-secondary)]
            border border-[var(--glass-border)] text-sm font-medium transition-colors"
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.99 }}
        >
          Change Password
        </motion.button>
      )}

      {/* User Management Table (user-account mode) */}
      {mode === 'user-account' && config?.users && (
        <div className="rounded-2xl bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)] overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--glass-border)]">
                <th className="px-4 py-3 text-left text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">User</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">Role</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">Last Login</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--glass-border)]">
              {config.users.map((user) => (
                <tr key={user.username} className="hover:bg-[var(--glass-hover-bg)] transition-colors">
                  <td className="px-4 py-3 text-[var(--text-primary)] font-medium">{user.username}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium border
                      ${user.role === 'admin'
                        ? 'bg-amber-500/20 text-amber-300 border-amber-400/20'
                        : 'bg-blue-500/20 text-blue-300 border-blue-400/20'
                      }`}>
                      {user.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-[var(--text-tertiary)] text-xs">{formatDate(user.last_login)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Revoke All Sessions */}
      <motion.button
        type="button"
        onClick={handleRevokeAll}
        disabled={revoking}
        className="w-full px-4 py-2.5 rounded-xl bg-red-500/15 hover:bg-red-500/25 text-red-300
          border border-red-400/20 text-sm font-medium transition-colors
          disabled:opacity-40 disabled:cursor-not-allowed"
        whileHover={{ scale: 1.01 }}
        whileTap={{ scale: 0.99 }}
      >
        {revoking ? 'Revoking...' : 'Revoke All Sessions'}
      </motion.button>
    </div>
  );
}
