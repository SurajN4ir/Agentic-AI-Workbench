import React, { useEffect, useState } from 'react'
import { api } from './api/client'
import type { HealthStatus, User } from './types/auth'
import type { ArtifactInfo, RouteDecision, ToolResultItem } from './types/workbench'
import {
  Shield,
  Server,
  User as UserIcon,
  LogOut,
  Cpu,
  Database,
  Terminal,
  FileText,
  Download,
  Play,
  RotateCw,
  CheckCircle2,
  XCircle,
  Sparkles,
  ChevronDown,
  ChevronRight,
  Award,
} from 'lucide-react'
import { BenchmarkDashboard } from './components/BenchmarkDashboard'
import { KnowledgeHub } from './components/KnowledgeHub'


export const App: React.FC = () => {
  // Auth & System Health
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [ready, setReady] = useState<HealthStatus | null>(null)
  const [currentUser, setCurrentUser] = useState<User | null>(null)
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [loginError, setLoginError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // Active Tab: 'workbench' | 'knowledge' | 'sandbox' | 'benchmarks'
  const [activeTab, setActiveTab] = useState<'workbench' | 'knowledge' | 'sandbox' | 'benchmarks'>('workbench')

  // Workbench State
  const [prompt, setPrompt] = useState('')
  const [roleOverride, setRoleOverride] = useState<string>('auto')
  const [agentRunning, setAgentRunning] = useState(false)
  const [agentStatus, setAgentStatus] = useState<string | null>(null)
  const [routeDecision, setRouteDecision] = useState<RouteDecision | null>(null)
  const [thinkingSteps, setThinkingSteps] = useState<string[]>([])
  const [showThinking, setShowThinking] = useState(true)
  const [liveTools, setLiveTools] = useState<ToolResultItem[]>([])
  const [agentResponse, setAgentResponse] = useState<string | null>(null)
  const [citationsVerified, setCitationsVerified] = useState<boolean | null>(null)
  const [ungroundedCitations, setUngroundedCitations] = useState<string[]>([])
  const [sessionArtifacts, setSessionArtifacts] = useState<ArtifactInfo[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string>('session_' + Math.random().toString(36).substring(2, 9))

  // Math & Sandbox Quick Tester
  const [mathExpr, setMathExpr] = useState('integrate(x**2 * sin(x), x)')
  const [mathOperation, setMathOperation] = useState('integrate')
  const [mathOutput, setMathOutput] = useState<string | null>(null)

  useEffect(() => {
    // Initial health checks
    api.checkHealth().then(setHealth).catch(() => setHealth({ status: 'unreachable' }))
    api.checkReady().then(setReady).catch(() => setReady({ status: 'not_ready', database: 'unreachable' }))

    if (api.getToken()) {
      api.getMe().then(setCurrentUser).catch(() => api.setToken(null))
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
      setLoginError(err instanceof Error ? err.message : 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = async () => {
    await api.logout()
    setCurrentUser(null)
  }

  // --- Run Agent with SSE Streaming ---
  const handleExecuteAgent = async () => {
    if (!prompt.trim() || agentRunning) return

    setAgentRunning(true)
    setAgentStatus('Initiating Sovereign Agent loop...')
    setRouteDecision(null)
    setThinkingSteps([])
    setLiveTools([])
    setAgentResponse(null)
    setSessionArtifacts([])

    try {
      await api.streamAgentTask(
        prompt,
        (event, data) => {
          if (event === 'status') {
            setAgentStatus(data.status)
          } else if (event === 'route') {
            setRouteDecision(data)
            setAgentStatus(`Routed to ${data.role} via ${data.method} (${Math.round(data.confidence * 100)}%)`)
          } else if (event === 'thinking') {
            setThinkingSteps((prev) => [...prev, data.content])
          } else if (event === 'tool_call') {
            setAgentStatus(`Executing tool: ${data.name}...`)
          } else if (event === 'tool_result') {
            setLiveTools((prev) => [...prev, data])
          } else if (event === 'done') {
            setAgentResponse(data.response)
            setAgentStatus(`Task finished (${data.status}) in ${data.duration_ms}ms`)
            if (data.citations_verified !== undefined) {
              setCitationsVerified(data.citations_verified)
              setUngroundedCitations(data.ungrounded_citations || [])
            }
          }
        },
        roleOverride === 'auto' ? undefined : roleOverride,
        currentSessionId,
      )

      // Fetch artifacts generated during task
      const arts = await api.listArtifacts(currentSessionId)
      setSessionArtifacts(arts)
    } catch (err) {
      setAgentStatus(`Execution error: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setAgentRunning(false)
    }
  }



  // --- Quick Math Tester ---
  const handleRunMath = async () => {
    setMathOutput('Evaluating expression symbolically...')
    try {
      const res = await fetch('/api/v1/tools/math', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${api.getToken()}`,
        },
        body: JSON.stringify({
          expression: mathExpr,
          operation: mathOperation,
        }),
      })
      const data = await res.json()
      if (res.ok) {
        setMathOutput(data.output || data.result_text || JSON.stringify(data.data, null, 2))
      } else {
        setMathOutput(`Error: ${data.detail || 'Evaluation failed'}`)
      }
    } catch (err) {
      setMathOutput(`Error: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  return (
    <div className="min-h-screen bg-black text-white flex flex-col font-sans selection:bg-neutral-800">
      {/* Top Sovereign Navigation Header */}
      <header className="border-b border-neutral-800 bg-neutral-950 px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-neutral-900 border border-neutral-700 flex items-center justify-center">
            <Shield className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight text-white leading-tight flex items-center gap-2">
              Sovereign Workbench
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800 font-mono">
                AIR-GAPPED
              </span>
            </h1>
            <p className="text-xs text-neutral-400">
              Confidential Industrial AI Engine &middot; Local-First Monolith
            </p>
          </div>
        </div>

        {/* Health Monitors & Status */}
        <div className="flex items-center gap-3 text-xs font-mono">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-neutral-900 border border-neutral-800">
            <Server className="h-3.5 w-3.5 text-neutral-400" />
            <span className="text-neutral-400">API:</span>
            <span className={health?.status === 'ok' ? 'text-emerald-400' : 'text-amber-400'}>
              {health?.status ?? '...'}
            </span>
          </div>

          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-neutral-900 border border-neutral-800">
            <Database className="h-3.5 w-3.5 text-neutral-400" />
            <span className="text-neutral-400">pgvector:</span>
            <span className={ready?.database === 'ok' ? 'text-emerald-400' : 'text-neutral-500'}>
              {ready?.database ?? 'standby'}
            </span>
          </div>

          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-neutral-900 border border-neutral-800">
            <Cpu className="h-3.5 w-3.5 text-blue-400" />
            <span className="text-neutral-400">Ollama:</span>
            <span className="text-blue-400">Local (Loopback)</span>
          </div>

          {currentUser ? (
            <div className="flex items-center gap-3 pl-2 border-l border-neutral-800">
              <div className="flex items-center gap-2">
                <div className="h-6 w-6 rounded-full bg-slate-700 flex items-center justify-center text-xs font-bold text-white uppercase">
                  {currentUser.username[0]}
                </div>
                <div className="flex flex-col">
                  <span className="text-xs font-medium text-white">{currentUser.username}</span>
                  <span className="text-[10px] text-neutral-400 uppercase font-mono">{currentUser.role}</span>
                </div>
              </div>
              <button
                onClick={handleLogout}
                className="p-1.5 rounded hover:bg-neutral-800 text-neutral-400 hover:text-white transition-colors"
                title="Logout"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          ) : null}
        </div>
      </header>

      {/* Main Workspace Body */}
      {!currentUser ? (
        /* Login Card */
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="w-full max-w-sm rounded-xl border border-neutral-800 bg-neutral-950 p-6 shadow-2xl">
            <div className="flex items-center gap-2 mb-4">
              <UserIcon className="h-5 w-5 text-neutral-400" />
              <h2 className="text-lg font-semibold text-white">Sovereign Sign In</h2>
            </div>
            <p className="text-xs text-neutral-400 mb-6">
              Enter your local on-premise credentials to access the workbench.
            </p>

            {loginError && (
              <div className="mb-4 rounded-lg bg-red-950/60 border border-red-800/80 p-3 text-xs text-red-300">
                {loginError}
              </div>
            )}

            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1">Username</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full rounded-lg bg-neutral-900 border border-neutral-800 px-3 py-2 text-sm text-white focus:border-neutral-600 focus:outline-none"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-lg bg-neutral-900 border border-neutral-800 px-3 py-2 text-sm text-white focus:border-neutral-600 focus:outline-none"
                  required
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full mt-2 rounded-lg bg-white text-black font-semibold py-2 px-4 text-sm hover:bg-neutral-200 transition-colors disabled:opacity-50"
              >
                {loading ? 'Authenticating...' : 'Sign In'}
              </button>
            </form>
          </div>
        </div>
      ) : (
        /* Authenticated Workbench Dashboard */
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Sub Navigation Bar */}
          <div className="border-b border-neutral-800 bg-neutral-950/60 px-6 flex items-center justify-between">
            <div className="flex gap-1 py-2">
              <button
                onClick={() => setActiveTab('workbench')}
                className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  activeTab === 'workbench'
                    ? 'bg-neutral-800 text-white shadow-sm'
                    : 'text-neutral-400 hover:text-white hover:bg-neutral-900'
                }`}
              >
                <Sparkles className="h-3.5 w-3.5 text-blue-400" />
                Agent Workbench
              </button>

              <button
                onClick={() => setActiveTab('knowledge')}
                className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  activeTab === 'knowledge'
                    ? 'bg-neutral-800 text-white shadow-sm'
                    : 'text-neutral-400 hover:text-white hover:bg-neutral-900'
                }`}
              >
                <FileText className="h-3.5 w-3.5 text-emerald-400" />
                Knowledge Base (RAG)
              </button>

              <button
                onClick={() => setActiveTab('sandbox')}
                className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  activeTab === 'sandbox'
                    ? 'bg-neutral-800 text-white shadow-sm'
                    : 'text-neutral-400 hover:text-white hover:bg-neutral-900'
                }`}
              >
                <Terminal className="h-3.5 w-3.5 text-amber-400" />
                Tools & Math Console
              </button>

              <button
                onClick={() => setActiveTab('benchmarks')}
                className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  activeTab === 'benchmarks'
                    ? 'bg-neutral-800 text-white shadow-sm'
                    : 'text-neutral-400 hover:text-white hover:bg-neutral-900'
                }`}
              >
                <Award className="h-3.5 w-3.5 text-purple-400" />
                Benchmarks & Analytics
              </button>
            </div>

            <div className="text-[11px] font-mono text-neutral-500">
              Session ID: <span className="text-neutral-300">{currentSessionId}</span>
            </div>
          </div>

          {/* TAB 1: AGENT WORKBENCH */}
          {activeTab === 'workbench' && (
            <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
              {/* Left Column: Prompt Input & Controls */}
              <div className="w-full lg:w-2/5 border-r border-neutral-800 p-6 flex flex-col gap-4 overflow-y-auto">
                <div>
                  <h2 className="text-sm font-semibold text-white mb-1 flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-blue-400" />
                    Task Prompt
                  </h2>
                  <p className="text-xs text-neutral-400 mb-3">
                    Submit industrial workflows, equations, technical analysis, or report generation tasks.
                  </p>

                  <textarea
                    rows={6}
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder="e.g. Calculate the integral of x^3 * cos(x), check refinery safety limits for reactor R-101, and generate a Word inspection report."
                    className="w-full rounded-xl bg-neutral-900 border border-neutral-800 p-3 text-sm text-white placeholder-neutral-500 focus:border-neutral-600 focus:outline-none resize-none font-sans"
                  />
                </div>

                {/* Routing Mode Selector */}
                <div className="flex items-center justify-between bg-neutral-900/60 border border-neutral-800 rounded-lg p-3">
                  <div>
                    <label className="text-xs font-medium text-white block">Routing Mode</label>
                    <span className="text-[10px] text-neutral-400">3-Stage Waterfall Routing</span>
                  </div>
                  <select
                    value={roleOverride}
                    onChange={(e) => setRoleOverride(e.target.value)}
                    className="bg-neutral-950 border border-neutral-700 text-xs text-white rounded px-2.5 py-1 focus:outline-none"
                  >
                    <option value="auto">Auto (3-Stage Waterfall)</option>
                    <option value="reasoning">Force Reasoning (Qwen 2.5 3B)</option>
                    <option value="coding">Force Coding (Qwen Coder 3B)</option>
                  </select>
                </div>

                {/* Action Buttons */}
                <div className="flex items-center gap-3">
                  <button
                    onClick={handleExecuteAgent}
                    disabled={agentRunning || !prompt.trim()}
                    className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-blue-600 text-white font-medium py-2.5 px-4 text-xs hover:bg-blue-500 transition-colors disabled:opacity-50"
                  >
                    {agentRunning ? (
                      <>
                        <RotateCw className="h-3.5 w-3.5 animate-spin" />
                        Executing Task...
                      </>
                    ) : (
                      <>
                        <Play className="h-3.5 w-3.5 fill-current" />
                        Execute Workflow
                      </>
                    )}
                  </button>

                  <button
                    onClick={() => {
                      setPrompt('')
                      setAgentResponse(null)
                      setCitationsVerified(null)
                      setUngroundedCitations([])
                      setThinkingSteps([])
                      setLiveTools([])
                      setRouteDecision(null)
                      setCurrentSessionId('session_' + Math.random().toString(36).substring(2, 9))
                    }}
                    className="px-3 py-2.5 rounded-lg border border-neutral-800 text-xs text-neutral-400 hover:text-white hover:bg-neutral-900 transition-colors"
                  >
                    Reset
                  </button>
                </div>

                {/* Generated Artifacts Box */}
                {sessionArtifacts.length > 0 && (
                  <div className="mt-2 rounded-xl border border-neutral-800 bg-neutral-950 p-4">
                    <h3 className="text-xs font-semibold text-white mb-2 flex items-center gap-1.5">
                      <Download className="h-3.5 w-3.5 text-emerald-400" />
                      Generated Deliverables ({sessionArtifacts.length})
                    </h3>
                    <div className="space-y-2">
                      {sessionArtifacts.map((art, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between bg-neutral-900 border border-neutral-800 rounded-lg p-2.5 text-xs font-mono"
                        >
                          <div className="truncate pr-2">
                            <span className="text-white font-medium">{art.filename}</span>
                            <span className="text-neutral-500 block text-[10px]">
                              {Math.round(art.size_bytes / 1024)} KB &middot; {art.mime_type.split('/').pop()}
                            </span>
                          </div>
                          <a
                            href={art.download_url}
                            download={art.filename}
                            className="px-2.5 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-white text-[11px] flex items-center gap-1 transition-colors"
                          >
                            <Download className="h-3 w-3" />
                            Download
                          </a>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Right Column: Thought Trace, Tool Dispatches, and Output */}
              <div className="flex-1 p-6 overflow-y-auto flex flex-col gap-4">
                {/* Live Status Header */}
                <div className="flex items-center justify-between border-b border-neutral-800 pb-3">
                  <div className="flex items-center gap-2">
                    <div
                      className={`h-2.5 w-2.5 rounded-full ${
                        agentRunning ? 'bg-amber-400 animate-ping' : 'bg-emerald-400'
                      }`}
                    />
                    <span className="text-xs font-mono text-neutral-300">
                      {agentStatus || 'Workbench standby.'}
                    </span>
                  </div>

                  {routeDecision && (
                    <div className="flex items-center gap-2 text-xs font-mono">
                      <span className="px-2 py-0.5 rounded bg-blue-950 border border-blue-800 text-blue-300">
                        {routeDecision.role.toUpperCase()}
                      </span>
                      <span className="text-neutral-500">
                        ({Math.round(routeDecision.confidence * 100)}% via {routeDecision.method})
                      </span>
                    </div>
                  )}
                </div>

                {/* Thinking Trace Accordion */}
                {thinkingSteps.length > 0 && (
                  <div className="rounded-xl border border-neutral-800 bg-neutral-950 overflow-hidden">
                    <button
                      onClick={() => setShowThinking(!showThinking)}
                      className="w-full px-4 py-2.5 bg-neutral-900/60 flex items-center justify-between text-xs font-semibold text-neutral-300 hover:bg-neutral-900 transition-colors"
                    >
                      <span className="flex items-center gap-2">
                        <Sparkles className="h-3.5 w-3.5 text-amber-400" />
                        Model Chain-of-Thought ({thinkingSteps.length} reasoning steps)
                      </span>
                      {showThinking ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    </button>
                    {showThinking && (
                      <div className="p-4 space-y-2 text-xs font-mono text-neutral-400 bg-black/40 border-t border-neutral-800 max-h-60 overflow-y-auto">
                        {thinkingSteps.map((step, idx) => (
                          <div key={idx} className="whitespace-pre-wrap leading-relaxed">
                            {step}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Tool Invocations Cards */}
                {liveTools.length > 0 && (
                  <div className="space-y-2">
                    <h3 className="text-xs font-semibold text-neutral-400 flex items-center gap-1.5 uppercase font-mono">
                      <Terminal className="h-3.5 w-3.5 text-blue-400" />
                      Executed Tools ({liveTools.length})
                    </h3>
                    <div className="grid grid-cols-1 gap-2">
                      {liveTools.map((t, idx) => (
                        <div
                          key={idx}
                          className="rounded-lg border border-neutral-800 bg-neutral-950 p-3 text-xs font-mono"
                        >
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="font-semibold text-blue-400 flex items-center gap-1.5">
                              {t.status === 'success' ? (
                                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                              ) : (
                                <XCircle className="h-3.5 w-3.5 text-red-400" />
                              )}
                              {t.tool_name}
                            </span>
                            <span className="text-[10px] text-neutral-500 uppercase">{t.status}</span>
                          </div>
                          <div className="bg-neutral-900 p-2 rounded text-neutral-300 text-[11px] whitespace-pre-wrap max-h-32 overflow-y-auto">
                            {t.output || t.error || JSON.stringify(t.data, null, 2)}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Final Agent Response */}
                {agentResponse && (
                  <div className="rounded-xl border border-neutral-800 bg-neutral-950 p-5 flex flex-col gap-3">
                    <div className="flex items-center justify-between border-b border-neutral-800 pb-2">
                      <h3 className="text-xs font-semibold text-white flex items-center gap-2">
                        <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                        Synthesized Response
                      </h3>
                      <div className="flex items-center gap-2">
                        {citationsVerified === true && (
                          <span className="text-[10px] bg-emerald-950/80 text-emerald-400 border border-emerald-800/80 px-2 py-0.5 rounded font-mono">
                            ✓ Grounded Citations
                          </span>
                        )}
                        {citationsVerified === false && (
                          <span className="text-[10px] bg-amber-950/80 text-amber-400 border border-amber-800/80 px-2 py-0.5 rounded font-mono">
                            ⚠ Citations Flagged ({ungroundedCitations.length})
                          </span>
                        )}
                        <span className="text-[10px] text-neutral-500 font-mono">Complete</span>
                      </div>
                    </div>
                    <div className="text-sm text-neutral-200 leading-relaxed whitespace-pre-wrap font-sans">
                      {agentResponse}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 2: KNOWLEDGE BASE & CHUNK INSPECTOR */}
          {activeTab === 'knowledge' && (
            <KnowledgeHub currentUser={currentUser} />
          )}

          {/* TAB 3: TOOLS & MATH CONSOLE */}
          {activeTab === 'sandbox' && (
            <div className="flex-1 p-6 overflow-y-auto flex flex-col lg:flex-row gap-6">
              {/* Symbolic Math Evaluator */}
              <div className="w-full lg:w-1/2 rounded-xl border border-neutral-800 bg-neutral-950 p-5 flex flex-col gap-4">
                <div>
                  <h2 className="text-sm font-semibold text-white mb-1 flex items-center gap-2">
                    <Cpu className="h-4 w-4 text-amber-400" />
                    SymPy Safe Symbolic Mathematics
                  </h2>
                  <p className="text-xs text-neutral-400 mb-3">
                    Evaluates exact algebraic equations, differentiation, integration, and limits without eval().
                  </p>
                </div>

                <div className="space-y-3">
                  <div>
                    <label className="text-xs font-medium text-neutral-400 block mb-1">Mathematical Expression</label>
                    <input
                      type="text"
                      value={mathExpr}
                      onChange={(e) => setMathExpr(e.target.value)}
                      className="w-full rounded-lg bg-neutral-900 border border-neutral-800 p-2 text-xs text-white font-mono focus:outline-none"
                    />
                  </div>

                  <div className="flex gap-2">
                    {['evaluate', 'differentiate', 'integrate', 'solve', 'simplify'].map((op) => (
                      <button
                        key={op}
                        type="button"
                        onClick={() => setMathOperation(op)}
                        className={`px-3 py-1.5 rounded text-xs font-mono transition-colors ${
                          mathOperation === op
                            ? 'bg-amber-600 text-white'
                            : 'bg-neutral-900 text-neutral-400 hover:text-white'
                        }`}
                      >
                        {op}
                      </button>
                    ))}
                  </div>

                  <button
                    onClick={handleRunMath}
                    className="w-full rounded-lg bg-white text-black font-semibold py-2 px-4 text-xs hover:bg-neutral-200 transition-colors"
                  >
                    Evaluate Symbolically
                  </button>
                </div>

                {mathOutput && (
                  <div className="mt-2 rounded-lg bg-neutral-900 border border-neutral-800 p-3 font-mono text-xs text-emerald-400 whitespace-pre-wrap">
                    {mathOutput}
                  </div>
                )}
              </div>

              {/* Air-Gapped Code Sandbox Security Specification */}
              <div className="w-full lg:w-1/2 rounded-xl border border-neutral-800 bg-neutral-950 p-5 flex flex-col gap-3">
                <h2 className="text-sm font-semibold text-white mb-1 flex items-center gap-2">
                  <Terminal className="h-4 w-4 text-blue-400" />
                  Air-Gapped Docker Sandbox Policy
                </h2>
                <div className="space-y-2 text-xs text-neutral-300 font-mono">
                  <div className="p-2.5 rounded bg-neutral-900 border border-neutral-800">
                    <span className="text-blue-400 font-bold block mb-1">Fail-Closed Guarantee</span>
                    If Docker is down or unresponsive, untrusted execution is refused. No subprocess fallback.
                  </div>
                  <div className="p-2.5 rounded bg-neutral-900 border border-neutral-800">
                    <span className="text-blue-400 font-bold block mb-1">Network Isolation</span>
                    network_mode: &quot;none&quot; &middot; Outbound egress blocked at kernel namespace.
                  </div>
                  <div className="p-2.5 rounded bg-neutral-900 border border-neutral-800">
                    <span className="text-blue-400 font-bold block mb-1">Resource Constraints</span>
                    512 MB RAM limit &middot; 50 PIDs limit &middot; Dropped capabilities (ALL).
                  </div>
                  <div className="p-2.5 rounded bg-neutral-900 border border-neutral-800">
                    <span className="text-blue-400 font-bold block mb-1">Path Boundary Isolation</span>
                    Operations strictly validated inside &lt;workspace&gt;/&lt;session_id&gt;/. Traversal blocked.
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: BENCHMARK & EVALUATION DASHBOARD */}
          {activeTab === 'benchmarks' && <BenchmarkDashboard currentUser={currentUser} />}
        </div>
      )}
    </div>
  )
}
export default App
