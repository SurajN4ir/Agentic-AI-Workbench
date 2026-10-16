import React, { useEffect, useState } from 'react'
import { api } from './api/client'
import type { HealthStatus, User } from './types/auth'
import { Shield, ShieldAlert, ShieldCheck, Server, User as UserIcon, Lock, LogOut } from 'lucide-react'

export const App: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [ready, setReady] = useState<HealthStatus | null>(null)
  const [currentUser, setCurrentUser] = useState<User | null>(null)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loginError, setLoginError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    // Initial health checks
    api.checkHealth()
      .then(setHealth)
      .catch(() => setHealth({ status: 'unreachable' }))

    api.checkReady()
      .then(setReady)
      .catch(() => setReady({ status: 'not_ready', database: 'unreachable' }))

    // If token exists, fetch profile
    if (api.getToken()) {
      api.getMe()
        .then(setCurrentUser)
        .catch(() => api.setToken(null))
    }
  }, [])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoginError(null)
    setLoading(true)
    try {
      const resp = await api.login(username, password)
      if (resp.requires_2fa) {
        setLoginError('2FA challenge required. Complete TOTP verification.')
      } else {
        const user = await api.getMe()
        setCurrentUser(user)
        setPassword('')
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setLoginError(err.message)
      } else {
        setLoginError('Authentication failed')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = async () => {
    await api.logout()
    setCurrentUser(null)
  }

  return (
    <div className="min-h-screen bg-black text-white flex flex-col font-sans">
      {/* Top Header */}
      <header className="border-b border-neutral-800 bg-neutral-950 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-neutral-900 border border-neutral-700 flex items-center justify-center">
            <Shield className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight text-white leading-tight">
              Sovereign Workbench
            </h1>
            <p className="text-xs text-neutral-400">
              On-Premise Industrial AI &middot; Air-Gapped Foundation
            </p>
          </div>
        </div>

        {/* System Health Indicators */}
        <div className="flex items-center gap-4 text-xs font-mono">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-neutral-900 border border-neutral-800">
            <Server className="h-3.5 w-3.5 text-neutral-400" />
            <span className="text-neutral-400">API:</span>
            <span className={health?.status === 'ok' ? 'text-emerald-400' : 'text-amber-400'}>
              {health?.status ?? 'checking...'}
            </span>
          </div>

          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-neutral-900 border border-neutral-800">
            <span className="text-neutral-400">DB:</span>
            <span className={ready?.database === 'ok' ? 'text-emerald-400' : 'text-neutral-500'}>
              {ready?.database ?? 'standby'}
            </span>
          </div>

          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-neutral-900 border border-neutral-800">
            <ShieldCheck className="h-3.5 w-3.5 text-blue-400" />
            <span className="text-neutral-300">Phase 1: Core</span>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-4xl w-full mx-auto p-8 flex flex-col justify-center">
        {currentUser ? (
          /* Authenticated User View */
          <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-8 space-y-6">
            <div className="flex items-center justify-between border-b border-neutral-800 pb-5">
              <div className="flex items-center gap-3">
                <div className="h-12 w-12 rounded-full bg-neutral-800 border border-neutral-700 flex items-center justify-center font-bold text-lg">
                  {currentUser.name.charAt(0)}
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-white">{currentUser.name}</h2>
                  <p className="text-xs text-neutral-400 font-mono">
                    @{currentUser.username} &middot; Role: <span className="text-emerald-400 uppercase font-bold">{currentUser.role}</span>
                  </p>
                </div>
              </div>
              <button
                onClick={handleLogout}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-neutral-900 hover:bg-neutral-800 border border-neutral-700 text-xs font-medium text-neutral-300 transition"
              >
                <LogOut className="h-3.5 w-3.5" />
                Logout
              </button>
            </div>

            <div className="grid grid-cols-2 gap-4 text-xs">
              <div className="p-4 rounded-lg bg-neutral-900/50 border border-neutral-800">
                <span className="text-neutral-400 block mb-1">Department</span>
                <span className="text-white font-medium">{currentUser.department || 'Not specified'}</span>
              </div>
              <div className="p-4 rounded-lg bg-neutral-900/50 border border-neutral-800">
                <span className="text-neutral-400 block mb-1">Two-Factor Authentication</span>
                <span className={currentUser.totp_enabled ? 'text-emerald-400 font-medium' : 'text-neutral-500 font-medium'}>
                  {currentUser.totp_enabled ? 'Enforced (TOTP Active)' : 'Not Enabled'}
                </span>
              </div>
            </div>

            <div className="p-4 rounded-lg bg-neutral-900/30 border border-neutral-800/80">
              <h3 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-emerald-400" />
                Security Verification
              </h3>
              <p className="text-xs text-neutral-400 leading-relaxed">
                Authentication verified via air-gapped HMAC-SHA256 Bearer JWT. Session active in PostgreSQL with append-only audit tracking. Next phases will unlock confidential agent workflows and document pipelines.
              </p>
            </div>
          </div>
        ) : (
          /* Authentication Screen */
          <div className="max-w-md w-full mx-auto space-y-6">
            <div className="text-center space-y-2">
              <h2 className="text-xl font-bold tracking-tight text-white">
                Sovereign Authentication
              </h2>
              <p className="text-xs text-neutral-400">
                Access your confidential on-premise workbench
              </p>
            </div>

            <form onSubmit={handleLogin} className="bg-neutral-950 border border-neutral-800 rounded-xl p-6 space-y-4">
              {loginError && (
                <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-200 text-xs flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4 shrink-0 text-rose-400" />
                  <span>{loginError}</span>
                </div>
              )}

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-neutral-300 flex items-center gap-1.5">
                  <UserIcon className="h-3.5 w-3.5 text-neutral-400" />
                  Username
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="e.g. sysadmin"
                  required
                  className="w-full px-3 py-2 bg-neutral-900 border border-neutral-800 rounded-lg text-sm text-white placeholder-neutral-500 focus:outline-none focus:border-neutral-600 transition font-mono"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-neutral-300 flex items-center gap-1.5">
                  <Lock className="h-3.5 w-3.5 text-neutral-400" />
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  required
                  className="w-full px-3 py-2 bg-neutral-900 border border-neutral-800 rounded-lg text-sm text-white placeholder-neutral-500 focus:outline-none focus:border-neutral-600 transition font-mono"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 px-4 rounded-lg bg-white hover:bg-neutral-200 text-black font-semibold text-xs tracking-wide transition uppercase disabled:opacity-50"
              >
                {loading ? 'Authenticating...' : 'Sign In'}
              </button>

              <div className="pt-2 text-center">
                <p className="text-[11px] text-neutral-500">
                  Initial setup? Use <code className="text-neutral-400 bg-neutral-900 px-1 py-0.5 rounded font-mono">python scripts/setup_admin.py</code>
                </p>
              </div>
            </form>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-neutral-900 px-6 py-3 text-center text-[11px] text-neutral-600 font-mono">
        Sovereign On-Premise Workbench &middot; Local Offline Inference &middot; Zero Outbound WAN Telemetry
      </footer>
    </div>
  )
}
