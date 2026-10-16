import type { HealthStatus, TokenResponse, User } from '../types/auth'

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
      // Security rule: tokens ONLY in Authorization header, never in query string
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
}

export const api = new ApiClient()
