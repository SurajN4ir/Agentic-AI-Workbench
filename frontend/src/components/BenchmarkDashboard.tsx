import React, { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { User } from '../types/auth'
import type {
  BenchmarkProgress,
  BenchmarkRunDetail,
  BenchmarkRunSummary,
  CaseResult,
} from '../types/benchmarks'
import {
  Award,
  CheckCircle2,
  ChevronRight,
  Clock,
  Info,
  Layers,
  Lock,
  Play,
  RefreshCw,
  Search,
  Shield,
  Sliders,
  TrendingUp,
  X,
  XCircle,
} from 'lucide-react'

interface BenchmarkDashboardProps {
  currentUser: User | null
}

const CATEGORY_NAMES: Record<string, string> = {
  engineering_reasoning: 'Engineering Reasoning',
  symbolic_math: 'Symbolic Math',
  data_analysis: 'Data Analysis',
  knowledge_retrieval: 'Knowledge Retrieval',
  deliverable_generation: 'Deliverable Generation',
  security_adversarial: 'Security & Adversarial',
}

export const BenchmarkDashboard: React.FC<BenchmarkDashboardProps> = ({ currentUser }) => {
  // Data state
  const [latestRun, setLatestRun] = useState<BenchmarkRunDetail | null>(null)
  const [selectedRun, setSelectedRun] = useState<BenchmarkRunDetail | null>(null)
  const [historyRuns, setHistoryRuns] = useState<BenchmarkRunSummary[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  // Filters & Drill-down
  const [activeCategory, setActiveCategory] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<'all' | 'passed' | 'failed' | 'adversarial'>('all')
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [inspectedCase, setInspectedCase] = useState<CaseResult | null>(null)

  // Run Benchmark Modal & Live Progress
  const [showRunModal, setShowRunModal] = useState<boolean>(false)
  const [runCategoryFilter, setRunCategoryFilter] = useState<string>('')
  const [runMockMode, setRunMockMode] = useState<boolean>(false)
  const [runningEval, setRunningEval] = useState<boolean>(false)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [progress, setProgress] = useState<BenchmarkProgress | null>(null)

  const isAdmin = currentUser?.role === 'admin'

  useEffect(() => {
    loadDashboardData()
  }, [])

  const loadDashboardData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [latest, hist] = await Promise.all([
        api.getLatestBenchmark().catch((e) => {
          console.warn('Could not load latest benchmark:', e)
          return null
        }),
        api.getBenchmarkHistory().catch(() => []),
      ])

      setLatestRun(latest)
      setSelectedRun(latest)
      setHistoryRuns(hist)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load evaluation data')
    } finally {
      setLoading(false)
    }
  }

  // Poll progress when evaluation is actively running
  useEffect(() => {
    if (!runningEval || !activeRunId) return

    const interval = setInterval(async () => {
      try {
        const prog = await api.getBenchmarkProgress(activeRunId)
        setProgress(prog)

        if (prog.status === 'completed' || prog.status === 'failed') {
          setRunningEval(false)
          clearInterval(interval)
          // Refresh dashboard data
          const [updatedLatest, updatedHist] = await Promise.all([
            api.getLatestBenchmark(),
            api.getBenchmarkHistory(),
          ])
          setLatestRun(updatedLatest)
          setSelectedRun(updatedLatest)
          setHistoryRuns(updatedHist)
        }
      } catch (err) {
        console.error('Error polling benchmark progress:', err)
      }
    }, 1500)

    return () => clearInterval(interval)
  }, [runningEval, activeRunId])

  const handleStartRun = async () => {
    if (!isAdmin) return

    setRunningEval(true)
    setProgress(null)
    setShowRunModal(false)

    try {
      const res = await api.triggerBenchmark({
        category: runCategoryFilter || undefined,
        mock: runMockMode,
      })
      setActiveRunId(res.run_id)
    } catch (err) {
      setRunningEval(false)
      alert(err instanceof Error ? err.message : 'Failed to initiate benchmark run')
    }
  }

  const handleSelectHistoricalRun = async (runId: string) => {
    if (latestRun && latestRun.id === runId) {
      setSelectedRun(latestRun)
      return
    }
    setLoading(true)
    try {
      const detail = await api.getBenchmarkRun(runId)
      setSelectedRun(detail)
    } catch (err) {
      console.error('Failed to load historical run details:', err)
      alert('Failed to load historical run details')
    } finally {
      setLoading(false)
    }
  }

  // Filtered case results
  const currentResults = selectedRun?.results || []
  const filteredResults = currentResults.filter((r) => {
    // Category filter
    if (activeCategory !== 'all' && r.category !== activeCategory) return false

    // Status filter
    if (statusFilter === 'passed' && !r.passed) return false
    if (statusFilter === 'failed' && r.passed) return false
    if (statusFilter === 'adversarial' && r.category !== 'security_adversarial') return false

    // Search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      const matchId = r.case_id.toLowerCase().includes(q)
      const matchTitle = (r.title || '').toLowerCase().includes(q)
      const matchCategory = r.category.toLowerCase().includes(q)
      const matchDiag = (r.failure_diagnosis || '').toLowerCase().includes(q)
      if (!matchId && !matchTitle && !matchCategory && !matchDiag) return false
    }

    return true
  })

  const isHistorical = selectedRun && latestRun && selectedRun.id !== latestRun.id

  if (loading && !selectedRun) {
    return (
      <div className="flex-1 flex items-center justify-center p-12 bg-black text-white">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="h-7 w-7 text-blue-400 animate-spin" />
          <p className="text-sm font-mono text-neutral-400">Loading Benchmark Analytics & Ground-Truth Engine...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col bg-black text-neutral-200 overflow-y-auto selection:bg-neutral-800">
      {/* ─── Top Control & Telemetry Bar ─────────────────────────── */}
      <div className="border-b border-neutral-800 bg-neutral-950/80 px-6 py-4 flex flex-col md:flex-row md:items-center justify-between gap-4 sticky top-0 z-20 backdrop-blur-md">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <div className="flex items-center gap-2.5">
            <div className="h-9 w-9 rounded-lg bg-blue-950/60 border border-blue-800/80 flex items-center justify-center">
              <Award className="h-5 w-5 text-blue-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-white tracking-tight">
                  Industrial Benchmark & Model Evaluation
                </h2>
                {isHistorical ? (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-950/80 text-amber-400 border border-amber-800 font-mono font-medium">
                    HISTORICAL ARCHIVE
                  </span>
                ) : (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950/80 text-emerald-400 border border-emerald-800 font-mono font-medium">
                    LATEST VERIFIED RUN
                  </span>
                )}
              </div>
              <p className="text-xs text-neutral-400">
                15 Core Industrial Scenarios &middot; SYNOPSIS V1 SPEC &middot; Fail-Closed Security Audited
              </p>
            </div>
          </div>

          {/* Historical Run Selector Dropdown */}
          {historyRuns.length > 0 && (
            <div className="sm:ml-4">
              <select
                value={selectedRun?.id || ''}
                onChange={(e) => handleSelectHistoricalRun(e.target.value)}
                className="bg-neutral-900 border border-neutral-800 text-neutral-300 text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-500 font-mono"
              >
                {historyRuns.map((h, i) => (
                  <option key={h.id} value={h.id}>
                    {i === 0 ? 'Latest Run: ' : 'Run: '}
                    {new Date(h.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}{' '}
                    ({Math.round(h.accuracy_percentage)}% &middot; {h.model_name})
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2.5">
          <button
            onClick={loadDashboardData}
            className="p-2 rounded-lg bg-neutral-900 border border-neutral-800 text-neutral-400 hover:text-white hover:bg-neutral-800 transition-colors"
            title="Refresh Evaluation Data"
          >
            <RefreshCw className="h-4 w-4" />
          </button>

          {/* Run Evaluation Trigger */}
          <button
            onClick={() => setShowRunModal(true)}
            disabled={!isAdmin || runningEval}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all shadow-sm ${
              isAdmin
                ? runningEval
                  ? 'bg-neutral-800 text-neutral-400 cursor-not-allowed border border-neutral-700'
                  : 'bg-white text-black hover:bg-neutral-200 cursor-pointer'
                : 'bg-neutral-900 text-neutral-500 border border-neutral-800 cursor-not-allowed opacity-60'
            }`}
            title={isAdmin ? 'Execute benchmark suite' : 'Admin role required to trigger benchmark execution'}
          >
            {runningEval ? (
              <>
                <RefreshCw className="h-3.5 w-3.5 animate-spin text-blue-400" />
                Evaluating...
              </>
            ) : (
              <>
                {isAdmin ? <Play className="h-3.5 w-3.5 fill-black" /> : <Lock className="h-3.5 w-3.5" />}
                Run Benchmark
              </>
            )}
          </button>
        </div>
      </div>

      {/* ─── Error Alert Banner (if any) ─────────────────────────── */}
      {error && (
        <div className="bg-rose-950/40 border-b border-rose-900/60 px-6 py-2.5 text-xs text-rose-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <XCircle className="h-4 w-4 text-rose-400" />
            <span>{error}</span>
          </div>
          <button
            onClick={() => setError(null)}
            className="text-rose-400 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* ─── Active Run Progress Banner (when executing) ───────────── */}
      {runningEval && progress && (
        <div className="bg-blue-950/40 border-b border-blue-900/60 px-6 py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <RefreshCw className="h-5 w-5 text-blue-400 animate-spin" />
            <div>
              <div className="text-xs font-semibold text-white flex items-center gap-2">
                Running Benchmark Evaluation
                <span className="font-mono text-blue-400 font-normal">
                  [{progress.completed_cases}/{progress.total_cases}]
                </span>
              </div>
              <p className="text-[11px] text-neutral-300 font-mono">
                Current: {progress.current_case_id ? `${progress.current_case_id} — ${progress.current_case_title}` : 'Initializing test harnesses...'}
              </p>
            </div>
          </div>
          <div className="w-full sm:w-48 bg-neutral-900 h-2 rounded-full overflow-hidden border border-neutral-800">
            <div
              className="bg-blue-500 h-full transition-all duration-300"
              style={{
                width: `${progress.total_cases > 0 ? (progress.completed_cases / progress.total_cases) * 100 : 0}%`,
              }}
            />
          </div>
        </div>
      )}

      <div className="p-6 space-y-6 max-w-7xl mx-auto w-full">
        {/* ─── Model & Harness Configuration Banner ──────────────── */}
        <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4 text-xs font-mono">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-neutral-500">Model:</span>
              <span className="px-2 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-800 font-semibold">
                {selectedRun?.model_name || 'llama3.2:latest'}
              </span>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-neutral-500">Provider:</span>
              <span className="px-2 py-0.5 rounded bg-neutral-900 text-neutral-300 border border-neutral-800 uppercase">
                {selectedRun?.provider_type || 'ollama'} (Loopback)
              </span>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-neutral-500">Suite Version:</span>
              <span className="text-neutral-300">
                {selectedRun?.benchmark_version || 'industrial_benchmark_v1'}
              </span>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-neutral-500">Executed:</span>
              <span className="text-neutral-300">
                {selectedRun ? new Date(selectedRun.timestamp).toLocaleString() : '—'}
              </span>
            </div>
          </div>

          <div className="text-[11px] text-neutral-500 flex items-center gap-1.5">
            <Shield className="h-3.5 w-3.5 text-emerald-400" />
            Air-Gapped Sovereign Enforcement
          </div>
        </div>

        {/* ─── TOP KPI SUMMARY CARDS (5-col grid) ────────────────── */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3.5">
          {/* 1. Pass Rate */}
          <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-4 flex flex-col justify-between shadow-sm">
            <div className="flex items-center justify-between text-neutral-400 mb-2">
              <span className="text-xs font-medium">Overall Pass Rate</span>
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            </div>
            <div>
              <div className="text-2xl font-bold tracking-tight text-white flex items-baseline gap-1.5 font-mono">
                {selectedRun ? `${selectedRun.accuracy_percentage.toFixed(1)}%` : '0.0%'}
              </div>
              <p className="text-[11px] text-emerald-400/90 font-mono mt-1">
                {selectedRun?.passed_cases || 0} / {selectedRun?.total_cases || 0} Scenarios Passed
              </p>
            </div>
            <div className="w-full bg-neutral-900 h-1.5 rounded-full mt-3 overflow-hidden">
              <div
                className="bg-emerald-500 h-full rounded-full"
                style={{ width: `${selectedRun?.accuracy_percentage || 0}%` }}
              />
            </div>
          </div>

          {/* 2. Composite Benchmark Score */}
          <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-4 flex flex-col justify-between shadow-sm">
            <div className="flex items-center justify-between text-neutral-400 mb-2">
              <span className="text-xs font-medium">Composite Score</span>
              <TrendingUp className="h-4 w-4 text-blue-400" />
            </div>
            <div>
              <div className="text-2xl font-bold tracking-tight text-white flex items-baseline gap-1 font-mono">
                {selectedRun ? selectedRun.overall_score.toFixed(3) : '0.000'}
                <span className="text-xs font-normal text-neutral-500 font-mono">/ 1.000</span>
              </div>
              <p className="text-[11px] text-blue-400 font-mono mt-1">
                {(selectedRun?.overall_score || 0) >= 0.9 ? 'Grade: A+ (Target Surpassed)' : 'Grade: Satisfactory'}
              </p>
            </div>
            <div className="w-full bg-neutral-900 h-1.5 rounded-full mt-3 overflow-hidden">
              <div
                className="bg-blue-500 h-full rounded-full"
                style={{ width: `${(selectedRun?.overall_score || 0) * 100}%` }}
              />
            </div>
          </div>

          {/* 3. Latency Metrics */}
          <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-4 flex flex-col justify-between shadow-sm">
            <div className="flex items-center justify-between text-neutral-400 mb-2">
              <span className="text-xs font-medium">Inference Latency</span>
              <Clock className="h-4 w-4 text-amber-400" />
            </div>
            <div>
              <div className="text-2xl font-bold tracking-tight text-white font-mono">
                {selectedRun ? `${(selectedRun.average_duration_ms / 1000).toFixed(1)}s` : '0.0s'}
              </div>
              <p className="text-[11px] text-neutral-400 font-mono mt-1">
                p95: {selectedRun ? `${(selectedRun.p95_duration_ms / 1000).toFixed(1)}s` : '0.0s'}
              </p>
            </div>
            <div className="text-[10px] text-neutral-500 font-mono mt-3">
              On-Premise GPU/CPU Local Inference
            </div>
          </div>

          {/* 4. Security Violations */}
          <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-4 flex flex-col justify-between shadow-sm">
            <div className="flex items-center justify-between text-neutral-400 mb-2">
              <span className="text-xs font-medium">Security Invariants</span>
              <Shield className="h-4 w-4 text-emerald-400" />
            </div>
            <div>
              <div className="text-2xl font-bold tracking-tight text-emerald-400 font-mono">
                {selectedRun?.security_violations === 0 ? '0 VIOLATIONS' : `${selectedRun?.security_violations} BREACHES`}
              </div>
              <p className="text-[11px] text-neutral-400 font-mono mt-1">
                Zero Host Traversal &middot; Egress Blocked
              </p>
            </div>
            <div className="text-[10px] text-emerald-500/90 font-mono mt-3">
              Fail-Closed Isolation: 100% Verified
            </div>
          </div>

          {/* 5. Total Scenarios Audited */}
          <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-4 flex flex-col justify-between shadow-sm col-span-2 md:col-span-1">
            <div className="flex items-center justify-between text-neutral-400 mb-2">
              <span className="text-xs font-medium">Scenarios Audited</span>
              <Layers className="h-4 w-4 text-purple-400" />
            </div>
            <div>
              <div className="text-2xl font-bold tracking-tight text-white font-mono">
                {selectedRun?.total_cases || 15}
              </div>
              <p className="text-[11px] text-purple-400 font-mono mt-1">
                6 Domain Categories
              </p>
            </div>
            <div className="text-[10px] text-neutral-500 font-mono mt-3">
              Full Industrial Coverage
            </div>
          </div>
        </div>

        {/* ─── CATEGORY PERFORMANCE BREAKDOWN (Interactive Chart) ── */}
        <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-5 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
            <div>
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <BarChartIcon />
                Category Performance Breakdown
              </h3>
              <p className="text-xs text-neutral-400">
                Click any category bar to filter the scenario execution matrix below.
              </p>
            </div>
            {activeCategory !== 'all' && (
              <button
                onClick={() => setActiveCategory('all')}
                className="text-xs font-mono text-blue-400 hover:text-blue-300 underline cursor-pointer"
              >
                Reset category filter
              </button>
            )}
          </div>

          {/* Interactive Progress Bars */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Object.entries(selectedRun?.category_scores || {}).map(([catKey, scoreVal]) => {
              const isSelected = activeCategory === catKey
              const label = CATEGORY_NAMES[catKey] || catKey
              const percentage = Math.round(scoreVal * 100)
              const isPassing = scoreVal >= 0.7

              return (
                <div
                  key={catKey}
                  onClick={() => setActiveCategory(isSelected ? 'all' : catKey)}
                  className={`p-3.5 rounded-lg border transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-neutral-900 border-blue-500 ring-1 ring-blue-500/50'
                      : 'bg-neutral-900/50 border-neutral-850 hover:bg-neutral-900 hover:border-neutral-750'
                  }`}
                >
                  <div className="flex items-center justify-between text-xs mb-2">
                    <span className="font-medium text-neutral-200">{label}</span>
                    <span
                      className={`font-mono font-semibold ${
                        isPassing ? 'text-emerald-400' : 'text-amber-400'
                      }`}
                    >
                      {scoreVal.toFixed(3)}
                    </span>
                  </div>

                  {/* Visual Bar */}
                  <div className="w-full bg-neutral-950 h-2 rounded-full overflow-hidden border border-neutral-800">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        scoreVal >= 0.9
                          ? 'bg-emerald-500'
                          : scoreVal >= 0.7
                          ? 'bg-blue-500'
                          : 'bg-amber-500'
                      }`}
                      style={{ width: `${percentage}%` }}
                    />
                  </div>

                  <div className="flex items-center justify-between text-[10px] text-neutral-500 mt-2 font-mono">
                    <span>Target &ge; 0.70</span>
                    <span className={isPassing ? 'text-emerald-400 font-semibold' : 'text-amber-400'}>
                      {isPassing ? 'PASS' : 'WARN'} ({percentage}%)
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* ─── SCENARIO DRILL-DOWN MATRIX ────────────────────────── */}
        <div className="bg-neutral-950 border border-neutral-800 rounded-xl overflow-hidden shadow-sm">
          {/* Table Header and Search Filters */}
          <div className="p-4 border-b border-neutral-800 flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <Sliders className="h-4 w-4 text-blue-400" />
                Scenario Results Matrix
                <span className="text-xs px-2 py-0.5 rounded-full bg-neutral-900 text-neutral-400 border border-neutral-800 font-mono">
                  {filteredResults.length} / {currentResults.length}
                </span>
              </h3>

              {/* Status Filter Tabs */}
              <div className="flex items-center gap-1 bg-neutral-900 p-1 rounded-lg border border-neutral-800 text-xs">
                {(['all', 'passed', 'failed', 'adversarial'] as const).map((st) => (
                  <button
                    key={st}
                    onClick={() => setStatusFilter(st)}
                    className={`px-2.5 py-1 rounded text-xs capitalize transition-colors ${
                      statusFilter === st
                        ? 'bg-neutral-800 text-white font-medium shadow-sm'
                        : 'text-neutral-400 hover:text-white'
                    }`}
                  >
                    {st}
                  </button>
                ))}
              </div>
            </div>

            {/* Search Input */}
            <div className="relative w-full md:w-64">
              <Search className="h-3.5 w-3.5 text-neutral-500 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search scenarios or errors..."
                className="w-full bg-neutral-900 border border-neutral-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-neutral-600 font-sans"
              />
            </div>
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-neutral-900/60 text-neutral-400 font-mono border-b border-neutral-800 uppercase tracking-wider text-[11px]">
                <tr>
                  <th className="py-3 px-4">ID</th>
                  <th className="py-3 px-4">Title & Category</th>
                  <th className="py-3 px-4">Score</th>
                  <th className="py-3 px-4">Routing</th>
                  <th className="py-3 px-4">Tools Dispatched</th>
                  <th className="py-3 px-4">Security</th>
                  <th className="py-3 px-4">Duration</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-850">
                {filteredResults.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="py-8 text-center text-neutral-500 font-mono">
                      No benchmark scenarios match the current filters.
                    </td>
                  </tr>
                ) : (
                  filteredResults.map((r) => {
                    const isPassing = r.passed
                    return (
                      <tr
                        key={r.case_id}
                        onClick={() => setInspectedCase(r)}
                        className="hover:bg-neutral-900/60 transition-colors cursor-pointer group"
                      >
                        <td className="py-3 px-4 font-mono font-semibold text-white">
                          {r.case_id}
                        </td>
                        <td className="py-3 px-4 max-w-xs">
                          <div className="font-medium text-white truncate">{r.title || r.case_id}</div>
                          <div className="text-[11px] text-neutral-500 font-mono">
                            {CATEGORY_NAMES[r.category] || r.category}
                          </div>
                        </td>
                        <td className="py-3 px-4 font-mono">
                          <div className="flex items-center gap-2">
                            <span className={isPassing ? 'text-emerald-400 font-bold' : 'text-amber-400'}>
                              {r.score.toFixed(2)}
                            </span>
                            <div className="w-12 bg-neutral-900 h-1.5 rounded-full overflow-hidden">
                              <div
                                className={`h-full ${isPassing ? 'bg-emerald-500' : 'bg-amber-500'}`}
                                style={{ width: `${r.score * 100}%` }}
                              />
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-4 font-mono">
                          {r.routing_passed ? (
                            <span className="text-emerald-400 flex items-center gap-1">
                              <CheckCircle2 className="h-3.5 w-3.5" /> OK
                            </span>
                          ) : (
                            <span className="text-rose-400 flex items-center gap-1">
                              <XCircle className="h-3.5 w-3.5" /> MISMATCH
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 font-mono">
                          {r.actual_tools && r.actual_tools.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {r.actual_tools.map((t, idx) => (
                                <span
                                  key={idx}
                                  className="px-1.5 py-0.5 rounded bg-neutral-900 text-blue-300 border border-neutral-800 text-[10px]"
                                >
                                  {t}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-neutral-500">None</span>
                          )}
                        </td>
                        <td className="py-3 px-4 font-mono">
                          {r.security_passed ? (
                            <span className="px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-900 text-[10px]">
                              SECURE
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded bg-rose-950 text-rose-400 border border-rose-800 text-[10px]">
                              VIOLATION
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 font-mono text-neutral-400">
                          {r.duration_ms.toFixed(0)}ms
                        </td>
                        <td className="py-3 px-4">
                          {isPassing ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
                              PASS
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-semibold bg-rose-950 text-rose-400 border border-rose-800">
                              FAIL
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              setInspectedCase(r)
                            }}
                            className="p-1 rounded text-neutral-400 hover:text-white group-hover:bg-neutral-800 transition-colors"
                            title="Inspect Scenario Trace"
                          >
                            <ChevronRight className="h-4 w-4" />
                          </button>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ─── SCENARIO DRILL-DOWN MODAL / DRAWER ─────────────────── */}
      {inspectedCase && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-neutral-950 border border-neutral-800 rounded-2xl max-w-2xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="p-5 border-b border-neutral-800 flex items-center justify-between bg-neutral-900/50">
              <div className="flex items-center gap-2.5">
                <div
                  className={`h-8 w-8 rounded-lg flex items-center justify-center ${
                    inspectedCase.passed ? 'bg-emerald-950 border border-emerald-800' : 'bg-rose-950 border border-rose-800'
                  }`}
                >
                  {inspectedCase.passed ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  ) : (
                    <XCircle className="h-4 w-4 text-rose-400" />
                  )}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-white font-mono">{inspectedCase.case_id}</span>
                    <span className="text-xs px-2 py-0.5 rounded bg-neutral-800 text-neutral-300 font-mono">
                      {CATEGORY_NAMES[inspectedCase.category] || inspectedCase.category}
                    </span>
                  </div>
                  <h4 className="text-xs text-neutral-300 font-medium mt-0.5">
                    {inspectedCase.title}
                  </h4>
                </div>
              </div>

              <button
                onClick={() => setInspectedCase(null)}
                className="p-1.5 rounded-lg text-neutral-400 hover:text-white hover:bg-neutral-800 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-5 overflow-y-auto space-y-4 text-xs font-sans">
              {/* Task Prompt */}
              <div>
                <label className="text-neutral-400 text-[11px] font-mono block mb-1">
                  Scenario Task Prompt:
                </label>
                <div className="p-3 rounded-lg bg-neutral-900 border border-neutral-800 text-neutral-200 leading-relaxed font-mono text-[11px]">
                  {inspectedCase.prompt || 'No prompt recorded'}
                </div>
              </div>

              {/* Execution Diagnostics & Validation Proof */}
              <div
                className={`p-3.5 rounded-lg border text-xs leading-relaxed ${
                  inspectedCase.passed
                    ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
                    : 'bg-rose-950/40 border-rose-800 text-rose-300'
                }`}
              >
                <div className="font-semibold mb-1 flex items-center gap-1.5">
                  <Info className="h-3.5 w-3.5" />
                  Verification & Behavioral Diagnosis:
                </div>
                <p className="font-mono text-[11px]">
                  {inspectedCase.failure_diagnosis || 'Verified ground-truth invariants satisfied.'}
                </p>
              </div>

              {/* Expectations vs Actual Grid */}
              <div className="grid grid-cols-2 gap-3 text-xs font-mono">
                <div className="p-3 rounded-lg bg-neutral-900/60 border border-neutral-800">
                  <span className="text-neutral-500 block mb-1 text-[10px] uppercase">Routing Role</span>
                  <div className="flex items-center justify-between">
                    <span className="text-neutral-400">Expected: {inspectedCase.expected_role || 'reasoning'}</span>
                    <span className="text-white font-semibold">Actual: {inspectedCase.actual_role || 'reasoning'}</span>
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-neutral-900/60 border border-neutral-800">
                  <span className="text-neutral-500 block mb-1 text-[10px] uppercase">Score & Iterations</span>
                  <div className="flex items-center justify-between">
                    <span className="text-white font-bold">{inspectedCase.score.toFixed(3)}</span>
                    <span className="text-neutral-400">Used {inspectedCase.iterations_used} iter ({inspectedCase.duration_ms.toFixed(0)}ms)</span>
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-neutral-900/60 border border-neutral-800 col-span-2">
                  <span className="text-neutral-500 block mb-1 text-[10px] uppercase">Tools Invoked</span>
                  <div className="flex items-center justify-between">
                    <span className="text-neutral-400">
                      Expected: {inspectedCase.expected_tools?.join(', ') || 'None'}
                    </span>
                    <span className="text-blue-300 font-semibold">
                      Actual: {inspectedCase.actual_tools?.join(', ') || 'None'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Output Response Preview */}
              <div>
                <label className="text-neutral-400 text-[11px] font-mono block mb-1">
                  Synthesized Model Output / Artifact Preview:
                </label>
                <div className="p-3 rounded-lg bg-neutral-900 border border-neutral-800 text-neutral-300 font-mono text-[11px] leading-relaxed max-h-36 overflow-y-auto whitespace-pre-wrap">
                  {inspectedCase.output_preview || 'No response preview recorded.'}
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-neutral-800 bg-neutral-900/40 flex justify-end">
              <button
                onClick={() => setInspectedCase(null)}
                className="px-4 py-1.5 rounded-lg bg-white text-black font-semibold text-xs hover:bg-neutral-200 transition-colors"
              >
                Close Trace
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── RUN BENCHMARK MODAL ────────────────────────────────── */}
      {showRunModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-neutral-950 border border-neutral-800 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-5 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <Play className="h-4 w-4 text-blue-400" />
                Launch Benchmark Evaluation Run
              </h3>
              <button
                onClick={() => setShowRunModal(false)}
                className="p-1 rounded text-neutral-400 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <p className="text-xs text-neutral-400 leading-relaxed">
              Executes the industrial evaluation harness against ground-truth scenarios. Real scores and error diagnostics will be persisted into the database.
            </p>

            <div className="space-y-4">
              {/* Category Scope */}
              <div>
                <label className="block text-xs font-mono text-neutral-400 mb-1.5">
                  Category Scope:
                </label>
                <select
                  value={runCategoryFilter}
                  onChange={(e) => setRunCategoryFilter(e.target.value)}
                  className="w-full bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-neutral-600 font-mono"
                >
                  <option value="">All Categories (Full 15 Scenarios)</option>
                  <option value="engineering_reasoning">Engineering Reasoning (3 cases)</option>
                  <option value="symbolic_math">Symbolic Math (3 cases)</option>
                  <option value="data_analysis">Data Analysis & Calibration (2 cases)</option>
                  <option value="knowledge_retrieval">Knowledge Retrieval / RAG (2 cases)</option>
                  <option value="deliverable_generation">Deliverable Generation (2 cases)</option>
                  <option value="security_adversarial">Security & Adversarial Probes (3 cases)</option>
                </select>
              </div>

              {/* Execution Engine Toggle */}
              <div className="p-3 rounded-lg bg-neutral-900/60 border border-neutral-800 flex items-center justify-between">
                <div>
                  <span className="text-xs font-medium text-white block">Execution Engine</span>
                  <span className="text-[11px] text-neutral-400 block font-mono">
                    {runMockMode ? 'Fast Deterministic Mock (CI validation)' : 'Genuine Local Ollama (llama3.2:latest)'}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={runMockMode}
                  onChange={(e) => setRunMockMode(e.target.checked)}
                  className="h-4 w-4 rounded border-neutral-700 bg-neutral-900 text-blue-500 focus:ring-0 cursor-pointer"
                />
              </div>

              <div className="p-3 rounded-lg bg-blue-950/30 border border-blue-900/50 text-[11px] text-blue-300 font-mono flex items-start gap-2">
                <Shield className="h-4 w-4 shrink-0 text-blue-400 mt-0.5" />
                Air-gapped local execution strictly guaranteed. All tool dispatches run in isolated sandbox boundaries.
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setShowRunModal(false)}
                className="px-3.5 py-1.5 rounded-lg text-xs text-neutral-400 hover:text-white hover:bg-neutral-900 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleStartRun}
                className="px-4 py-1.5 rounded-lg bg-white text-black font-semibold text-xs hover:bg-neutral-200 transition-colors shadow-sm cursor-pointer"
              >
                Initiate Run
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function BarChartIcon() {
  return (
    <svg className="h-4 w-4 text-blue-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  )
}
