import React, { useState } from 'react'
import {
  X,
  FileText,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Copy,
  Check,
  ExternalLink,
  Layers,
  Hash,
  Database,
  BarChart2,
} from 'lucide-react'
import type { CitationDetail } from '../types/workbench'

interface CitationInspectorDrawerProps {
  citation: CitationDetail | null
  onClose: () => void
  onOpenInKnowledgeHub?: (documentId?: string | null, filename?: string) => void
}

export const CitationInspectorDrawer: React.FC<CitationInspectorDrawerProps> = ({
  citation,
  onClose,
  onOpenInKnowledgeHub,
}) => {
  const [copied, setCopied] = useState(false)

  if (!citation) return null

  const isSupported = citation.status === 'SUPPORTED'
  const isFabricated =
    citation.status === 'FABRICATED_SOURCE' ||
    citation.status === 'FABRICATED_PAGE' ||
    citation.status === 'EMPTY_RETRIEVAL'
  const isMismatch = citation.status === 'UNSUPPORTED_NUMERIC'

  const handleCopyChunk = async () => {
    if (citation.chunk_content) {
      await navigator.clipboard.writeText(citation.chunk_content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const getStatusBadge = () => {
    if (isSupported) {
      return (
        <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800 text-xs font-mono font-medium">
          <CheckCircle2 className="h-3.5 w-3.5" />
          VERIFIED GROUNDED
        </span>
      )
    }
    if (isMismatch) {
      return (
        <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-950 text-amber-400 border border-amber-800 text-xs font-mono font-medium">
          <AlertTriangle className="h-3.5 w-3.5" />
          NUMERIC CLAIM MISMATCH
        </span>
      )
    }
    if (isFabricated) {
      return (
        <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-red-950 text-red-400 border border-red-800 text-xs font-mono font-medium">
          <XCircle className="h-3.5 w-3.5" />
          {citation.status.replace('_', ' ')}
        </span>
      )
    }
    return (
      <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-neutral-800 text-neutral-300 border border-neutral-700 text-xs font-mono">
        {citation.status}
      </span>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm transition-opacity animate-in fade-in">
      <div className="w-full max-w-xl bg-neutral-950 border-l border-neutral-800 shadow-2xl flex flex-col h-full overflow-hidden">
        {/* Drawer Header */}
        <div className="p-5 border-b border-neutral-800 flex items-center justify-between bg-neutral-900/80">
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-neutral-800 border border-neutral-700 flex items-center justify-center">
              <FileText className="h-4 w-4 text-blue-400" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white tracking-tight flex items-center gap-2">
                Citation & Grounding Inspector
              </h2>
              <p className="text-[11px] font-mono text-neutral-400">
                Audited Knowledge Hub Provenance
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {getStatusBadge()}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-neutral-400 hover:text-white hover:bg-neutral-800 transition-colors"
              title="Close Inspector"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Drawer Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5 text-xs font-sans">
          {/* Citation Identification Banner */}
          <div className="p-3.5 rounded-xl bg-neutral-900/60 border border-neutral-800 space-y-2">
            <div className="text-[10px] font-mono uppercase tracking-wider text-neutral-500">
              Cited In AI Synthesis
            </div>
            <div className="font-mono text-xs text-blue-300 bg-black/40 p-2.5 rounded-lg border border-neutral-800/80 break-all">
              {citation.citation_text}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
              <div className="flex items-center gap-2 font-mono text-neutral-300 text-[11px]">
                <span className="font-semibold text-white">{citation.source_file}</span>
                {citation.page_number !== null && citation.page_number !== undefined && (
                  <span className="px-1.5 py-0.5 rounded bg-neutral-800 text-neutral-400 text-[10px]">
                    Page {citation.page_number}
                  </span>
                )}
                {citation.section && (
                  <span className="px-1.5 py-0.5 rounded bg-blue-950/80 text-blue-400 border border-blue-900 text-[10px] uppercase">
                    {citation.section}
                  </span>
                )}
              </div>
              {onOpenInKnowledgeHub && (
                <button
                  type="button"
                  onClick={() => onOpenInKnowledgeHub(citation.document_id, citation.source_file)}
                  className="px-2.5 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-white text-[11px] font-mono flex items-center gap-1.5 transition-colors border border-neutral-700"
                >
                  <ExternalLink className="h-3 w-3 text-neutral-400" />
                  View in Knowledge Hub
                </button>
              )}
            </div>
          </div>

          {/* Verification Reason / Audit Assessment */}
          <div
            className={`p-3.5 rounded-xl border ${
              isSupported
                ? 'bg-emerald-950/20 border-emerald-900/60 text-emerald-300'
                : isMismatch
                ? 'bg-amber-950/20 border-amber-900/60 text-amber-300'
                : 'bg-red-950/20 border-red-900/60 text-red-300'
            }`}
          >
            <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider font-semibold mb-1">
              {isSupported ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
              ) : isMismatch ? (
                <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
              ) : (
                <XCircle className="h-3.5 w-3.5 text-red-400" />
              )}
              Deterministic Grounding Verdict
            </div>
            <p className="text-xs font-mono leading-relaxed">{citation.reason}</p>
          </div>

          {/* Numerical Claim Grounding Comparison */}
          {((citation.extracted_numbers && citation.extracted_numbers.length > 0) ||
            (citation.ground_truth_numbers && citation.ground_truth_numbers.length > 0)) && (
            <div className="p-3.5 rounded-xl bg-neutral-900/60 border border-neutral-800 space-y-2.5">
              <div className="text-[10px] font-mono uppercase tracking-wider text-neutral-500 flex items-center gap-1.5">
                <Hash className="h-3 w-3 text-neutral-400" />
                Numerical Fact Attribution Audit
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs font-mono">
                <div className="p-2.5 rounded-lg bg-black/40 border border-neutral-800">
                  <span className="text-[10px] text-neutral-500 block mb-1">Claimed Numbers</span>
                  <div className="flex flex-wrap gap-1">
                    {citation.extracted_numbers && citation.extracted_numbers.length > 0 ? (
                      citation.extracted_numbers.map((n, i) => (
                        <span
                          key={i}
                          className={`px-1.5 py-0.5 rounded text-[10px] ${
                            citation.ground_truth_numbers?.includes(n)
                              ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                              : 'bg-red-950 text-red-300 border border-red-800 font-bold'
                          }`}
                        >
                          {n}
                        </span>
                      ))
                    ) : (
                      <span className="text-neutral-500 text-[10px]">None</span>
                    )}
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-black/40 border border-neutral-800">
                  <span className="text-[10px] text-neutral-500 block mb-1">Ground Truth Numbers</span>
                  <div className="flex flex-wrap gap-1">
                    {citation.ground_truth_numbers && citation.ground_truth_numbers.length > 0 ? (
                      citation.ground_truth_numbers.map((n, i) => (
                        <span
                          key={i}
                          className="px-1.5 py-0.5 rounded bg-neutral-800 text-neutral-300 border border-neutral-700 text-[10px]"
                        >
                          {n}
                        </span>
                      ))
                    ) : (
                      <span className="text-neutral-500 text-[10px]">None</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Context Sentence in Synthesized Response */}
          {citation.associated_sentence && (
            <div className="p-3.5 rounded-xl bg-neutral-900/60 border border-neutral-800 space-y-1.5">
              <div className="text-[10px] font-mono uppercase tracking-wider text-neutral-500">
                Source Context in Output
              </div>
              <p className="text-xs text-neutral-300 leading-relaxed italic bg-black/40 p-2.5 rounded-lg border border-neutral-800/80">
                &ldquo;{citation.associated_sentence}&rdquo;
              </p>
            </div>
          )}

          {/* Hybrid Retrieval Telemetry */}
          {(citation.similarity !== undefined ||
            citation.dense_similarity !== undefined ||
            citation.sparse_score !== undefined ||
            citation.rrf_score !== undefined) && (
            <div className="p-3.5 rounded-xl bg-neutral-900/60 border border-neutral-800 space-y-2.5">
              <div className="text-[10px] font-mono uppercase tracking-wider text-neutral-500 flex items-center gap-1.5">
                <BarChart2 className="h-3 w-3 text-neutral-400" />
                Hybrid Ranking Telemetry
              </div>
              <div className="grid grid-cols-3 gap-2 text-center font-mono">
                <div className="p-2 rounded-lg bg-black/40 border border-neutral-800">
                  <span className="text-[10px] text-neutral-500 block">Dense Cosine</span>
                  <span className="text-xs font-semibold text-blue-400">
                    {citation.dense_similarity !== undefined
                      ? `${(citation.dense_similarity * 100).toFixed(1)}%`
                      : '—'}
                  </span>
                  {citation.dense_rank && (
                    <span className="block text-[9px] text-neutral-500">Rank #{citation.dense_rank}</span>
                  )}
                </div>

                <div className="p-2 rounded-lg bg-black/40 border border-neutral-800">
                  <span className="text-[10px] text-neutral-500 block">Sparse BM25</span>
                  <span className="text-xs font-semibold text-amber-400">
                    {citation.sparse_score !== undefined ? citation.sparse_score.toFixed(2) : '—'}
                  </span>
                  {citation.sparse_rank && (
                    <span className="block text-[9px] text-neutral-500">Rank #{citation.sparse_rank}</span>
                  )}
                </div>

                <div className="p-2 rounded-lg bg-black/40 border border-neutral-800">
                  <span className="text-[10px] text-neutral-500 block">RRF Score</span>
                  <span className="text-xs font-semibold text-emerald-400">
                    {citation.rrf_score !== undefined ? citation.rrf_score.toFixed(4) : '—'}
                  </span>
                  <span className="block text-[9px] text-neutral-500">Fused</span>
                </div>
              </div>
            </div>
          )}

          {/* Exact Retrieved Chunk Passage */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase tracking-wider text-neutral-500 flex items-center gap-1.5">
                <Layers className="h-3 w-3 text-neutral-400" />
                Retrieved Knowledge Hub Passage
              </span>
              {citation.chunk_content && (
                <button
                  type="button"
                  onClick={handleCopyChunk}
                  className="text-[10px] font-mono text-neutral-400 hover:text-white flex items-center gap-1 transition-colors"
                >
                  {copied ? (
                    <>
                      <Check className="h-3 w-3 text-emerald-400" />
                      Copied
                    </>
                  ) : (
                    <>
                      <Copy className="h-3 w-3" />
                      Copy text
                    </>
                  )}
                </button>
              )}
            </div>

            {citation.chunk_content ? (
              <div className="p-3.5 rounded-xl bg-black border border-neutral-800 font-mono text-xs text-neutral-300 leading-relaxed max-h-64 overflow-y-auto whitespace-pre-wrap selection:bg-blue-900">
                {citation.chunk_content}
              </div>
            ) : (
              <div className="p-4 rounded-xl bg-neutral-900/40 border border-dashed border-neutral-800 text-center text-xs font-mono text-neutral-500">
                No indexed chunk content exists for this ungrounded citation in the session.
              </div>
            )}
          </div>

          {/* Audit Provenance Identifiers */}
          <div className="p-3 rounded-xl bg-neutral-900/40 border border-neutral-800/80 font-mono text-[10px] text-neutral-400 space-y-1">
            <div className="flex items-center justify-between truncate">
              <span className="text-neutral-500 flex items-center gap-1">
                <Database className="h-3 w-3" /> Document ID:
              </span>
              <span className="text-neutral-300 select-all">{citation.document_id || 'unindexed'}</span>
            </div>
            <div className="flex items-center justify-between truncate">
              <span className="text-neutral-500 flex items-center gap-1">
                <Hash className="h-3 w-3" /> Chunk ID:
              </span>
              <span className="text-neutral-300 select-all">{citation.chunk_id || 'unindexed'}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
