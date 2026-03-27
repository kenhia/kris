# kris Sprint Planning Roadmap

## Vision

kris becomes a personal data intelligence platform: a single system that knows about every file across all machines and storage, understands their content, and answers questions about them — locally, privately, and incrementally. It provides both **semantic understanding** ("how does the auth module work?") and **literal precision** ("which files define `resolve_db_url`?", "find every file containing 'grok'") — unified under one query interface.

## Current State (Post-MVP)

Sprint 001 delivered the core vertical slice: **Scan → Index → Embed → Query** for local sources (including NAS mount at `/gratch`). The system handles 745K+ files across two sources, with content-addressed dedup, incremental processing, and CLI-driven natural language queries with LLM synthesis.

**What works today:**
- Rust scanner with SHA-256 change detection
- SQLite catalog with full file metadata (even for skipped files)
- Text/code/markdown extraction, chunking (semantic + AST-aware), embedding
- Qdrant vector search + LLM synthesis with source citations
- Content-addressed dedup across sources
- Archive-on-deletion with user-initiated cleanup
- Multi-source configuration with independent schedules (schema only; execution deferred)

## Roadmap

### Sprint 002 — Production Hardening
**Theme**: Make the existing pipeline robust at real scale before adding new capabilities.

- Default exclude patterns with per-source opt-out (B003)
- Encoding failure diagnostics for tuning excludes (B004)
- Qdrant migration from local/embedded mode to server mode (B008)
- VRAM auto-calibration CLI (B010)
- Log noise reduction (B002)
- `--show-failed` flag for `kris status` (B011)

### Sprint 003 — Summarization & Hybrid Search
**Theme**: Deepen content understanding and improve query quality.

- Local LLM summarization pipeline (file-level and repo-level summaries)
- Hybrid search: semantic + BM25 full-text (SQLite FTS5)
- Environment context enrichment (parent chain summaries in query prompts)
- Multi-collection query fusion (Reciprocal Rank Fusion)

> **Foundation note**: The FTS5 index built here is the foundation for the literal file search capability in Sprint 006. Design the full-text schema to support standalone text search queries (not just as a BM25 re-ranking signal for semantic search). Consider trigram tokenization for substring/pattern matching from the start.

### Sprint 004 — HTTP API & Multi-Model
**Theme**: Open kris up beyond the CLI; support specialized embeddings.

- FastAPI HTTP API service (query, status, config endpoints)
- Multi-model embedding support (e.g., code-specific model alongside text model)
- Model registry expansion (per-file-kind model routing)
- API authentication (localhost-only, token-based)

> **Foundation note**: The API should expose a unified `/search` endpoint that can route to semantic, literal, or hybrid backends. Design the query request schema to support `mode: semantic | literal | hybrid | symbol` from the start, even if only `semantic` and `hybrid` are implemented here.

### Sprint 005 — NAS Scheduling & Dedup Tools
**Theme**: Operationalize for daily use across large storage.

- Scan schedule execution (cron-like triggers per source)
- Background/daemon mode for scheduled scans
- Duplicate detection CLI (group by content hash, show space savings)
- Cross-source file relationship views

### Sprint 006 — Code Search & Literal Indexing
**Theme**: Find files by content — full-text search, regex patterns, and exact matches across the entire corpus.

This sprint adds the **literal search axis** alongside the existing semantic search. While Sprint 003's FTS5 provides the hybrid-search foundation, this sprint builds it into a first-class queryable file index: "find all files containing 'grok'", "which files match this regex?", "show me .py files that import torch".

- Research phase: evaluate open-source code search systems (Zoekt, Livegrep/codesearch, OpenGrok, Sourcegraph/SCIP) for architecture inspiration, indexing strategies, and potential integration
- Literal text search via FTS5 (extend Sprint 003 foundation to standalone search queries)
- Trigram index for fast substring and regex pattern matching
- File-content search CLI (`kris search` or `kris find`) with filters (file kind, source, path pattern, extension)
- Incremental index updates fed by the existing scan → extract pipeline (no redundant file reads)
- Query result ranking and dedup (same content across paths)

> **Research areas**: trigram vs. suffix array indexing; whether to embed an existing search engine (e.g., Tantivy/Rust) or build on SQLite FTS5; how to handle binary/non-UTF8 files; index size budget for 745K+ files.

### Sprint 007 — Code Intelligence
**Theme**: Structural code search — find definitions, references, call sites, and symbols across the codebase.

This sprint elevates code search from "text that matches" to "symbols I can navigate": "where is `resolve_db_url` defined?", "where is it called?", "show all classes that inherit from `BaseModel`".

- Symbol extraction during AST-aware chunking (extend existing tree-sitter pipeline)
- Symbol index in SQLite: function/class/method definitions with file, line, scope
- Reference/call-site tracking: where each symbol is used
- Symbol search CLI (`kris symbol` or extend `kris search --mode symbol`)
- Language-aware queries (definition vs. reference vs. import)
- Cross-file navigation (definition in file A, usage in files B, C, D)
- Integration with the HTTP API (`/search?mode=symbol`)

> **Design note**: The tree-sitter infrastructure from the MVP's AST-aware chunking is the foundation. Symbol extraction should be added as an additional processing step in the existing extract → chunk pipeline, storing results in a SYMBOL table linked to CONTENT by content_hash. This keeps the symbol index consistent with the content-addressed dedup model.

### Sprint 008 — Image & Multimodal
**Theme**: Extend beyond text — vision LLM captioning, thumbnail generation.

- Image captioning pipeline (vision LLM POC, then production)
- Caption embedding for image search
- Thumbnail generation and blob storage
- Multimodal query support (search across text + image captions)

### Sprint 009 — Remote Agents
**Theme**: Extend collection to remote machines.

- Remote agent mode for the Rust scanner binary
- SSH-based manifest push to central catalog
- Remote source configuration and health monitoring
- Agent deployment tooling (single binary distribution)

### Sprint 010 — Classification & Repo Intelligence
**Theme**: Higher-level understanding — auto-tagging, repo summaries.

- Classification/tagging pipeline (LLM + heuristic)
- Repo analysis (detect project type, dependencies, structure)
- Tag-based filtering in queries
- Content relationship graph (CONTENT_RELATION table)

### Sprint 011 — UI & Editor Integration
**Theme**: Make kris accessible beyond the terminal.

- Web UI (read-only dashboard: status, search, browse)
- Editor integration (VS Code extension, Neovim plugin)
- TUI for interactive exploration
- Streaming query responses

### Sprint 012 — Plugin System & Analytics
**Theme**: Extensibility and cross-cutting insights.

- Plugin architecture for custom pipelines and output formats
- Cross-source analytics (file distribution, duplication heatmaps)
- Temporal queries ("what changed this week?")
- Export and reporting capabilities

## Sequencing Rationale

1. **002 (Hardening)** first because the MVP must be reliable at full scale before adding complexity. Running on 745K files will surface edge cases.
2. **003 (Summarization & Hybrid Search)** before API because summaries improve query quality dramatically, and the FTS5 index built here is the foundation for literal file search in Sprint 006.
3. **004 (API)** unlocks Web UI and editor integration in later sprints. The query API is designed from the start with multiple search modes (semantic, literal, hybrid, symbol) even though not all are implemented yet.
4. **005 (Scheduling)** makes kris operational as a "set and forget" system.
5. **006–007 (Code Search → Code Intelligence)** are sequenced here because they build on three prior foundations: FTS5 from Sprint 003, the API from Sprint 004, and the operational pipeline from Sprint 005. Literal text search (006) comes first as the simpler, broader capability; structural symbol search (007) builds on it. Together they complete kris's dual-axis search model: semantic understanding + literal precision.
6. **008 (Multimodal)** adds the most-requested missing modality (images are 30%+ of scanned files).
7. **009 (Remote Agents)** deferred until local pipeline is fully mature — the architecture supports this cleanly.
8. **010–012** are capability extensions that build naturally on the foundation.

## Notes

- Sprint boundaries are flexible — items may shift based on what we learn at scale.
- Each sprint updates `docs/specification.md`, `docs/architecture.md`, and `docs/usage.md` per the constitution.
- Backlog items (B-series) are tracked in the kwi workitems database.
- This document is a living plan; update it as priorities evolve.
