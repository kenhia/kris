# Implementation Plan: MVP Core — Local Scan, Index, Embed, Query

**Branch**: `001-mvp-core` | **Date**: 2026-03-19 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-mvp-core/spec.md`

## Summary

kris MVP delivers a vertical slice through the full architecture:
scan local directories (including NAS mounts) with a Rust scanner,
catalog files in SQLite, plan and execute processing tasks (extract,
chunk, embed) in Python, store vectors in Qdrant, and answer natural
language queries via CLI with LLM synthesis. The scanner and Python
core communicate through a shared SQLite database. Content-addressed
dedup, incremental re-indexing, and archive-on-deletion are
architecturally baked in from the start.

## Technical Context

**Language/Version**: Rust (stable, latest) for scanner; Python 3.12+ for core (managed by `uv`)
**Primary Dependencies**: `sentence-transformers`, `llama-cpp-python`, `qdrant-client`, `typer`, `rich`, `py-tree-sitter`, `charset-normalizer`; Rust: `walkdir`, `sha2`, `rusqlite`, `serde`, `clap`
**Storage**: SQLite (WAL mode) for file catalog + processing state; Qdrant (embedded mode) for vectors
**Testing**: `pytest` (Python), `cargo test` (Rust)
**Target Platform**: Linux (x86_64), single-user local
**Project Type**: CLI tool + background scanner binary
**Performance Goals**: 1,000 files cataloged in <60s (SSD); incremental re-index <30s for <10 changed files; query response <30s (excluding model load)
**Constraints**: 16 GB VRAM budget (NVIDIA 4090 Super); local-first (no cloud dependencies); must handle 1-2M files / ~8 TB addressable
**Scale/Scope**: Single user, ~1-2M files across local dirs + NAS mount

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-Driven Development | PASS | Spec exists at `specs/001-mvp-core/spec.md` with 30 FRs, 6 user stories, 8 success criteria |
| II. Architecture First | PASS | `docs/architecture.md` and `docs/data-model.md` are authoritative; plan aligns with documented architecture |
| III. Test-Driven Development | PASS | Plan includes test strategy per component; TDD Red-Green-Refactor workflow applies |
| IV. Code Standards Gate | PASS | Python: ruff format, ruff check, ty check, pytest. Rust: cargo fmt, cargo clippy, cargo test |
| V. User Documentation | PASS | Plan includes `quickstart.md` and CLI help text as deliverables |
| VI. Quality & Accessibility | PASS | CLI uses Rich for output, respects `NO_COLOR`, errors to stderr, JSON output available |
| VII. Simplicity | PASS | No PyO3 for MVP, embedded Qdrant, standard sqlite3, no unnecessary abstractions |

## Project Structure

### Documentation (this feature)

```text
specs/001-mvp-core/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 research output
├── data-model.md        # Phase 1 data model (MVP subset)
├── contracts/           # Phase 1 CLI contract
│   └── cli.md
├── quickstart.md        # Phase 1 getting started guide
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
kris/
├── pyproject.toml              # Python project root (uv-managed)
├── uv.lock                     # Dependency lockfile
├── Justfile                    # Build commands: build, test, check, dev
├── src/kris/                   # Python package
│   ├── __init__.py
│   ├── __main__.py             # Entry point
│   ├── cli/                    # CLI layer (Typer + Rich)
│   │   ├── __init__.py
│   │   ├── app.py              # Main app, top-level commands
│   │   ├── index.py            # `kris index` command
│   │   ├── query.py            # `kris query` / `kris retrieve` commands
│   │   ├── status.py           # `kris status` command
│   │   ├── config_cmd.py       # `kris config validate`, `kris init`
│   │   ├── cleanup.py          # `kris cleanup` command
│   │   └── duplicates.py       # `kris duplicates` command
│   ├── catalog/                # SQLite catalog layer
│   │   ├── __init__.py
│   │   ├── db.py               # Connection management, migrations
│   │   ├── models.py           # Dataclasses for Source, File, Content, etc.
│   │   ├── files.py            # File CRUD operations
│   │   ├── content.py          # Content CRUD, dedup lookups
│   │   └── tasks.py            # Task CRUD, queue operations
│   ├── scanner/                # Scanner orchestration (invokes Rust binary)
│   │   ├── __init__.py
│   │   └── runner.py           # Launches scanner subprocess, monitors
│   ├── planner/                # Task planning
│   │   ├── __init__.py
│   │   └── planner.py          # Generates task DAGs from pending files
│   ├── processing/             # Processing pipelines
│   │   ├── __init__.py
│   │   ├── worker.py           # Task executor loop
│   │   ├── extract.py          # Text extraction
│   │   ├── chunk.py            # Chunking strategies (text, code, markdown)
│   │   └── embed.py            # Embedding via sentence-transformers
│   ├── models/                 # Model management
│   │   ├── __init__.py
│   │   ├── registry.py         # Model registry (from config)
│   │   └── manager.py          # VRAM-aware model loading/unloading
│   ├── query/                  # Query engine
│   │   ├── __init__.py
│   │   ├── retriever.py        # Qdrant search + metadata enrichment
│   │   ├── synthesizer.py      # LLM answer synthesis
│   │   └── engine.py           # Orchestrates retrieval + synthesis
│   └── config/                 # Configuration
│       ├── __init__.py
│       ├── schema.py           # Config dataclass + TOML loading
│       └── defaults.py         # Default config generation
├── scanner/                    # Rust scanner binary
│   ├── Cargo.toml
│   ├── Cargo.lock
│   └── src/
│       ├── main.rs             # CLI entry point (clap)
│       ├── lib.rs              # Core scanner logic
│       ├── catalog.rs          # SQLite writes (rusqlite)
│       ├── classify.rs         # FileKind classification
│       ├── hash.rs             # SHA-256 content hashing
│       └── walk.rs             # Directory traversal (walkdir)
├── tests/                      # Python tests
│   ├── conftest.py             # Shared fixtures (temp dirs, test DBs)
│   ├── unit/
│   │   ├── test_catalog_db.py
│   │   ├── test_catalog.py
│   │   ├── test_planner.py
│   │   ├── test_extract.py
│   │   ├── test_chunk.py
│   │   ├── test_config.py
│   │   └── test_retriever.py
│   └── integration/
│       ├── test_index_flow.py  # Scan → catalog → plan → process
│       ├── test_query_flow.py  # Query → retrieve → synthesize
│       └── test_scanner.py     # Rust scanner integration
├── docs/
├── specs/
└── .github/
```

**Structure Decision**: Monorepo with Python at root (`pyproject.toml`)
and Rust scanner in `scanner/` subdirectory. Python is the primary
language (CLI, processing, query); Rust is a focused tool (scanner
binary). The scanner is invoked as a subprocess by the Python
orchestration layer. Both share the SQLite database as their IPC
mechanism.

## Technology Decisions

Detailed research in [research.md](research.md). Summary:

| Decision | Choice | Key Rationale |
|----------|--------|---------------|
| PyO3 | Skip for MVP | Python workload is I/O-bound; C-backed libs sufficient |
| Code chunking | py-tree-sitter | Official bindings, C-backed, keeps processing in Python |
| Embedding | sentence-transformers | De facto standard, HuggingFace ecosystem, GPU support |
| LLM inference | llama-cpp-python | GGUF support, OpenAI-compat API, embeds in Python process |
| SQLite concurrency | WAL mode + busy_timeout | Standard pattern for concurrent reader/writer |
| Qdrant | Embedded mode | In-process, no daemon, same API as server mode |
| Project layout | Monorepo, uv-managed | Python root + Rust scanner subdirectory |
| Text extraction | charset-normalizer + stdlib | MVP is text-only, no binary format conversion needed |

## Implementation Phases

### Phase A — Foundation (Catalog + Config + Scanner)

Establish the database schema, configuration loading, and Rust scanner.
These are prerequisites for all processing and query work.

**Components**:
1. SQLite schema + migrations (`catalog/db.py`)
2. Data models / dataclasses (`catalog/models.py`)
3. Configuration loading + validation (`config/`)
4. Rust scanner: directory walk → classify → hash → write to SQLite
5. Scanner runner: Python subprocess to invoke scanner

**Key contract**: Scanner writes to SQLite tables `source`,
`scan_schedule`, `file`, `content`. Python reads from them. WAL mode
enables concurrent access.

**Note**: `kris init` and `kris config validate` are delivered in
Phase D (US3) since US1 can operate with a hand-written config.

**Tests**: Unit tests for catalog CRUD, config parsing/validation.
Integration test for scanner → SQLite → Python read path.

---

### Phase B — Processing Pipeline (Extract + Chunk + Embed)

Build the processing pipeline: task planner, workers, extraction,
chunking, and embedding.

**Components**:
1. Task planner: query pending files → generate task DAGs
2. Worker loop: pull tasks by model affinity → execute → mark complete
3. Text extraction (text/code/markdown/config → raw text)
4. Chunking strategies:
   - Text/markdown: semantic splitting (by paragraph/section)
   - Code: `py-tree-sitter` AST-aware chunking (function/class level)
   - Config: section-based splitting
5. Embedding: `sentence-transformers` → Qdrant embedded mode
6. Model manager: load/unload embedding model, track VRAM
7. `kris index` command (orchestrates scan → plan → process)

**Key contract**: Planner reads `file` + `content` tables, writes
`task` records. Worker reads `task`, writes `chunk` + `embedding`
records and Qdrant points.

**Tests**: Unit tests for each pipeline stage. Integration test
for full index flow (scan → plan → extract → chunk → embed → Qdrant).

---

### Phase C — Query & Retrieval

Build the query engine: semantic search, LLM synthesis, and CLI
commands.

**Components**:
1. Retriever: Qdrant similarity search → enrich with SQLite metadata
2. Synthesizer: Build LLM prompt with retrieved chunks → generate answer
3. Query engine: orchestrate retrieval + synthesis
4. Model manager: load/unload LLM (hot-swap with embedding model)
5. `kris query` command (semantic search + LLM synthesis)
6. `kris retrieve` command (retrieval-only, no LLM)

**Key contract**: Query engine searches Qdrant by vector similarity,
joins back to SQLite for file metadata (paths, sources, tags).
Synthesizer formats chunks as LLM context with source citations.

**Tests**: Unit tests for retriever and synthesizer. Integration
test for full query flow.

---

### Phase D — Status, Dedup, Cleanup

Build observability and maintenance features.

**Components**:
1. `kris status` command: file counts by source, kind, status
2. `kris duplicates` command: group files by content_hash
3. `kris cleanup` command: remove archived files with selectors
4. `kris init` command: create default config
5. `kris config validate` command: validate configuration
6. Incremental re-indexing: detect changes, re-plan, re-process
7. Archive-on-deletion: mark missing files in catalog
8. Logging: structured, leveled, rotating log files

**Tests**: Unit tests for status queries, dedup detection, cleanup
logic. Integration test for incremental re-index and archive flow.

---

### Phase E — Polish & Documentation

Finalize the MVP for usability.

**Components**:
1. CLI help text and error messages (Rich formatting)
2. `--json` output mode for all commands
3. `NO_COLOR` support
4. `docs/setup.md` — installation guide
5. `docs/usage.md` — usage guide
6. Progress indicators for long operations (day zero scan)
7. `docs/specification.md` — combined canonical specification (constitution §I)
8. Performance benchmarks against success criteria (review with user before optimizing)
9. Architecture doc review and update

### Phase F — GPU Embedding Performance (B006)

Fix embedding throughput — GPU is available but per-content-hash
overhead makes the pipeline ~100x slower than necessary.

**Root cause**: `embed_chunks()` is called once per content hash.
Each call instantiates a new `QdrantClient(path=...)` (expensive for
embedded mode) and calls `model.encode()` with a tiny batch (typically
1-5 chunks). The GPU is on `cuda:0` and PyTorch has CUDA 12.8, so
compute is not the issue — per-call overhead is.

**Components**:
1. Create Qdrant client once and pass it through the embed pipeline
2. Log the device at model load time for user visibility
3. Batch `model.encode()` across content hashes for GPU throughput
4. Verify GPU utilization with `nvtop` during a re-embed run

### Phase G — GPU Query/LLM Inference (B007)

Ensure `llama-cpp-python` uses GPU for LLM synthesis during
`kris query`. The model manager already passes `n_gpu_layers=-1`
but the package may have been installed without CUDA support.

**Components**:
1. Diagnose whether `llama-cpp-python` has CUDA bindings
2. Reinstall with CUDA if needed
3. Log the LLM backend/device at load time
4. Verify GPU utilization with `nvtop` during a query

## Complexity Tracking

No constitution violations. All design choices follow the simplest
approach that meets the spec.
