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
- Production hardening complete: default exclude patterns, encoding diagnostics, Qdrant dual-mode, VRAM calibration, log noise reduction

## Roadmap

### Sprint 002 — Production Hardening
**Theme**: Make the existing pipeline robust at real scale before adding new capabilities.

- Default exclude patterns with per-source opt-out (B003)
- Encoding failure diagnostics for tuning excludes (B004)
- Qdrant migration from local/embedded mode to server mode (B008)
- VRAM auto-calibration CLI (B010)
- Log noise reduction (B002)
- `--show-failed` flag for `kris status` (B011)

### Sprint 003 — OpenSearch Transition
**Theme**: Replace Qdrant with OpenSearch, unifying vector search, full-text search, and structured queries in a single backend.

Migrate the vector store from Qdrant (embedded/server) to OpenSearch. This is a foundational infrastructure change that simplifies all subsequent sprints by consolidating vector search, BM25 full-text search, hybrid query fusion, and structured metadata queries into one engine. SQLite remains the canonical metadata store and scanner IPC layer.

- OpenSearch single-node Docker deployment (docker-compose.yml)
- Python dependency swap: `qdrant-client` → `opensearch-py`
- OpenSearch client factory and index management (k-NN mapping, `ensure_index()`)
- Embedding pipeline rewrite: bulk index to OpenSearch with chunk text + vectors
- Retriever rewrite: k-NN search with pre-filtering (source, file kind)
- Configuration migration: `[qdrant]` → `[opensearch]` in config schema and TOML
- CLI command updates (index, query, retrieve, cleanup, diagnose)
- Test migration: unit mocks and integration tests against OpenSearch
- Data migration: re-index existing content into OpenSearch
- Documentation updates across architecture, data model, and spec docs

> **Design note**: OpenSearch documents carry both the embedding vector and the chunk text content. This means hybrid search (Sprint 004) becomes a query-time configuration rather than a separate indexing pipeline. The full-text content indexed here is also the foundation for literal code search in Sprint 007.

> **Resolves**: B008 (Qdrant local mode 20K point warning) — eliminated entirely. OpenSearch runs as a server from day one.

See `docs/opensearch-research/` for detailed analysis:
- `01-additional-functionality.md` — capabilities OpenSearch unlocks
- `02-architecture-changes.md` — document-by-document change catalog
- `03-transition-plan.md` — phased implementation plan

### Sprint 004 — Summarization & Hybrid Search
**Theme**: Deepen content understanding and improve query quality.

- Local LLM summarization pipeline (file-level and repo-level summaries)
- Hybrid search: semantic + BM25 via OpenSearch native `hybrid` query with score normalization
- Environment context enrichment (parent chain summaries in query prompts)
- Multi-field vector search with built-in score combination

> **Foundation note**: OpenSearch's `hybrid` query type with normalization processor replaces the need for custom RRF code. The full-text index created in Sprint 003 provides the BM25 component. Design search pipelines (normalization technique, combination weights) to be tunable via config. The full-text foundation here also supports standalone literal search in Sprint 007.

### Sprint 005 — HTTP API & Multi-Model
**Theme**: Open kris up beyond the CLI; support specialized embeddings.

- FastAPI HTTP API service (query, status, config endpoints)
- Multi-model embedding support (e.g., code-specific model alongside text model) — maps to multiple k-NN fields in the same OpenSearch index
- Model registry expansion (per-file-kind model routing)
- API authentication (localhost-only, token-based)

> **Foundation note**: The API should expose a unified `/search` endpoint that can route to semantic, literal, or hybrid backends via OpenSearch. Design the query request schema to support `mode: semantic | literal | hybrid | symbol` from the start, even if only `semantic` and `hybrid` are implemented here.

### Sprint 006 — NAS Scheduling & Dedup Tools
**Theme**: Operationalize for daily use across large storage.

- Scan schedule execution (cron-like triggers per source)
- Background/daemon mode for scheduled scans
- Duplicate detection CLI (group by content hash, show space savings)
- Cross-source file relationship views

### Sprint 007 — Code Search & Literal Indexing
**Theme**: Find files by content — full-text search, regex patterns, and exact matches across the entire corpus.

This sprint adds the **literal search axis** alongside the existing semantic search. OpenSearch's full-text index (created in Sprint 003, enhanced in Sprint 004) provides the BM25 foundation. This sprint builds it into a first-class queryable file index: "find all files containing 'grok'", "which files match this regex?", "show me .py files that import torch".

- Literal text search via OpenSearch `match`, `multi_match`, and `query_string` queries
- N-gram / edge n-gram analyzer configuration for substring matching
- Regex search via OpenSearch `regexp` query type
- File-content search CLI (`kris search` or `kris find`) with filters (file kind, source, path pattern, extension)
- Incremental index updates fed by the existing scan → extract pipeline (no redundant file reads)
- Query result ranking and dedup (same content across paths)

> **Research areas**: OpenSearch analyzer tuning (n-gram size, custom tokenizers); per-field analyzer strategy (code vs. prose vs. paths); how to handle binary/non-UTF8 files; index size budget for 745K+ files.

### Sprint 008 — Code Intelligence
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

### Sprint 009 — Image & Multimodal
**Theme**: Extend beyond text — vision LLM captioning, thumbnail generation.

- Image captioning pipeline (vision LLM POC, then production)
- Caption embedding for image search — additional k-NN vector field in OpenSearch index
- Thumbnail generation and blob storage
- Multimodal query support (search across text + image captions via multi-field k-NN)

### Sprint 010 — Remote Agents
**Theme**: Extend collection to remote machines.

- Remote agent mode for the Rust scanner binary
- SSH-based manifest push to central catalog
- Remote source configuration and health monitoring
- Agent deployment tooling (single binary distribution)

### Sprint 011 — Classification & Repo Intelligence
**Theme**: Higher-level understanding — auto-tagging, repo summaries.

- Classification/tagging pipeline (LLM + heuristic)
- Repo analysis (detect project type, dependencies, structure)
- Tag-based filtering in queries
- Content relationship graph (CONTENT_RELATION table)

### Sprint 012 — UI & Editor Integration
**Theme**: Make kris accessible beyond the terminal.

- Web UI (read-only dashboard: status, search, browse) — consider OpenSearch Dashboards for visualization layer
- Editor integration (VS Code extension, Neovim plugin)
- TUI for interactive exploration
- Streaming query responses

### Sprint 013 — Plugin System & Analytics
**Theme**: Extensibility and cross-cutting insights.

- Plugin architecture for custom pipelines and output formats
- Cross-source analytics (file distribution, duplication heatmaps) — leverage OpenSearch aggregation framework
- Temporal queries ("what changed this week?") — OpenSearch date histogram aggregations
- Export and reporting capabilities

## Sequencing Rationale

1. **002 (Hardening)** first because the MVP must be reliable at full scale before adding complexity. Running on 745K files will surface edge cases.
2. **003 (OpenSearch Transition)** before hybrid search because it provides the unified search backend that all subsequent sprints build on. Without it, Sprint 004 would build FTS5 + custom RRF only to replace it later. OpenSearch also resolves B008 (Qdrant 20K point warning) and establishes the full-text index foundation.
3. **004 (Summarization & Hybrid Search)** leverages OpenSearch's native `hybrid` query — no custom fusion code. Summaries improve query quality dramatically.
4. **005 (API)** unlocks Web UI and editor integration in later sprints. The query API is designed from the start with multiple search modes (semantic, literal, hybrid, symbol) even though not all are implemented yet.
5. **006 (Scheduling)** makes kris operational as a "set and forget" system.
6. **007–008 (Code Search → Code Intelligence)** build on OpenSearch's full-text index from Sprint 003, the API from Sprint 005, and the operational pipeline from Sprint 006. Literal text search (007) comes first as the simpler, broader capability; structural symbol search (008) builds on it. Together they complete kris's dual-axis search model: semantic understanding + literal precision.
7. **009 (Multimodal)** adds the most-requested missing modality (images are 30%+ of scanned files). OpenSearch multi-field k-NN makes cross-modal search straightforward.
8. **010 (Remote Agents)** deferred until local pipeline is fully mature — the architecture supports this cleanly.
9. **011–013** are capability extensions that build naturally on the foundation.

## Notes

- Sprint boundaries are flexible — items may shift based on what we learn at scale.
- Each sprint updates `docs/specification.md`, `docs/architecture.md`, and `docs/usage.md` per the constitution.
- Backlog items (B-series) are tracked in the kwi workitems database.
- This document is a living plan; update it as priorities evolve.
