import React, { useEffect, useState, useMemo } from 'react'
import { api } from '../api/client'
import type { User } from '../types/auth'
import type {
  ChunkDetail,
  ChunkListResponse,
  CollectionSummary,
  DocumentDetail,
  ReindexStatusResponse,
  SearchResponse,
} from '../types/knowledge'
import {
  Database,
  FileText,
  Search,
  Upload,
  RefreshCw,
  Trash2,
  FolderPlus,
  Folder,
  Layers,
  ChevronRight,
  ChevronLeft,
  X,
  AlertTriangle,
  CheckCircle2,
  Sparkles,
  Sliders,
  Copy,
  Check,
  MoveRight,
  Eye,
  FileCode,
  FileSpreadsheet,
} from 'lucide-react'

interface KnowledgeHubProps {
  currentUser: User | null
  initialTarget?: {
    documentId?: string | null
    filename?: string
    chunkId?: string | null
  } | null
  onClearTarget?: () => void
}

export const KnowledgeHub: React.FC<KnowledgeHubProps> = ({
  currentUser,
  initialTarget,
  onClearTarget,
}) => {
  const isAdmin = currentUser?.role === 'admin'
  // Navigation View
  const [activeView, setActiveView] = useState<'documents' | 'collections' | 'retrieval'>('documents')

  // Data State
  const [collections, setCollections] = useState<CollectionSummary[]>([])
  const [documents, setDocuments] = useState<DocumentDetail[]>([])
  const [selectedCollection, setSelectedCollection] = useState<string>('all')
  const [selectedFileType, setSelectedFileType] = useState<string>('all')
  const [docSearchQuery, setDocSearchQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [actionSuccess, setActionSuccess] = useState<string | null>(null)

  // Ingestion Modal State
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [targetCollection, setTargetCollection] = useState('default')
  const [uploading, setUploading] = useState(false)

  // Collection Management State
  const [showCreateCollModal, setShowCreateCollModal] = useState(false)
  const [newCollName, setNewCollName] = useState('')
  const [newCollDesc, setNewCollDesc] = useState('')
  const [collActionLoading, setCollActionLoading] = useState(false)

  const [collToDelete, setCollToDelete] = useState<CollectionSummary | null>(null)
  const [deleteMode, setDeleteMode] = useState<'reassign' | 'cascade'>('reassign')
  const [reassignTarget, setReassignTarget] = useState('default')

  // Document Reassign Modal State
  const [docToReassign, setDocToReassign] = useState<DocumentDetail | null>(null)
  const [reassignCollTarget, setReassignCollTarget] = useState('default')

  // Chunk Inspector Drawer State
  const [inspectingDoc, setInspectingDoc] = useState<DocumentDetail | null>(null)
  const [chunkPage, setChunkPage] = useState(1)
  const [chunkSectionFilter, setChunkSectionFilter] = useState<string>('all')
  const [chunkSearchQuery, setChunkSearchQuery] = useState('')
  const [chunkList, setChunkList] = useState<ChunkListResponse | null>(null)
  const [loadingChunks, setLoadingChunks] = useState(false)
  const [selectedChunkDetail, setSelectedChunkDetail] = useState<ChunkDetail | null>(null)
  const [loadingChunkDetail, setLoadingChunkDetail] = useState(false)

  // Re-indexing State (Live Progress Map by Document ID)
  const [reindexingDocs, setReindexingDocs] = useState<Record<string, ReindexStatusResponse>>({})

  // Hybrid Retrieval Tester State
  const [searchQuery, setSearchQuery] = useState('')
  const [searchCollection, setSearchCollection] = useState<string>('all')
  const [searchTopK, setSearchTopK] = useState(5)
  const [searchMinSim, setSearchMinSim] = useState(0.35)
  const [searching, setSearching] = useState(false)
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null)
  const [copiedContext, setCopiedContext] = useState(false)

  // Load Collections and Documents
  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [colls, docs] = await Promise.all([
        api.listCollections(),
        api.listKnowledgeDocuments(selectedCollection === 'all' ? undefined : selectedCollection),
      ])
      setCollections(colls)
      setDocuments(docs)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [selectedCollection])

  // Toast / notification helper
  const notifySuccess = (msg: string) => {
    setActionSuccess(msg)
    setTimeout(() => setActionSuccess(null), 4000)
  }

  // Poll active reindexing jobs
  useEffect(() => {
    const activeDocIds = Object.keys(reindexingDocs).filter(
      (id) => reindexingDocs[id]?.status === 'in_progress'
    )
    if (activeDocIds.length === 0) return

    const timer = setInterval(async () => {
      for (const docId of activeDocIds) {
        try {
          const stat = await api.getReindexStatus(docId)
          setReindexingDocs((prev) => ({ ...prev, [docId]: stat }))
          if (stat.status === 'completed' || stat.status === 'failed') {
            loadData()
          }
        } catch {
          // ignore transient poll errors
        }
      }
    }, 1500)

    return () => clearInterval(timer)
  }, [reindexingDocs])

  // Handle Document Upload
  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!uploadFile) return
    setUploading(true)
    setError(null)
    try {
      await api.uploadDocument(uploadFile, targetCollection)
      notifySuccess(`Document "${uploadFile.name}" successfully ingested into collection "${targetCollection}".`)
      setShowUploadModal(false)
      setUploadFile(null)
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setUploading(false)
    }
  }

  // Handle Create Collection
  const handleCreateCollection = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newCollName.trim()) return
    setCollActionLoading(true)
    setError(null)
    try {
      await api.createCollection(newCollName.trim(), newCollDesc.trim())
      notifySuccess(`Collection "${newCollName}" created.`)
      setShowCreateCollModal(false)
      setNewCollName('')
      setNewCollDesc('')
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setCollActionLoading(false)
    }
  }

  // Handle Delete Collection
  const handleDeleteCollection = async () => {
    if (!collToDelete) return
    setCollActionLoading(true)
    setError(null)
    try {
      await api.deleteCollection(
        collToDelete.name,
        deleteMode === 'reassign' ? reassignTarget : undefined,
        deleteMode === 'cascade'
      )
      notifySuccess(`Collection "${collToDelete.name}" deleted.`)
      setCollToDelete(null)
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setCollActionLoading(false)
    }
  }

  // Handle Document Delete
  const handleDeleteDocument = async (doc: DocumentDetail) => {
    if (!window.confirm(`Are you sure you want to delete "${doc.filename}" and its vector chunks?`)) {
      return
    }
    try {
      await api.deleteDocument(doc.id)
      notifySuccess(`Document "${doc.filename}" deleted.`)
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  // Handle Document Reassign
  const handleReassignDocument = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!docToReassign) return
    setCollActionLoading(true)
    try {
      await api.reassignDocument(docToReassign.id, reassignCollTarget)
      notifySuccess(`Document "${docToReassign.filename}" moved to "${reassignCollTarget}".`)
      setDocToReassign(null)
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setCollActionLoading(false)
    }
  }

  // Handle Trigger Re-index
  const handleTriggerReindex = async (doc: DocumentDetail) => {
    setError(null)
    try {
      const res = await api.triggerReindex(doc.id, false)
      setReindexingDocs((prev) => ({ ...prev, [doc.id]: res }))
      notifySuccess(`Re-indexing started for "${doc.filename}".`)
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  // Load Chunks for Inspector
  const loadChunks = async (docId: string, page: number = 1) => {
    setLoadingChunks(true)
    try {
      const res = await api.listDocumentChunks(
        docId,
        page,
        15,
        chunkSectionFilter === 'all' ? undefined : chunkSectionFilter,
        chunkSearchQuery.trim() || undefined
      )
      setChunkList(res)
      setChunkPage(page)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoadingChunks(false)
    }
  }

  useEffect(() => {
    if (inspectingDoc) {
      loadChunks(inspectingDoc.id, 1)
    }
  }, [inspectingDoc, chunkSectionFilter, chunkSearchQuery])

  // View Chunk Detail Modal
  const handleViewChunkDetail = async (chunkId: string) => {
    setLoadingChunkDetail(true)
    try {
      const detail = await api.getChunkDetail(chunkId)
      setSelectedChunkDetail(detail)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoadingChunkDetail(false)
    }
  }

  // Handle provenance navigation from Citation Inspector
  useEffect(() => {
    if (!initialTarget) return

    // 1. If chunkId is specified, fetch chunk detail modal directly
    if (initialTarget.chunkId) {
      handleViewChunkDetail(initialTarget.chunkId)
    }

    // 2. Open document chunk drawer if target document is found
    const targetDoc = documents.find(
      (d) =>
        (initialTarget.documentId && d.id === initialTarget.documentId) ||
        (initialTarget.filename && d.filename.toLowerCase() === initialTarget.filename.toLowerCase())
    )

    if (targetDoc) {
      setActiveView('documents')
      setInspectingDoc(targetDoc)
      setChunkSectionFilter('all')
      setChunkSearchQuery('')
      notifySuccess(`Navigated to provenance: ${targetDoc.filename}`)
      onClearTarget?.()
    } else if (documents.length > 0 && selectedCollection !== 'all') {
      // Document might be in another collection; widen view to all collections
      setSelectedCollection('all')
    }
  }, [initialTarget, documents, selectedCollection])
  const handleRunSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!searchQuery.trim()) return
    setSearching(true)
    setError(null)
    try {
      const res = await api.searchKnowledgeWithBreakdown(
        searchQuery.trim(),
        searchTopK,
        searchCollection === 'all' ? undefined : searchCollection,
        searchMinSim
      )
      setSearchResponse(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSearching(false)
    }
  }

  const handleCopyContext = () => {
    if (searchResponse?.formatted_context) {
      navigator.clipboard.writeText(searchResponse.formatted_context)
      setCopiedContext(true)
      setTimeout(() => setCopiedContext(false), 2500)
    }
  }

  // Filtered documents list
  const filteredDocuments = useMemo(() => {
    return documents.filter((doc) => {
      const matchSearch =
        !docSearchQuery.trim() ||
        doc.filename.toLowerCase().includes(docSearchQuery.toLowerCase()) ||
        doc.file_hash.toLowerCase().includes(docSearchQuery.toLowerCase())
      const matchType =
        selectedFileType === 'all' || doc.file_type.toLowerCase() === selectedFileType.toLowerCase()
      return matchSearch && matchType
    })
  }, [documents, docSearchQuery, selectedFileType])

  // Aggregate stats
  const totalChunksCount = useMemo(() => {
    return collections.reduce((acc, c) => acc + c.chunk_count, 0)
  }, [collections])

  const totalBytesCount = useMemo(() => {
    return collections.reduce((acc, c) => acc + c.total_bytes, 0)
  }, [collections])

  // Helper for file type icons
  const renderFileTypeIcon = (ext: string) => {
    const e = ext.toLowerCase()
    if (e.includes('pdf')) return <FileText className="h-4 w-4 text-red-400" />
    if (e.includes('doc')) return <FileText className="h-4 w-4 text-blue-400" />
    if (e.includes('xls') || e.includes('csv')) return <FileSpreadsheet className="h-4 w-4 text-emerald-400" />
    if (e.includes('py') || e.includes('sql') || e.includes('json') || e.includes('yaml'))
      return <FileCode className="h-4 w-4 text-amber-400" />
    return <FileText className="h-4 w-4 text-neutral-400" />
  }

  return (
    <div className="flex-1 flex flex-col bg-neutral-950 overflow-hidden font-sans">
      {/* Top Knowledge Hub Bar */}
      <div className="border-b border-neutral-800 bg-neutral-900/60 px-6 py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5 text-emerald-400" />
            <h2 className="text-base font-semibold text-white tracking-tight">
              Knowledge Hub &amp; Chunk Inspector
            </h2>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
              pgvector 768-D
            </span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800">
              RRF Hybrid
            </span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-neutral-800 text-neutral-300 border border-neutral-700">
              {isAdmin ? 'ADMIN ACCESS' : 'USER ACCESS'}
            </span>
          </div>
          <p className="text-xs text-neutral-400 mt-0.5">
            Cryptographic deduplication, layout-aware parsing, chunk inspection, and verified citation provenance.
          </p>
        </div>

        {/* Global Hub Action Buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowCreateCollModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-800 border border-neutral-700 text-xs text-neutral-200 hover:text-white hover:bg-neutral-700 transition-colors"
          >
            <FolderPlus className="h-3.5 w-3.5 text-blue-400" />
            New Collection
          </button>
          <button
            onClick={() => setShowUploadModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 text-xs font-medium text-white hover:bg-emerald-500 transition-colors shadow-sm"
          >
            <Upload className="h-3.5 w-3.5" />
            Ingest Document
          </button>
          <button
            onClick={loadData}
            disabled={loading}
            className="p-1.5 rounded-lg bg-neutral-800 border border-neutral-700 text-neutral-400 hover:text-white hover:bg-neutral-700 transition-colors"
            title="Refresh Knowledge Hub"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Aggregate Statistics Header */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 px-6 py-3 border-b border-neutral-800/80 bg-neutral-950/40 text-xs font-mono">
        <div className="flex items-center gap-2 p-2 rounded bg-neutral-900/50 border border-neutral-800">
          <Folder className="h-4 w-4 text-blue-400" />
          <div>
            <div className="text-[10px] text-neutral-500 uppercase">Collections</div>
            <div className="font-semibold text-white">{collections.length}</div>
          </div>
        </div>
        <div className="flex items-center gap-2 p-2 rounded bg-neutral-900/50 border border-neutral-800">
          <FileText className="h-4 w-4 text-emerald-400" />
          <div>
            <div className="text-[10px] text-neutral-500 uppercase">Documents</div>
            <div className="font-semibold text-white">{documents.length}</div>
          </div>
        </div>
        <div className="flex items-center gap-2 p-2 rounded bg-neutral-900/50 border border-neutral-800">
          <Layers className="h-4 w-4 text-purple-400" />
          <div>
            <div className="text-[10px] text-neutral-500 uppercase">Total Chunks</div>
            <div className="font-semibold text-white">{totalChunksCount.toLocaleString()}</div>
          </div>
        </div>
        <div className="flex items-center gap-2 p-2 rounded bg-neutral-900/50 border border-neutral-800">
          <Database className="h-4 w-4 text-amber-400" />
          <div>
            <div className="text-[10px] text-neutral-500 uppercase">Storage Volume</div>
            <div className="font-semibold text-white">{(totalBytesCount / 1024).toFixed(1)} KB</div>
          </div>
        </div>
      </div>

      {/* View Selector Tabs */}
      <div className="flex items-center px-6 border-b border-neutral-800 bg-neutral-900/30 gap-6">
        <button
          onClick={() => setActiveView('documents')}
          className={`py-3 text-xs font-medium border-b-2 flex items-center gap-2 transition-colors ${
            activeView === 'documents'
              ? 'border-emerald-500 text-white'
              : 'border-transparent text-neutral-400 hover:text-neutral-200'
          }`}
        >
          <FileText className="h-3.5 w-3.5" />
          Documents &amp; Chunks ({documents.length})
        </button>
        <button
          onClick={() => setActiveView('collections')}
          className={`py-3 text-xs font-medium border-b-2 flex items-center gap-2 transition-colors ${
            activeView === 'collections'
              ? 'border-emerald-500 text-white'
              : 'border-transparent text-neutral-400 hover:text-neutral-200'
          }`}
        >
          <Folder className="h-3.5 w-3.5" />
          Collections Directory ({collections.length})
        </button>
        <button
          onClick={() => setActiveView('retrieval')}
          className={`py-3 text-xs font-medium border-b-2 flex items-center gap-2 transition-colors ${
            activeView === 'retrieval'
              ? 'border-emerald-500 text-white'
              : 'border-transparent text-neutral-400 hover:text-neutral-200'
          }`}
        >
          <Search className="h-3.5 w-3.5" />
          Hybrid Retrieval &amp; Ranking Tester
        </button>
      </div>

      {/* Notifications / Error Banner */}
      {error && (
        <div className="mx-6 mt-3 p-3 rounded-lg bg-red-950/80 border border-red-800/80 text-xs text-red-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-white">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
      {actionSuccess && (
        <div className="mx-6 mt-3 p-3 rounded-lg bg-emerald-950/80 border border-emerald-800/80 text-xs text-emerald-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
            <span>{actionSuccess}</span>
          </div>
          <button onClick={() => setActionSuccess(null)} className="text-emerald-400 hover:text-white">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* MAIN VIEW CONTENT */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* ============================================================ */}
        {/* VIEW 1: DOCUMENTS & CHUNKS TABLE */}
        {/* ============================================================ */}
        {activeView === 'documents' && (
          <div className="space-y-4">
            {/* Filter Bar */}
            <div className="flex flex-wrap items-center justify-between gap-3 bg-neutral-900/60 p-3 rounded-xl border border-neutral-800 text-xs">
              <div className="flex flex-wrap items-center gap-3">
                {/* Collection Filter */}
                <div className="flex items-center gap-1.5">
                  <span className="text-neutral-400 font-mono">Collection:</span>
                  <select
                    value={selectedCollection}
                    onChange={(e) => setSelectedCollection(e.target.value)}
                    className="bg-neutral-800 border border-neutral-700 rounded px-2.5 py-1 text-white focus:outline-none focus:border-neutral-500 font-mono"
                  >
                    <option value="all">All Collections ({collections.length})</option>
                    {collections.map((c) => (
                      <option key={c.name} value={c.name}>
                        {c.name} ({c.document_count})
                      </option>
                    ))}
                  </select>
                </div>

                {/* File Type Filter */}
                <div className="flex items-center gap-1.5">
                  <span className="text-neutral-400 font-mono">Type:</span>
                  <select
                    value={selectedFileType}
                    onChange={(e) => setSelectedFileType(e.target.value)}
                    className="bg-neutral-800 border border-neutral-700 rounded px-2.5 py-1 text-white focus:outline-none focus:border-neutral-500 font-mono"
                  >
                    <option value="all">All Formats</option>
                    <option value=".pdf">PDF Document (.pdf)</option>
                    <option value=".docx">Word Document (.docx)</option>
                    <option value=".md">Markdown (.md)</option>
                    <option value=".txt">Plain Text (.txt)</option>
                    <option value=".csv">Spreadsheet (.csv)</option>
                    <option value=".xlsx">Excel (.xlsx)</option>
                  </select>
                </div>
              </div>

              {/* Filename Search Input */}
              <div className="flex items-center gap-2 w-full sm:w-auto">
                <div className="relative flex-1 sm:w-64">
                  <Search className="h-3.5 w-3.5 text-neutral-500 absolute left-2.5 top-2.5" />
                  <input
                    type="text"
                    value={docSearchQuery}
                    onChange={(e) => setDocSearchQuery(e.target.value)}
                    placeholder="Filter by filename or hash..."
                    className="w-full bg-neutral-800 border border-neutral-700 rounded pl-8 pr-3 py-1 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-neutral-500"
                  />
                </div>
                {(docSearchQuery || selectedCollection !== 'all' || selectedFileType !== 'all') && (
                  <button
                    onClick={() => {
                      setDocSearchQuery('')
                      setSelectedCollection('all')
                      setSelectedFileType('all')
                    }}
                    className="text-[11px] text-neutral-400 hover:text-white underline"
                  >
                    Reset
                  </button>
                )}
              </div>
            </div>

            {/* Document Listing Table */}
            <div className="rounded-xl border border-neutral-800 bg-neutral-900/40 overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-neutral-900 border-b border-neutral-800 text-neutral-400 font-mono text-[11px] uppercase">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Document / Filename</th>
                    <th className="px-4 py-3 font-semibold">Collection</th>
                    <th className="px-4 py-3 font-semibold">Chunks</th>
                    <th className="px-4 py-3 font-semibold">File Size</th>
                    <th className="px-4 py-3 font-semibold">Status</th>
                    <th className="px-4 py-3 font-semibold">Ingested At</th>
                    <th className="px-4 py-3 font-semibold text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-800/60 font-sans">
                  {filteredDocuments.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-12 text-center text-neutral-500 font-mono">
                        No ingested documents found matching the filter criteria.
                      </td>
                    </tr>
                  ) : (
                    filteredDocuments.map((doc) => {
                      const reindexJob = reindexingDocs[doc.id]
                      const isIndexing = reindexJob?.status === 'in_progress' || doc.status === 'indexing'

                      return (
                        <tr key={doc.id} className="hover:bg-neutral-900/60 transition-colors">
                          {/* Filename & Type */}
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2.5">
                              {renderFileTypeIcon(doc.file_type)}
                              <div>
                                <span className="font-medium text-white block leading-tight">{doc.filename}</span>
                                <span className="text-[10px] text-neutral-500 font-mono">
                                  SHA: {doc.file_hash.slice(0, 12)}...
                                </span>
                              </div>
                            </div>
                          </td>

                          {/* Collection */}
                          <td className="px-4 py-3">
                            <span className="inline-flex items-center gap-1 font-mono text-[11px] px-2 py-0.5 rounded bg-neutral-800 text-neutral-300 border border-neutral-700">
                              <Folder className="h-3 w-3 text-blue-400" />
                              {doc.collection_id}
                            </span>
                          </td>

                          {/* Chunks */}
                          <td className="px-4 py-3 font-mono">
                            <span className="text-white font-semibold">{doc.total_chunks}</span>
                            <span className="text-neutral-500 text-[10px] ml-1">chunks</span>
                          </td>

                          {/* Size */}
                          <td className="px-4 py-3 font-mono text-neutral-300">
                            {(doc.file_size_bytes / 1024).toFixed(1)} KB
                          </td>

                          {/* Status */}
                          <td className="px-4 py-3">
                            {isIndexing ? (
                              <div className="flex items-center gap-1.5 text-blue-400 font-mono text-[11px]">
                                <RefreshCw className="h-3 w-3 animate-spin" />
                                <span>{reindexJob?.progress_pct ? `${reindexJob.progress_pct}%` : 'Indexing...'}</span>
                              </div>
                            ) : doc.status === 'failed' ? (
                              <div className="flex items-center gap-1.5 text-red-400 font-mono text-[11px]" title={doc.error_message || 'Indexing error'}>
                                <AlertTriangle className="h-3 w-3" />
                                <span>Failed</span>
                              </div>
                            ) : (
                              <div className="flex items-center gap-1.5 text-emerald-400 font-mono text-[11px]">
                                <CheckCircle2 className="h-3 w-3" />
                                <span>Indexed</span>
                              </div>
                            )}
                          </td>

                          {/* Created Timestamp */}
                          <td className="px-4 py-3 text-neutral-400 font-mono text-[11px]">
                            {new Date(doc.created_at).toLocaleDateString()}
                          </td>

                          {/* Actions */}
                          <td className="px-4 py-3 text-right">
                            <div className="inline-flex items-center gap-1.5">
                              {/* Inspect Chunks */}
                              <button
                                onClick={() => setInspectingDoc(doc)}
                                className="flex items-center gap-1 px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-white font-medium text-[11px] transition-colors border border-neutral-700"
                                title="Inspect document vector chunks"
                              >
                                <Eye className="h-3 w-3 text-emerald-400" />
                                Chunks
                              </button>

                              {/* Re-index */}
                              <button
                                onClick={() => handleTriggerReindex(doc)}
                                disabled={isIndexing}
                                className="flex items-center gap-1 px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-300 hover:text-white text-[11px] transition-colors border border-neutral-700 disabled:opacity-40"
                                title="Re-extract and re-embed document chunks"
                              >
                                <RefreshCw className={`h-3 w-3 ${isIndexing ? 'animate-spin text-blue-400' : 'text-neutral-400'}`} />
                                Re-index
                              </button>

                              {/* Reassign Collection */}
                              <button
                                onClick={() => {
                                  setDocToReassign(doc)
                                  setReassignCollTarget(doc.collection_id)
                                }}
                                className="p-1 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-400 hover:text-blue-400 transition-colors border border-neutral-700"
                                title="Reassign to another collection"
                              >
                                <MoveRight className="h-3 w-3" />
                              </button>

                              {/* Delete */}
                              <button
                                onClick={() => handleDeleteDocument(doc)}
                                className="p-1 rounded bg-neutral-800 hover:bg-red-950/60 text-neutral-400 hover:text-red-400 transition-colors border border-neutral-700"
                                title="Delete document"
                              >
                                <Trash2 className="h-3 w-3" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ============================================================ */}
        {/* VIEW 2: COLLECTIONS DIRECTORY */}
        {/* ============================================================ */}
        {activeView === 'collections' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-white">Active Knowledge Collections</h3>
                <p className="text-xs text-neutral-400">
                  Logical multi-tenant isolation partitions for documents and retrieval filtering.
                </p>
              </div>
              <button
                onClick={() => setShowCreateCollModal(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 text-xs font-medium text-white hover:bg-emerald-500 transition-colors"
              >
                <FolderPlus className="h-3.5 w-3.5" />
                Create Collection
              </button>
            </div>

            {/* Collection Cards Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {collections.map((coll) => {
                const isDefault = coll.name === 'default'

                return (
                  <div
                    key={coll.name}
                    className="rounded-xl border border-neutral-800 bg-neutral-900/50 p-4 flex flex-col justify-between hover:border-neutral-700 transition-colors"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <Folder className="h-4 w-4 text-blue-400" />
                          <span className="font-semibold text-sm text-white font-mono">{coll.name}</span>
                        </div>
                        {isDefault ? (
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                            DEFAULT
                          </span>
                        ) : (
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-neutral-800 text-neutral-400 border border-neutral-700">
                            USER-DEFINED
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-neutral-400 line-clamp-2 mb-4">
                        {coll.description || 'No description provided for this collection.'}
                      </p>
                    </div>

                    <div className="border-t border-neutral-800 pt-3">
                      <div className="grid grid-cols-3 gap-2 text-center text-[11px] font-mono mb-3">
                        <div className="bg-neutral-950/60 p-1.5 rounded border border-neutral-800">
                          <div className="text-[10px] text-neutral-500 uppercase">Docs</div>
                          <div className="font-semibold text-white">{coll.document_count}</div>
                        </div>
                        <div className="bg-neutral-950/60 p-1.5 rounded border border-neutral-800">
                          <div className="text-[10px] text-neutral-500 uppercase">Chunks</div>
                          <div className="font-semibold text-white">{coll.chunk_count}</div>
                        </div>
                        <div className="bg-neutral-950/60 p-1.5 rounded border border-neutral-800">
                          <div className="text-[10px] text-neutral-500 uppercase">Size</div>
                          <div className="font-semibold text-white">{(coll.total_bytes / 1024).toFixed(0)} KB</div>
                        </div>
                      </div>

                      <div className="flex items-center justify-between text-xs pt-1">
                        <button
                          onClick={() => {
                            setSelectedCollection(coll.name)
                            setActiveView('documents')
                          }}
                          className="text-emerald-400 hover:text-emerald-300 font-medium flex items-center gap-1"
                        >
                          View Documents <ChevronRight className="h-3 w-3" />
                        </button>

                        {!isDefault && (
                          <button
                            onClick={() => {
                              setCollToDelete(coll)
                              setDeleteMode('reassign')
                              setReassignTarget('default')
                            }}
                            className="p-1 rounded text-neutral-500 hover:text-red-400 transition-colors"
                            title="Delete collection"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* ============================================================ */}
        {/* VIEW 3: HYBRID RETRIEVAL & RANKING TESTER */}
        {/* ============================================================ */}
        {activeView === 'retrieval' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Search Configuration Panel */}
            <div className="lg:col-span-5 space-y-4">
              <div className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-5">
                <h3 className="text-sm font-semibold text-white flex items-center gap-2 mb-1">
                  <Sliders className="h-4 w-4 text-emerald-400" />
                  Hybrid Query Execution
                </h3>
                <p className="text-xs text-neutral-400 mb-4">
                  Executes dense vector search (all-minilm:l6-v2) + sparse BM25 term weighting, combined via Reciprocal Rank Fusion (k=60).
                </p>

                <form onSubmit={handleRunSearch} className="space-y-4 text-xs font-sans">
                  {/* Query input */}
                  <div>
                    <label className="block text-neutral-300 font-medium mb-1">Semantic Query</label>
                    <textarea
                      rows={3}
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="e.g. maximum turbine bearing temperature limit under full load"
                      className="w-full bg-neutral-800 border border-neutral-700 rounded-lg p-3 text-white placeholder-neutral-500 focus:outline-none focus:border-neutral-500 text-xs"
                    />
                  </div>

                  {/* Collection Target */}
                  <div>
                    <label className="block text-neutral-300 font-medium mb-1 font-mono text-[11px]">
                      Collection Target
                    </label>
                    <select
                      value={searchCollection}
                      onChange={(e) => setSearchCollection(e.target.value)}
                      className="w-full bg-neutral-800 border border-neutral-700 rounded-lg p-2 text-white text-xs font-mono"
                    >
                      <option value="all">Global (All Collections)</option>
                      {collections.map((c) => (
                        <option key={c.name} value={c.name}>
                          {c.name} ({c.document_count} docs)
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Top-K and Min Similarity */}
                  <div className="grid grid-cols-2 gap-3 font-mono text-[11px]">
                    <div>
                      <div className="flex justify-between text-neutral-400 mb-1">
                        <span>Top-K Results:</span>
                        <span className="text-white font-semibold">{searchTopK}</span>
                      </div>
                      <input
                        type="range"
                        min="1"
                        max="20"
                        value={searchTopK}
                        onChange={(e) => setSearchTopK(Number(e.target.value))}
                        className="w-full accent-emerald-500 cursor-pointer"
                      />
                    </div>
                    <div>
                      <div className="flex justify-between text-neutral-400 mb-1">
                        <span>Min Similarity:</span>
                        <span className="text-white font-semibold">{(searchMinSim * 100).toFixed(0)}%</span>
                      </div>
                      <input
                        type="range"
                        min="0"
                        max="0.8"
                        step="0.05"
                        value={searchMinSim}
                        onChange={(e) => setSearchMinSim(Number(e.target.value))}
                        className="w-full accent-emerald-500 cursor-pointer"
                      />
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={searching || !searchQuery.trim()}
                    className="w-full rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium py-2.5 px-4 text-xs flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
                  >
                    <Search className="h-3.5 w-3.5" />
                    {searching ? 'Computing Hybrid RRF...' : 'Run Hybrid Search'}
                  </button>
                </form>
              </div>

              {/* Formatted Context Snippet */}
              {searchResponse && (
                <div className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-4 space-y-2">
                  <div className="flex items-center justify-between text-xs font-mono">
                    <span className="text-neutral-400 flex items-center gap-1.5">
                      <Sparkles className="h-3.5 w-3.5 text-amber-400" />
                      Injected Prompt Context Block
                    </span>
                    <button
                      onClick={handleCopyContext}
                      className="text-neutral-400 hover:text-white flex items-center gap-1 text-[11px]"
                    >
                      {copiedContext ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                      {copiedContext ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                  <pre className="p-3 rounded-lg bg-black/60 border border-neutral-800 text-[10px] text-neutral-300 font-mono whitespace-pre-wrap max-h-48 overflow-y-auto leading-relaxed">
                    {searchResponse.formatted_context}
                  </pre>
                </div>
              )}
            </div>

            {/* Retrieved Results Stream with Detailed Ranking Breakdown */}
            <div className="lg:col-span-7 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                  <Layers className="h-4 w-4 text-purple-400" />
                  Retrieved Chunks &amp; Rank Breakdown ({searchResponse?.results.length || 0})
                </h3>
                {searchResponse && (
                  <span className="text-xs text-neutral-400 font-mono">
                    Evaluated against {totalChunksCount} candidate vectors
                  </span>
                )}
              </div>

              {!searchResponse ? (
                <div className="rounded-xl border border-neutral-800 bg-neutral-900/20 p-12 text-center text-neutral-500 font-mono text-xs">
                  Run a query to inspect hybrid ranking scores (dense similarity, BM25 term score, and RRF rank).
                </div>
              ) : searchResponse.results.length === 0 ? (
                <div className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-12 text-center text-amber-400 font-mono text-xs">
                  No chunks met the similarity threshold ({(searchMinSim * 100).toFixed(0)}%). Try lowering the threshold or broadening the query.
                </div>
              ) : (
                <div className="space-y-3">
                  {searchResponse.results.map((item, idx) => (
                    <div
                      key={item.chunk_id}
                      className="rounded-xl border border-neutral-800 bg-neutral-900/50 p-4 space-y-2.5 hover:border-neutral-700 transition-colors"
                    >
                      {/* Header with Blended & Provenance */}
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-800/80 pb-2">
                        <div className="flex items-center gap-2">
                          <span className="h-5 w-5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800 flex items-center justify-center font-mono text-[10px] font-bold">
                            #{idx + 1}
                          </span>
                          <span className="font-semibold text-xs text-white flex items-center gap-1.5 font-mono">
                            <FileText className="h-3.5 w-3.5 text-blue-400" />
                            {item.filename}
                            {item.page_number ? ` (Page ${item.page_number})` : ''}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 font-mono text-[11px]">
                          <span className="px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800 font-semibold">
                            Blended: {(item.similarity * 100).toFixed(1)}%
                          </span>
                          <span className="px-2 py-0.5 rounded bg-neutral-800 text-neutral-300 uppercase text-[10px]">
                            {item.section_type}
                          </span>
                        </div>
                      </div>

                      {/* True Hybrid Ranking Metrics Breakdown */}
                      <div className="grid grid-cols-3 gap-2 bg-black/40 p-2 rounded-lg border border-neutral-800/80 text-[10px] font-mono">
                        <div>
                          <span className="text-neutral-500 uppercase block">Dense (Cosine):</span>
                          <span className="text-blue-400 font-semibold">
                            {item.dense_similarity.toFixed(4)} (Rank #{item.dense_rank})
                          </span>
                        </div>
                        <div>
                          <span className="text-neutral-500 uppercase block">Sparse (BM25):</span>
                          <span className="text-amber-400 font-semibold">
                            {item.sparse_score.toFixed(3)} (Rank #{item.sparse_rank})
                          </span>
                        </div>
                        <div>
                          <span className="text-neutral-500 uppercase block">RRF Combined:</span>
                          <span className="text-purple-400 font-semibold">
                            {item.rrf_score.toFixed(5)}
                          </span>
                        </div>
                      </div>

                      {/* Chunk Content */}
                      <div className="text-xs text-neutral-200 leading-relaxed font-sans bg-neutral-950 p-3 rounded-lg border border-neutral-800/60 whitespace-pre-wrap">
                        {item.content}
                      </div>

                      {/* Citation header format */}
                      <div className="text-[10px] text-neutral-400 font-mono flex items-center justify-between">
                        <span>Citation: {item.citation}</span>
                        <button
                          onClick={() => handleViewChunkDetail(item.chunk_id)}
                          className="text-emerald-400 hover:text-emerald-300 underline"
                        >
                          Inspect Raw Metadata
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ============================================================ */}
      {/* DRAWER: CHUNK INSPECTOR PANEL */}
      {/* ============================================================ */}
      {inspectingDoc && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-40 flex justify-end">
          <div className="w-full max-w-2xl bg-neutral-900 border-l border-neutral-800 h-full flex flex-col shadow-2xl">
            {/* Drawer Header */}
            <div className="p-4 border-b border-neutral-800 flex items-center justify-between bg-neutral-950">
              <div className="flex items-center gap-2">
                <Layers className="h-5 w-5 text-emerald-400" />
                <div>
                  <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                    Chunk Inspector: {inspectingDoc.filename}
                  </h3>
                  <p className="text-[11px] text-neutral-400 font-mono">
                    Collection: {inspectingDoc.collection_id} &middot; {inspectingDoc.total_chunks} total chunks &middot; SHA: {inspectingDoc.file_hash.slice(0, 10)}...
                  </p>
                </div>
              </div>
              <button
                onClick={() => setInspectingDoc(null)}
                className="p-1 rounded text-neutral-400 hover:text-white hover:bg-neutral-800"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Filter and Search within chunks */}
            <div className="p-3 border-b border-neutral-800 bg-neutral-900/60 flex items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-2">
                <span className="text-neutral-400 font-mono text-[11px]">Section:</span>
                <select
                  value={chunkSectionFilter}
                  onChange={(e) => setChunkSectionFilter(e.target.value)}
                  className="bg-neutral-800 border border-neutral-700 rounded px-2 py-1 text-white text-[11px] font-mono"
                >
                  <option value="all">All Sections</option>
                  <option value="heading">Headings</option>
                  <option value="paragraph">Paragraphs</option>
                  <option value="table">Tables / Key-Values</option>
                  <option value="code">Code Blocks</option>
                  <option value="list">Lists</option>
                </select>
              </div>

              <div className="relative flex-1 max-w-xs">
                <Search className="h-3 w-3 text-neutral-500 absolute left-2.5 top-2.5" />
                <input
                  type="text"
                  value={chunkSearchQuery}
                  onChange={(e) => setChunkSearchQuery(e.target.value)}
                  placeholder="Filter chunk text..."
                  className="w-full bg-neutral-800 border border-neutral-700 rounded pl-7 pr-3 py-1 text-[11px] text-white placeholder-neutral-500 focus:outline-none"
                />
              </div>
            </div>

            {/* Chunks List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {loadingChunks ? (
                <div className="py-12 text-center text-xs text-neutral-400 font-mono">
                  <RefreshCw className="h-5 w-5 animate-spin mx-auto mb-2 text-emerald-400" />
                  Loading document vector chunks...
                </div>
              ) : !chunkList || chunkList.items.length === 0 ? (
                <div className="py-12 text-center text-xs text-neutral-500 font-mono">
                  No chunks match the current filters.
                </div>
              ) : (
                chunkList.items.map((chunk) => (
                  <div
                    key={chunk.id}
                    className="rounded-lg border border-neutral-800 bg-neutral-950 p-3 space-y-2 hover:border-neutral-700 transition-colors"
                  >
                    <div className="flex items-center justify-between text-[11px] font-mono">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-emerald-400">#{chunk.chunk_index + 1}</span>
                        <span className="px-1.5 py-0.5 rounded bg-neutral-800 text-neutral-300 uppercase text-[10px]">
                          {chunk.section_type}
                        </span>
                        {chunk.page_number && (
                          <span className="text-neutral-400 text-[10px]">Page {chunk.page_number}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-neutral-400 text-[10px]">
                        <span>{chunk.embedding_dim}-dim embedding</span>
                        <span>{chunk.char_count} chars</span>
                        <button
                          onClick={() => handleViewChunkDetail(chunk.id)}
                          className="text-blue-400 hover:text-blue-300 underline"
                        >
                          Raw View
                        </button>
                      </div>
                    </div>

                    <p className="text-xs text-neutral-200 font-sans leading-relaxed whitespace-pre-wrap bg-neutral-900 p-2.5 rounded border border-neutral-800/80">
                      {chunk.content_preview}
                    </p>

                    {Object.keys(chunk.metadata).length > 0 && (
                      <div className="flex flex-wrap gap-1 text-[10px] font-mono text-neutral-400">
                        {Object.entries(chunk.metadata).slice(0, 3).map(([k, v]) => (
                          <span key={k} className="px-1.5 py-0.5 rounded bg-neutral-900 border border-neutral-800">
                            {k}: {String(v)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

            {/* Pagination Controls */}
            {chunkList && chunkList.total_pages > 1 && (
              <div className="p-3 border-t border-neutral-800 bg-neutral-950 flex items-center justify-between text-xs font-mono">
                <span className="text-neutral-400">
                  Page {chunkPage} of {chunkList.total_pages} ({chunkList.total_chunks} chunks)
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => loadChunks(inspectingDoc.id, chunkPage - 1)}
                    disabled={chunkPage <= 1}
                    className="p-1.5 rounded bg-neutral-800 hover:bg-neutral-700 text-white disabled:opacity-40"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => loadChunks(inspectingDoc.id, chunkPage + 1)}
                    disabled={chunkPage >= chunkList.total_pages}
                    className="p-1.5 rounded bg-neutral-800 hover:bg-neutral-700 text-white disabled:opacity-40"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* MODAL: SINGLE CHUNK DETAIL (RAW VIEW) */}
      {/* ============================================================ */}
      {loadingChunkDetail && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center">
          <div className="bg-neutral-900 border border-neutral-800 p-4 rounded-xl flex items-center gap-3 text-xs font-mono text-white">
            <RefreshCw className="h-4 w-4 animate-spin text-emerald-400" />
            <span>Fetching chunk metadata...</span>
          </div>
        </div>
      )}

      {selectedChunkDetail && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-2xl bg-neutral-900 border border-neutral-800 rounded-xl flex flex-col max-h-[85vh] overflow-hidden shadow-2xl">
            <div className="p-4 border-b border-neutral-800 flex items-center justify-between bg-neutral-950">
              <div className="flex items-center gap-2">
                <FileCode className="h-4 w-4 text-emerald-400" />
                <h3 className="text-sm font-semibold text-white font-mono">
                  Chunk #{selectedChunkDetail.chunk_index + 1} &middot; {selectedChunkDetail.filename}
                </h3>
              </div>
              <button
                onClick={() => setSelectedChunkDetail(null)}
                className="p-1 rounded text-neutral-400 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="p-4 overflow-y-auto space-y-4 text-xs font-mono">
              <div>
                <span className="text-neutral-500 uppercase text-[10px] block mb-1">Unclipped Content:</span>
                <pre className="p-3 rounded-lg bg-black/60 border border-neutral-800 text-neutral-200 font-sans whitespace-pre-wrap max-h-60 overflow-y-auto leading-relaxed">
                  {selectedChunkDetail.content}
                </pre>
              </div>

              <div>
                <span className="text-neutral-500 uppercase text-[10px] block mb-1">Metadata JSON:</span>
                <pre className="p-3 rounded-lg bg-black/60 border border-neutral-800 text-emerald-300 text-[11px] whitespace-pre-wrap max-h-40 overflow-y-auto">
                  {JSON.stringify(selectedChunkDetail.metadata, null, 2)}
                </pre>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[11px] text-neutral-400">
                <div>Vector Dimension: {selectedChunkDetail.embedding_dim} float32 values</div>
                <div>Section Type: {selectedChunkDetail.section_type}</div>
                <div>Page Reference: {selectedChunkDetail.page_number || 'N/A'}</div>
                <div>Chunk UUID: {selectedChunkDetail.id}</div>
              </div>
            </div>

            <div className="p-3 border-t border-neutral-800 bg-neutral-950 flex justify-end">
              <button
                onClick={() => setSelectedChunkDetail(null)}
                className="px-4 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-xs text-white"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* MODAL: INGEST DOCUMENT */}
      {/* ============================================================ */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-neutral-900 border border-neutral-800 rounded-xl overflow-hidden shadow-2xl">
            <div className="p-4 border-b border-neutral-800 flex items-center justify-between bg-neutral-950">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <Upload className="h-4 w-4 text-emerald-400" />
                Ingest Document to Knowledge Base
              </h3>
              <button
                onClick={() => setShowUploadModal(false)}
                className="text-neutral-400 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleUpload} className="p-5 space-y-4 text-xs">
              <div>
                <label className="block text-neutral-300 font-medium mb-1">Target Collection</label>
                <select
                  value={targetCollection}
                  onChange={(e) => setTargetCollection(e.target.value)}
                  className="w-full bg-neutral-800 border border-neutral-700 rounded-lg p-2.5 text-white font-mono"
                >
                  {collections.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name} {c.name === 'default' ? '(Default)' : ''}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-neutral-300 font-medium mb-1">Select File</label>
                <input
                  type="file"
                  accept=".pdf,.docx,.doc,.xlsx,.csv,.txt,.md,.json,.py,.sql,.yaml,.yml"
                  onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  className="w-full text-xs text-neutral-400 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-neutral-800 file:text-white hover:file:bg-neutral-700 cursor-pointer"
                />
                <p className="text-[10px] text-neutral-500 mt-1">
                  Supported: PDF, DOCX, XLSX, CSV, TXT, MD, Python, JSON, SQL, YAML.
                </p>
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowUploadModal(false)}
                  className="px-3 py-1.5 rounded-lg bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={uploading || !uploadFile}
                  className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium disabled:opacity-50 flex items-center gap-2"
                >
                  {uploading ? (
                    <>
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" /> Ingesting...
                    </>
                  ) : (
                    'Start Ingestion'
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* MODAL: CREATE COLLECTION */}
      {/* ============================================================ */}
      {showCreateCollModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-neutral-900 border border-neutral-800 rounded-xl overflow-hidden shadow-2xl">
            <div className="p-4 border-b border-neutral-800 flex items-center justify-between bg-neutral-950">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <FolderPlus className="h-4 w-4 text-blue-400" />
                Create New Knowledge Collection
              </h3>
              <button
                onClick={() => setShowCreateCollModal(false)}
                className="text-neutral-400 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleCreateCollection} className="p-5 space-y-4 text-xs">
              <div>
                <label className="block text-neutral-300 font-medium mb-1 font-mono text-[11px]">
                  Collection Slug (Alphanumeric, hyphens)
                </label>
                <input
                  type="text"
                  value={newCollName}
                  onChange={(e) => setNewCollName(e.target.value)}
                  placeholder="e.g. aero-turbines-2026"
                  required
                  className="w-full bg-neutral-800 border border-neutral-700 rounded-lg p-2.5 text-white font-mono focus:outline-none focus:border-neutral-500"
                />
              </div>

              <div>
                <label className="block text-neutral-300 font-medium mb-1">Description (Optional)</label>
                <input
                  type="text"
                  value={newCollDesc}
                  onChange={(e) => setNewCollDesc(e.target.value)}
                  placeholder="e.g. Maintenance specifications and thermal barrier test data"
                  className="w-full bg-neutral-800 border border-neutral-700 rounded-lg p-2.5 text-white focus:outline-none focus:border-neutral-500"
                />
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowCreateCollModal(false)}
                  className="px-3 py-1.5 rounded-lg bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={collActionLoading || !newCollName.trim()}
                  className="px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium disabled:opacity-50"
                >
                  {collActionLoading ? 'Creating...' : 'Create Collection'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* MODAL: DELETE COLLECTION SAFEGUARD */}
      {/* ============================================================ */}
      {collToDelete && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-neutral-900 border border-neutral-800 rounded-xl overflow-hidden shadow-2xl">
            <div className="p-4 border-b border-neutral-800 flex items-center justify-between bg-neutral-950">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-red-400" />
                Safely Delete Collection: {collToDelete.name}
              </h3>
              <button onClick={() => setCollToDelete(null)} className="text-neutral-400 hover:text-white">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="p-5 space-y-4 text-xs font-sans">
              <p className="text-neutral-300">
                Collection <strong className="text-white font-mono">{collToDelete.name}</strong> currently contains{' '}
                <strong className="text-emerald-400 font-mono">{collToDelete.document_count}</strong> documents and{' '}
                <strong className="text-purple-400 font-mono">{collToDelete.chunk_count}</strong> vector chunks.
              </p>

              {collToDelete.document_count > 0 && (
                <div className="space-y-3 bg-neutral-950 p-3.5 rounded-lg border border-neutral-800">
                  <span className="text-[11px] font-semibold text-neutral-200 block">Choose Document Action:</span>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="deleteMode"
                      checked={deleteMode === 'reassign'}
                      onChange={() => setDeleteMode('reassign')}
                      className="accent-emerald-500"
                    />
                    <span className="text-neutral-300">Reassign documents to another collection</span>
                  </label>

                  {deleteMode === 'reassign' && (
                    <div className="pl-6 pt-1">
                      <select
                        value={reassignTarget}
                        onChange={(e) => setReassignTarget(e.target.value)}
                        className="w-full bg-neutral-800 border border-neutral-700 rounded p-2 text-white font-mono text-[11px]"
                      >
                        {collections
                          .filter((c) => c.name !== collToDelete.name)
                          .map((c) => (
                            <option key={c.name} value={c.name}>
                              {c.name}
                            </option>
                          ))}
                      </select>
                    </div>
                  )}

                  <label className="flex items-center gap-2 cursor-pointer text-red-400">
                    <input
                      type="radio"
                      name="deleteMode"
                      checked={deleteMode === 'cascade'}
                      onChange={() => setDeleteMode('cascade')}
                      className="accent-red-500"
                    />
                    <span>Permanently delete all {collToDelete.document_count} documents and vector chunks</span>
                  </label>
                </div>
              )}

              <div className="pt-2 flex justify-end gap-2">
                <button
                  onClick={() => setCollToDelete(null)}
                  className="px-3 py-1.5 rounded-lg bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDeleteCollection}
                  disabled={collActionLoading}
                  className="px-4 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white font-medium disabled:opacity-50"
                >
                  {collActionLoading ? 'Deleting...' : 'Confirm Deletion'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* MODAL: REASSIGN DOCUMENT */}
      {/* ============================================================ */}
      {docToReassign && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-neutral-900 border border-neutral-800 rounded-xl overflow-hidden shadow-2xl">
            <div className="p-4 border-b border-neutral-800 flex items-center justify-between bg-neutral-950">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <MoveRight className="h-4 w-4 text-blue-400" />
                Reassign Document Collection
              </h3>
              <button onClick={() => setDocToReassign(null)} className="text-neutral-400 hover:text-white">
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleReassignDocument} className="p-5 space-y-4 text-xs">
              <p className="text-neutral-300">
                Move <strong className="text-white">{docToReassign.filename}</strong> from{' '}
                <strong className="text-blue-400 font-mono">{docToReassign.collection_id}</strong> to:
              </p>

              <div>
                <label className="block text-neutral-300 font-medium mb-1 font-mono text-[11px]">
                  Target Collection
                </label>
                <select
                  value={reassignCollTarget}
                  onChange={(e) => setReassignCollTarget(e.target.value)}
                  className="w-full bg-neutral-800 border border-neutral-700 rounded-lg p-2.5 text-white font-mono"
                >
                  {collections.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setDocToReassign(null)}
                  className="px-3 py-1.5 rounded-lg bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={collActionLoading || reassignCollTarget === docToReassign.collection_id}
                  className="px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium disabled:opacity-50"
                >
                  {collActionLoading ? 'Moving...' : 'Move Document'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
