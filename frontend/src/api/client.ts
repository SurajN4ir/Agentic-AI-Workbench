import type { HealthStatus, TokenResponse, User } from '../types/auth'
import type { AgentRunResponse, ArtifactInfo, KnowledgeDoc, SearchResult } from '../types/workbench'
import type {
  BenchmarkCase,
  BenchmarkProgress,
  BenchmarkRunDetail,
  BenchmarkRunSummary,
} from '../types/benchmarks'

class ApiClient {
  private token: string | null = null

  constructor() {
    this.token = localStorage.getItem('sovereign_access_token')
  }

  setToken(token: string | null): void {
    this.token = token
    if (token) {
      localStorage.setItem('sovereign_access_token', token)
    } else {
      localStorage.removeItem('sovereign_access_token')
    }
  }

  getToken(): string | null {
    return this.token
  }

  private getHeaders(): HeadersInit {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`
    }
    return headers
  }

  async checkHealth(): Promise<HealthStatus> {
    const res = await fetch('/health')
    return res.json()
  }

  async checkReady(): Promise<HealthStatus> {
    const res = await fetch('/ready')
    return res.json()
  }

  async login(username: string, password: string): Promise<TokenResponse> {
    const res = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Login failed' }))
      throw new Error(err.detail || 'Authentication failed')
    }
    const data: TokenResponse = await res.json()
    if (data.access_token) {
      this.setToken(data.access_token)
    }
    return data
  }

  async getMe(): Promise<User> {
    const res = await fetch('/api/v1/auth/me', {
      headers: this.getHeaders(),
    })
    if (!res.ok) {
      throw new Error('Failed to fetch user profile')
    }
    return res.json()
  }

  async logout(): Promise<void> {
    this.setToken(null)
  }

  // --- Agent Execution ---
  async runAgentTask(
    prompt: string,
    roleOverride?: string,
    sessionId?: string,
    maxIterations: number = 8,
  ): Promise<AgentRunResponse> {
    const res = await fetch('/api/v1/agent/run', {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({
        prompt,
        role_override: roleOverride || undefined,
        session_id: sessionId || undefined,
        max_iterations: maxIterations,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Agent task failed' }))
      throw new Error(err.detail || 'Agent task failed')
    }
    return res.json()
  }

  async streamAgentTask(
    prompt: string,
    onEvent: (event: string, data: any) => void,
    roleOverride?: string,
    sessionId?: string,
  ): Promise<void> {
    const res = await fetch('/api/v1/agent/stream', {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({
        prompt,
        role_override: roleOverride || undefined,
        session_id: sessionId || undefined,
      }),
    })

    if (!res.ok || !res.body) {
      throw new Error('Failed to initiate agent stream')
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      let currentEvent = 'message'
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          const rawData = line.slice(6).trim()
          try {
            const parsed = JSON.parse(rawData)
            onEvent(currentEvent, parsed)
          } catch {
            onEvent(currentEvent, rawData)
          }
        }
      }
    }
  }

  // --- Knowledge & RAG ---
  async uploadDocument(file: File, collectionId: string = 'default'): Promise<any> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('collection_id', collectionId)

    const headers: Record<string, string> = {}
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`
    }

    const res = await fetch('/api/v1/knowledge/upload', {
      method: 'POST',
      headers,
      body: formData,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Upload failed' }))
      throw new Error(err.detail || 'Failed to upload document')
    }
    return res.json()
  }

  async searchKnowledge(query: string, topK: number = 4, collectionId?: string): Promise<SearchResult[]> {
    const res = await fetch('/api/v1/knowledge/search', {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ query, top_k: topK, collection_id: collectionId }),
    })
    if (!res.ok) {
      throw new Error('Knowledge search failed')
    }
    const data = await res.json()
    return data.results || []
  }

  async listDocuments(collectionId?: string): Promise<KnowledgeDoc[]> {
    const url = collectionId
      ? `/api/v1/knowledge/documents?collection_id=${encodeURIComponent(collectionId)}`
      : '/api/v1/knowledge/documents'
    const res = await fetch(url, { headers: this.getHeaders() })
    if (!res.ok) throw new Error('Failed to list documents')
    return res.json()
  }

  // --- Artifacts ---
  async listArtifacts(sessionId: string): Promise<ArtifactInfo[]> {
    const res = await fetch(`/api/v1/artifacts/${encodeURIComponent(sessionId)}`, {
      headers: this.getHeaders(),
    })
    if (!res.ok) return []
    return res.json()
  }

  // --- Benchmarks & Evaluation ---
  async getBenchmarkScenarios(): Promise<BenchmarkCase[]> {
    const res = await fetch('/api/v1/benchmarks/scenarios', {
      headers: this.getHeaders(),
    })
    if (!res.ok) throw new Error('Failed to load benchmark scenarios')
    return res.json()
  }

  async getLatestBenchmark(): Promise<BenchmarkRunDetail> {
    const res = await fetch('/api/v1/benchmarks/latest', {
      headers: this.getHeaders(),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to fetch latest benchmark' }))
      throw new Error(err.detail || 'Failed to fetch latest benchmark')
    }
    return res.json()
  }

  async getBenchmarkHistory(): Promise<BenchmarkRunSummary[]> {
    const res = await fetch('/api/v1/benchmarks/history', {
      headers: this.getHeaders(),
    })
    if (!res.ok) throw new Error('Failed to fetch benchmark history')
    return res.json()
  }

  async getBenchmarkRun(runId: string): Promise<BenchmarkRunDetail> {
    const res = await fetch(`/api/v1/benchmarks/runs/${encodeURIComponent(runId)}`, {
      headers: this.getHeaders(),
    })
    if (!res.ok) throw new Error('Failed to fetch benchmark run details')
    return res.json()
  }

  async triggerBenchmark(payload: { category?: string; mock?: boolean }): Promise<{ run_id: string; status: string; message: string }> {
    const res = await fetch('/api/v1/benchmarks/run', {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to trigger benchmark run' }))
      throw new Error(err.detail || 'Failed to trigger benchmark run')
    }
    return res.json()
  }

  async getBenchmarkProgress(runId: string): Promise<BenchmarkProgress> {
    const res = await fetch(`/api/v1/benchmarks/progress/${encodeURIComponent(runId)}`, {
      headers: this.getHeaders(),
    })
    if (!res.ok) throw new Error('Failed to fetch benchmark progress')
    return res.json()
  }
}

export const api = new ApiClient()
