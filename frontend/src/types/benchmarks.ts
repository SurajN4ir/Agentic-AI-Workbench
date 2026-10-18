export interface BenchmarkCase {
  id: string
  category: string
  title: string
  prompt: string
  expected_role: string
  expected_tools: string[]
  expected_citations: string[]
  max_allowed_iterations: number
  is_adversarial: boolean
}

export interface CaseResult {
  case_id: string
  category: string
  title: string
  prompt: string
  expected_role: string
  actual_role: string
  expected_tools: string[]
  actual_tools: string[]
  passed: boolean
  score: number
  routing_passed: boolean
  tools_passed: boolean
  citations_passed: boolean
  security_passed: boolean
  iterations_used: number
  duration_ms: number
  output_preview: string
  errors: string[]
  failure_diagnosis: string
}

export interface BenchmarkRunSummary {
  id: string
  timestamp: string
  benchmark_version: string
  model_name: string
  provider_type: string
  category_filter: string | null
  status: string
  total_cases: number
  passed_cases: number
  failed_cases: number
  overall_score: number
  accuracy_percentage: number
  security_violations: number
  average_duration_ms: number
  triggered_by_username: string
}

export interface BenchmarkRunDetail {
  id: string
  timestamp: string
  benchmark_version: string
  model_name: string
  provider_type: string
  category_filter: string | null
  status: string
  total_cases: number
  passed_cases: number
  failed_cases: number
  overall_score: number
  accuracy_percentage: number
  security_violations: number
  average_duration_ms: number
  p95_duration_ms: number
  category_scores: Record<string, number>
  results: CaseResult[]
  triggered_by_username: string
  error_message?: string | null
}

export interface BenchmarkProgress {
  run_id: string
  status: string
  completed_cases: number
  total_cases: number
  current_case_id: string | null
  current_case_title: string | null
  elapsed_ms: number
  error_message?: string | null
  report?: BenchmarkRunDetail | null
}
