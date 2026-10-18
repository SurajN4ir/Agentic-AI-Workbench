export interface CollectionSummary {
  id: string | null
  name: string
  description: string
  document_count: number
  chunk_count: number
  total_bytes: number
  user_id: string | null
  created_at: string
  updated_at: string
}

export interface DocumentDetail {
  id: string
  filename: string
  file_type: string
  file_size_bytes: number
  file_hash: string
  total_chunks: number
  collection_id: string
  status: 'indexed' | 'indexing' | 'failed' | string
  error_message: string | null
  source_path: string | null
  user_id: string | null
  created_at: string
  updated_at: string
}

export interface ChunkSummary {
  id: string
  chunk_index: number
  section_type: string
  page_number: number | null
  char_count: number
  content_preview: string
  metadata: Record<string, any>
  embedding_dim: number
  created_at: string
}

export interface ChunkListResponse {
  document_id: string
  page: number
  page_size: number
  total_chunks: number
  total_pages: number
  items: ChunkSummary[]
}

export interface ChunkDetail {
  id: string
  document_id: string
  filename: string
  chunk_index: number
  section_type: string
  page_number: number | null
  content: string
  metadata: Record<string, any>
  embedding_dim: number
  created_at: string
}

export interface ReindexStatusResponse {
  document_id: string
  status: 'in_progress' | 'completed' | 'failed' | 'idle' | string
  progress_pct: number
  message: string
}

export interface SearchResultItem {
  chunk_id: string
  document_id: string
  filename: string
  content: string
  similarity: number
  section_type: string
  page_number: number | null
  citation: string
  metadata: Record<string, any>
  dense_similarity: number
  dense_rank: number
  sparse_score: number
  sparse_rank: number
  rrf_score: number
}

export interface SearchResponse {
  query: string
  results_count: number
  results: SearchResultItem[]
  formatted_context: string
}
