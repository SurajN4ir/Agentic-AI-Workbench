export interface User {
  id: string
  username: string
  name: string
  email: string | null
  role: 'admin' | 'user'
  department: string | null
  avatar_color: string
  totp_enabled: boolean
  is_active: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  requires_2fa: boolean
  temp_token?: string | null
}

export interface HealthStatus {
  status: string
  database?: string
}
