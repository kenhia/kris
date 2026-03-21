# Tasks: MVP Core — Local Scan, Index, Embed, Query

**Input**: Design documents from `/specs/001-mvp-core/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/cli.md, quickstart.md

**Tests**: Included — constitution mandates TDD (Principle III).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- **CT###**: Commit Task — run pre-commit checks and commit at end of each phase (provides revert points)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization — Python project, Rust project, tooling

- [x] T001 Initialize Python project with `uv init` and configure `pyproject.toml` with project metadata, entry point (`kris`), and dev dependencies (pytest, ruff, ty)
- [x] T002 Create `src/kris/__init__.py` and `src/kris/__main__.py` entry point
- [x] T003 [P] Initialize Rust scanner project with `cargo init` in `scanner/` and configure `Cargo.toml` with dependencies (walkdir, sha2, rusqlite, serde, serde_json, clap)
- [x] T004 [P] Create `Justfile` with targets: `build` (scanner + uv sync), `test` (cargo test + pytest), `check` (fmt + lint + typecheck + test), `fmt` (cargo fmt + ruff format), `lint` (cargo clippy + ruff check + ty check)
- [x] T005 [P] Configure `ruff.toml` (or `[tool.ruff]` in pyproject.toml) with line-length, target version, and rule selection
- [x] T006 [P] Add `.pre-commit-config.yaml` or equivalent to run `just check` before commit
- [x] T007 Run `uv sync` and `cargo build` to verify project scaffolding compiles clean
- [x] CT001 Run `just check`, commit Phase 1: "feat(001): project scaffolding — Python, Rust, tooling"

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST complete before any user story — catalog schema, data models, configuration

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T008 Create catalog data models (dataclasses) for Source, File, Content, Task, Chunk, Embedding, ModelRegistryEntry, ScanSchedule in `src/kris/catalog/models.py`
- [x] T009 Implement SQLite database connection manager with WAL mode, busy_timeout, foreign keys, and schema migration support in `src/kris/catalog/db.py`
- [x] T010 Implement MVP DDL schema creation (all tables and indexes from `data-model.md`) in `src/kris/catalog/db.py`
- [x] T011 [P] Write unit tests for database initialization, WAL mode verification, and schema creation in `tests/unit/test_catalog_db.py`
- [x] T012 Implement config schema dataclass and TOML loading/validation in `src/kris/config/schema.py` (single-source config sufficient for US1; multi-source extension in US3/T054)
- [x] T013 [P] Implement default config generation (XDG paths, sensible defaults, inline comments) in `src/kris/config/defaults.py`
- [x] T014 [P] Write unit tests for config loading, validation, defaults, and XDG path resolution in `tests/unit/test_config.py`
- [x] T015 Create shared test fixtures (temp directories, test SQLite databases, sample file trees) in `tests/conftest.py`
- [x] T016 Implement File CRUD operations (insert, upsert on scan, query by status/source/kind) in `src/kris/catalog/files.py`
- [x] T017 [P] Implement Content CRUD operations (insert-if-not-exists by content_hash, status updates) in `src/kris/catalog/content.py`
- [x] T018 [P] Implement Task CRUD operations (create, query by status/model_hint, update status, dependency checks) in `src/kris/catalog/tasks.py`
- [x] T019 Write unit tests for File, Content, and Task CRUD operations in `tests/unit/test_catalog.py`
- [x] T020 Create CLI app skeleton with Typer, Rich console, `--json` global flag, `--verbose` flag, error-to-stderr handling in `src/kris/cli/app.py`
- [x] CT002 Run `just check`, commit Phase 2: "feat(001): foundational — catalog, config, CLI skeleton"

**Checkpoint**: Foundation ready — catalog, config, and CLI skeleton operational. User story implementation can begin.

---

## Phase 3: User Story 1 — Scan and Index Local Files (Priority: P1) — MVP

**Goal**: Scan local directories with the Rust scanner, catalog all discovered files in SQLite, extract text, chunk, embed, and store vectors in Qdrant.

**Independent Test**: Configure a source pointing at a test directory with text, code, and markdown files. Run `kris index`. Verify files are cataloged, chunks are created, and embeddings are in Qdrant.

### Tests for User Story 1

- [x] T021 [P] [US1] Write unit tests for Rust scanner: directory walk, file classification, SHA-256 hashing, SQLite writes in `scanner/src/tests/` (Rust `#[cfg(test)]` modules)
- [x] T022 [P] [US1] Write unit tests for text extraction (text, code, markdown, config files with encoding detection) in `tests/unit/test_extract.py`
- [x] T023 [P] [US1] Write unit tests for chunking strategies (text semantic split, code tree-sitter AST split, markdown section split) in `tests/unit/test_chunk.py`
- [x] T024 [P] [US1] Write unit tests for task planner (pending files → task DAG generation, model affinity ordering) in `tests/unit/test_planner.py`
- [x] T025 [P] [US1] Write integration test for full index flow (scan → catalog → plan → extract → chunk → embed → Qdrant) in `tests/integration/test_index_flow.py`

### Implementation for User Story 1

**Rust Scanner:**

- [x] T026 [US1] Implement directory traversal with `walkdir`, exclude pattern support, symlink handling, and symlink cycle detection in `scanner/src/walk.rs`
- [x] T027 [P] [US1] Implement FileKind classification by extension + MIME heuristics in `scanner/src/classify.rs`
- [x] T028 [P] [US1] Implement SHA-256 content hashing with streaming reader for large files in `scanner/src/hash.rs`
- [x] T029 [US1] Implement SQLite catalog writes (upsert file records, insert/update content records, set processing_status, detect hash mismatch between scan and extraction for re-queue) in `scanner/src/catalog.rs`
- [x] T030 [US1] Implement scanner main: parse CLI args (source config path, source ID), orchestrate walk → classify → hash → catalog in `scanner/src/main.rs` and `scanner/src/lib.rs`
- [x] T031 [US1] Write integration test: run scanner binary against a temp directory, verify SQLite contents in `tests/integration/test_scanner.py`

**Python Processing Pipeline:**

- [x] T032 [US1] Implement scanner runner: invoke Rust scanner binary as subprocess for a single configured source, pass config, capture output/errors in `src/kris/scanner/runner.py` (multi-source iteration added in US3/T057)
- [x] T033 [US1] Implement task planner: query pending files from catalog → generate extract/chunk/embed task DAGs with model affinity hints, ordering tasks to minimize model load/unload cycles (FR-017) in `src/kris/planner/planner.py`
- [x] T034 [US1] Implement text extraction pipeline (read file, detect encoding with charset-normalizer, return raw text) in `src/kris/processing/extract.py`
- [x] T035 [US1] Implement chunking strategies: text/markdown semantic splitting (paragraph/section boundaries) in `src/kris/processing/chunk.py`
- [x] T036 [US1] Implement code-aware chunking with `py-tree-sitter` (function/class level AST nodes) in `src/kris/processing/chunk.py`
- [x] T037 [US1] Implement model registry: load model definitions from config, query by type/id in `src/kris/models/registry.py`
- [x] T038 [US1] Implement model manager: VRAM-aware loading/unloading of sentence-transformers embedding model in `src/kris/models/manager.py`
- [x] T039 [US1] Implement embedding pipeline: load model → encode chunks → write to Qdrant (embedded mode) + write embedding records to SQLite in `src/kris/processing/embed.py`
- [x] T040 [US1] Implement task worker loop: pull tasks by model affinity (FR-017) → execute pipeline step → mark complete/failed → retry logic including Qdrant connection failure handling in `src/kris/processing/worker.py`
- [x] T041 [US1] Implement `kris index` CLI command: orchestrate scanner run → task planning → worker execution → summary output in `src/kris/cli/index.py`
- [x] T042 [US1] Implement progress indicators (Rich progress bar) for scan and processing steps in `src/kris/cli/index.py`
- [x] CT003 Run `just check`, commit Phase 3: "feat(001): US1 — scan, index, extract, chunk, embed"

**Checkpoint**: `kris index` scans a directory, catalogs files, extracts text, chunks, embeds, and stores vectors in Qdrant. US1 is fully functional.

---

## Phase 4: User Story 2 — Query My Files (Priority: P1)

**Goal**: Semantic search against embedded chunks via CLI with LLM-synthesized answers and source citations.

**Independent Test**: After indexing files, run `kris query "how does X work?"` and verify the response includes relevant content with file path citations.

### Tests for User Story 2

- [x] T043 [P] [US2] Write unit tests for retriever: Qdrant vector search, metadata enrichment from SQLite, result ranking in `tests/unit/test_retriever.py`
- [x] T044 [P] [US2] Write unit tests for synthesizer: prompt construction, source citation formatting, no-results handling in `tests/unit/test_synthesizer.py`
- [x] T045 [P] [US2] Write integration test for full query flow (query → embed → search Qdrant → enrich → synthesize → format) in `tests/integration/test_query_flow.py`

### Implementation for User Story 2

- [x] T046 [US2] Implement retriever: embed query with same model → Qdrant similarity search → join with SQLite for file metadata (path, source, kind) in `src/kris/query/retriever.py`
- [x] T047 [US2] Implement synthesizer: build LLM prompt with retrieved chunks as context → call llama-cpp-python → format answer with source citations in `src/kris/query/synthesizer.py`
- [x] T048 [US2] Implement query engine: orchestrate retriever + synthesizer, handle no-results case, support retrieval-only mode in `src/kris/query/engine.py`
- [x] T049 [US2] Extend model manager to support LLM loading/unloading (hot-swap with embedding model) in `src/kris/models/manager.py`
- [x] T050 [US2] Implement `kris query` CLI command: parse question + flags (--show-sources, --top-k, --source, --kind) → query engine → Rich-formatted output in `src/kris/cli/query.py`
- [x] T051 [US2] Implement `kris retrieve` CLI command: retrieval-only mode (chunks without LLM synthesis) in `src/kris/cli/query.py`
- [x] CT004 Run `just check`, commit Phase 4: "feat(001): US2 — query, retrieve, LLM synthesis"

**Checkpoint**: `kris query` and `kris retrieve` return answers with source citations. US2 is fully functional. Combined with US1, this is a complete vertical slice.

---

## Phase 5: User Story 3 — Configure Sources and Scan Schedules (Priority: P2)

**Goal**: Configure multiple sources with independent scan schedules and exclude patterns; `kris init` creates a default config.

**Independent Test**: Create config with two sources (different scan intervals). Run `kris index`. Verify both are scanned. Run `kris init` to create default config.

### Tests for User Story 3

- [x] T052 [P] [US3] Write unit tests for multi-source config parsing, schedule validation, exclude pattern handling in `tests/unit/test_config.py` (extend existing)
- [x] T053 [P] [US3] Write unit tests for `kris init` default config creation and `kris config validate` in `tests/unit/test_config_cmd.py`

### Implementation for User Story 3

- [x] T054 [US3] Extend config schema to support multiple sources with per-source schedules and exclude patterns in `src/kris/config/schema.py`
- [x] T055 [US3] Implement `kris init` CLI command: create default config at XDG path with inline comments in `src/kris/cli/config_cmd.py`
- [x] T056 [US3] Implement `kris config validate` CLI command: load and validate config, report errors in `src/kris/cli/config_cmd.py`
- [x] T057 [US3] Update scanner runner to iterate over configured sources and pass per-source settings to the Rust scanner in `src/kris/scanner/runner.py`
- [x] T058 [US3] Update Rust scanner to accept exclude patterns and scan schedule metadata from CLI args in `scanner/src/main.rs`
- [x] CT005 Run `just check`, commit Phase 5: "feat(001): US3 — multi-source config, init, validate"

**Checkpoint**: Multiple sources with different schedules are supported. `kris init` bootstraps a new user.

---

## Phase 6: User Story 4 — View Index Status (Priority: P2)

**Goal**: `kris status` displays file counts by source, kind, and processing status, plus failed file details.

**Independent Test**: After indexing, run `kris status` and verify output shows correct counts and any failed files with error reasons.

### Tests for User Story 4

- [x] T059 [P] [US4] Write unit tests for status query functions (counts by source, kind, status; failed file listing) in `tests/unit/test_status.py`

### Implementation for User Story 4

- [x] T060 [US4] Implement status query functions in catalog: aggregate counts by source/kind/status, list failed files with errors in `src/kris/catalog/files.py` (extend)
- [x] T061 [US4] Implement `kris status` CLI command: Rich table output with per-source breakdown, `--json` support, `--source` filter in `src/kris/cli/status.py`
- [x] CT006 Run `just check`, commit Phase 6: "feat(001): US4 — status command"

**Checkpoint**: `kris status` provides observability into the index state.

---

## Phase 7: User Story 5 — Content-Addressed Dedup (Priority: P3)

**Goal**: Files with identical content share processing artifacts; `kris duplicates` lists duplicate groups.

**Independent Test**: Copy a file to two indexed directories. Run `kris index`. Verify one set of chunks/embeddings. Run `kris duplicates` to see the group.

### Tests for User Story 5

- [x] T062 [P] [US5] Write unit tests for dedup logic: content_hash sharing, duplicate group queries in `tests/unit/test_catalog.py` (extend)
- [x] T063 [P] [US5] Write integration test: index duplicate files across sources, verify shared artifacts in `tests/integration/test_index_flow.py` (extend)

### Implementation for User Story 5

- [x] T064 [US5] Implement duplicate detection query: group files by content_hash where count > 1, with source/path details in `src/kris/catalog/content.py` (extend)
- [x] T065 [US5] Implement `kris duplicates` CLI command: Rich table output with groups, `--source` and `--min-size` filters in `src/kris/cli/duplicates.py`
- [x] T066 [US5] Verify that the index pipeline correctly skips reprocessing when content_hash already has chunks/embeddings (dedup path in planner) in `src/kris/planner/planner.py` (verify/fix)
- [x] CT007 Run `just check`, commit Phase 7: "feat(001): US5 — content-addressed dedup, duplicates command"

**Checkpoint**: Dedup is verified end-to-end. `kris duplicates` lists duplicate groups.

---

## Phase 8: User Story 6 — Archive and Cleanup (Priority: P3)

**Goal**: Missing files are preserved as `missing`; `kris cleanup` removes archived entries with selectors and confirmation.

**Independent Test**: Index a directory, delete a file, re-run `kris index`. Verify file is `missing`. Use `kris cleanup` to remove it.

### Tests for User Story 6

- [x] T067 [P] [US6] Write unit tests for archive logic: missing detection, visibility transition, timestamp tracking in `tests/unit/test_catalog.py` (extend)
- [x] T068 [P] [US6] Write unit tests for cleanup: selector filtering (path, age, source), cascade delete of artifacts in `tests/unit/test_cleanup.py`
- [x] T069 [P] [US6] Write integration test for archive flow: index → delete file → re-index → verify missing → cleanup in `tests/integration/test_index_flow.py` (extend)

### Implementation for User Story 6

- [x] T070 [US6] Implement archive-on-deletion in scanner catalog writes: set `visibility='missing'` and `disappeared_at` for files not seen in scan in `scanner/src/catalog.rs` (extend)
- [x] T071 [US6] Implement cleanup operations: delete file/content/chunk/embedding records by selectors (path pattern, age, source) with cascade in `src/kris/catalog/files.py` (extend)
- [x] T072 [US6] Implement Qdrant point deletion for cleaned-up embeddings in `src/kris/processing/embed.py` (extend)
- [x] T073 [US6] Implement `kris cleanup` CLI command: selector flags (--older-than, --path, --source), dry-run, confirmation prompt, Rich output in `src/kris/cli/cleanup.py`
- [x] CT008 Run `just check`, commit Phase 8: "feat(001): US6 — archive-on-deletion, cleanup command"

**Checkpoint**: Files missing from disk are preserved. `kris cleanup` removes them with user confirmation.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Finalize MVP usability, documentation, and logging

- [x] T074 [P] Implement structured, leveled, rotating log file support in `src/kris/config/schema.py` and `src/kris/cli/app.py`
- [x] T075 [P] Ensure all CLI commands support `--json` output per contract in `src/kris/cli/app.py`
- [x] T076 [P] Ensure Rich output respects `NO_COLOR` and terminal width in `src/kris/cli/app.py`
- [x] T077 [P] Create `docs/setup.md` — installation and setup guide
- [x] T078 [P] Create `docs/usage.md` — usage guide with examples
- [x] T079 Run `specs/001-mvp-core/quickstart.md` end-to-end validation: fresh install → init → index → query → status; time the end-to-end experience against SC-007 10-minute goal
- [x] T080 [P] Run performance benchmarks against SC-001 (1000 files <60s), SC-002 (re-index <30s), SC-003 (query <30s), SC-008 (100k+ files stability); document results and review with user before attempting optimization
- [x] T081 [P] Review and update `docs/architecture.md` and `docs/clarifications-needed.md` if any plan/implementation decisions diverge from current documentation
- [x] T082 Create `docs/specification.md` — combined canonical specification per constitution §I (SDD)
- [x] T083 Final `just check` pass: ruff format --check, ruff check, ty check, pytest, cargo fmt --check, cargo clippy, cargo test
- [x] CT009 Run `just check`, commit Phase 9: "feat(001): polish — docs, benchmarks, specification, final QA"

---

## Phase 10: GPU Embedding Performance (B006)

**Purpose**: Fix embedding pipeline throughput — eliminate per-content-hash overhead

- [x] T084 Diagnose: confirm `torch.cuda.is_available()`, log device at model load time in `src/kris/models/manager.py`
- [x] T085 [P] Refactor `src/kris/processing/embed.py`: accept a `QdrantClient` parameter instead of instantiating per call
- [x] T086 [P] Update `src/kris/processing/worker.py`: create `QdrantClient` once in `run_worker()`, pass to `execute_task()` and `embed_chunks()`
- [x] T087 [P] Update callers of `embed_chunks()` and `delete_points()` to pass/use shared client (including tests)
- [x] T088 Verify: run `kris index` on a test directory, confirm GPU compute visible in `nvtop`, measure throughput improvement
- [x] CT010 Run `just check`, commit Phase 10: "perf(001): GPU embedding — eliminate per-call QdrantClient overhead"

---

## Phase 11: GPU Query/LLM Inference (B007)

**Purpose**: Ensure LLM synthesis uses GPU during `kris query`

- [x] T089 Diagnose: check if `llama-cpp-python` has CUDA support, log backend at LLM load time in `src/kris/models/manager.py`
- [x] T090 [P] If CPU-only, reinstall `llama-cpp-python` with CUDA (`CMAKE_ARGS="-DGGML_CUDA=on"`)
- [x] T091 Verify: run `kris query`, confirm GPU compute visible in `nvtop`
- [x] CT011 Run `just check`, commit Phase 11: "perf(001): GPU LLM inference for query pipeline"

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — first deliverable vertical slice
- **US2 (Phase 4)**: Depends on Phase 2 + US1 (needs indexed content to query)
- **US3 (Phase 5)**: Depends on Phase 2 — can run in parallel with US1 (but logically extends scanner/config)
- **US4 (Phase 6)**: Depends on Phase 2 — can run in parallel with US1
- **US5 (Phase 7)**: Depends on Phase 2 + US1 (needs index pipeline to verify dedup)
- **US6 (Phase 8)**: Depends on Phase 2 + US1 (needs index pipeline to test archive flow)
- **Polish (Phase 9)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: Depends only on Foundational — no other story dependencies
- **US2 (P1)**: Depends on US1 (needs embedded content to query against)
- **US3 (P2)**: Independent of other stories — extends config and scanner
- **US4 (P2)**: Independent of other stories — reads from catalog
- **US5 (P3)**: Verifies dedup behavior in US1 — shares no implementation but needs index pipeline
- **US6 (P3)**: Extends scanner (archive) and catalog (cleanup) — needs index pipeline for testing

### Within Each User Story

- Tests MUST be written and FAIL before implementation (TDD)
- Rust scanner tasks before Python processing tasks (US1)
- Models/catalog before services
- Services before CLI commands
- Core implementation before integration

### Parallel Opportunities

- Phase 1: T003, T004, T005, T006 can all run in parallel
- Phase 2: T011, T013, T014 can run in parallel after T008-T010; T016, T017, T018 can run in parallel
- US1: All test tasks (T021-T025) in parallel; Rust tasks T027, T028 in parallel; processing tasks T034-T039 have some parallelism
- US2: All test tasks (T043-T045) in parallel
- US3-US6: Each story's test tasks can run in parallel
- US3, US4 can run in parallel with each other (and with US1 if staffed)

---

## Parallel Example: User Story 1

```bash
# Launch all US1 test tasks together (TDD: write failing tests first):
Task T021: Rust scanner tests in scanner/src/tests/
Task T022: Text extraction tests in tests/unit/test_extract.py
Task T023: Chunking tests in tests/unit/test_chunk.py
Task T024: Planner tests in tests/unit/test_planner.py
Task T025: Integration test in tests/integration/test_index_flow.py

# Then launch parallelizable Rust tasks:
Task T027: FileKind classifier in scanner/src/classify.rs
Task T028: SHA-256 hasher in scanner/src/hash.rs

# Then sequential Rust tasks:
Task T026: Directory walker (depends on T027, T028 concepts)
Task T029: Catalog writes (depends on T026)
Task T030: Scanner main (depends on all above)
Task T031: Scanner integration test
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: US1 — Scan and Index
4. **STOP and VALIDATE**: Verify files are cataloged, chunks exist, Qdrant has vectors
5. Complete Phase 4: US2 — Query
6. **STOP and VALIDATE**: Verify query returns answers with citations
7. This is the MVP vertical slice: index → query

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 (Scan/Index) → First data in the system (MVP start)
3. US2 (Query) → First user-facing value (MVP complete)
4. US3 (Config) → Multi-source, richer configuration
5. US4 (Status) → Observability
6. US5 (Dedup) → Storage efficiency, duplicate detection
7. US6 (Archive/Cleanup) → Data lifecycle management
8. Polish → Documentation, logging, final QA

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- TDD: verify tests fail before implementing (constitution Principle III)
- CT tasks run pre-commit checks and commit at end of each phase (provides revert points and work log)
- Additional commits within a phase are fine for logical sub-groups
- Stop at any checkpoint to validate story independently
- Rust scanner and Python core share SQLite as IPC — no other coupling
- Performance benchmarks should be recorded and reviewed with user before attempting optimization
