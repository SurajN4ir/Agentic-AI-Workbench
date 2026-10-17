export interface RouteDecision {
  role: 'reasoning' | 'coding' | 'vision' | 'ocr' | 'auto'
  confidence: number
  method: string
  reasoning: string
}

export interface ToolResultItem {
  tool_name: string
  tool_call_id: string
  status: 'success' | 'error' | 'partial'
  output?: string | null
  data?: Record<string, any> | null
  error?: string | null
  metadata?: Record<string, any>
}

export interface ArtifactInfo {
  filename: string
  size_bytes: number
  mime_type: string
  session_id: string
  download_url: string
}

export interface AgentRunResponse {
  session_id: string
  status: string
  route_decision: RouteDecision
  model_used: string
  response: string
  thinking_trace: string[]
  iterations: number
  tool_calls_count: number
  tool_results: ToolResultItem[]
  artifacts: Array<{ filename: string; path: string; tool: string; session_id: string }>
  duration_ms: number
}

export interface KnowledgeDoc {
  id: string
  filename: string
  mime_type: string
  file_size_bytes: number
  total_chunks: number
  is_ocr_applied: boolean
  created_at: string
}

export interface SearchResult {
  chunk_id: string
  document_id: string
  filename: string
  content: string
  similarity: number
  section_type: string
  page_number?: number | null
}
