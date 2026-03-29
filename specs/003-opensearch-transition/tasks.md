# Tasks: OpenSearch Transition

**Input**: Design documents from `/specs/003-opensearch-transition/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli.md, quickstart.md

**Tests**: Included — constitution mandates TDD (Principle III), spec requires FR-029 (unit tests) and FR-030 (integration tests).

**Organization**: Tasks grouped by user story. 6 user stories from spec.md (US1–US6), organized in priority order (P1 → P2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup

**Purpose**: Dependency swap and environment preparation

- [x] T001 Replace `qdrant-client>=1.14` with `opensearch-py>=3.0` in pyproject.toml
- [x] T002 Install updated dependencies in virtual environment and verify `import opensearchpy` succeeds

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data model, config schema, client factory, and test infrastructure that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 [P] Replace QdrantConfig with OpenSearchConfig dataclass (url, username, password, verify_certs, index_prefix) in src/kris/config/schema.py — remove `qdrant_path` property from KrisConfig, add `opensearch_index` property returning `f"{opensearch.index_prefix}_chunks"`
- [x] T004 [P] Update default config TOML template — replace `[qdrant]` section with `[opensearch]` section (url, username, password, verify_certs, index_prefix) in src/kris/config/defaults.py
- [x] T005 [P] Rename `Embedding.qdrant_point_id` → `opensearch_doc_id` and `collection_name` → `index_name` in src/kris/catalog/models.py
- [x] T006 [P] Add idempotent SQLite schema migration — `ALTER TABLE embedding RENAME COLUMN qdrant_point_id TO opensearch_doc_id` and `collection_name TO index_name` — in src/kris/catalog/db.py
- [x] T007 Implement `create_opensearch_client()` factory function in src/kris/processing/embed.py — create OpenSearch connection from config with HTTPS, auth, verify_certs, error handling for connection refused (R3, R9)
- [x] T008 Implement `ensure_index()` in src/kris/processing/embed.py — create `kris_chunks` index with k-NN mapping (768-dim Lucene HNSW cosinesimil, text content field, keyword metadata fields) if it does not exist; if index exists, verify mapping dimensions match config and raise actionable error on mismatch (R4, R5)
- [x] T009 [P] Add OpenSearch mock fixtures (mock client, mock index responses) in tests/conftest.py

**Checkpoint**: Foundation ready — OpenSearchConfig exists, client factory works, SQLite schema migrated, test fixtures available. User story implementation can begin.

---

## Phase 3: US3 — Configure OpenSearch Connection (Priority: P1)

**Goal**: Users can configure kris to connect to their OpenSearch instance via config.toml, validate the connection, and receive guidance when legacy Qdrant config is detected.

**Independent Test**: Run `kris init`, verify generated config contains `[opensearch]` section. Edit URL, run `kris config validate`, verify connection status is reported.

### Tests for US3

- [x] T010 [US3] Write unit tests for OpenSearchConfig parsing, env var fallback (KRIS_OPENSEARCH_PASSWORD), and create_opensearch_client() in tests/unit/test_config.py — replace TestQdrantConfig and TestCreateQdrantClient

### Implementation for US3

- [x] T011 [P] [US3] Update `kris init` to generate config with `[opensearch]` section (url, username, password, verify_certs, index_prefix) in src/kris/cli/config_cmd.py
- [x] T012 [P] [US3] Add OpenSearch connectivity check to `kris config validate` — GET cluster health, report version/status/index in Rich table, handle connection refused and auth failure per contracts/cli.md in src/kris/cli/config_cmd.py
- [x] T013 [US3] Add legacy `[qdrant]` config section detection — warn if present alongside `[opensearch]`, error if `[qdrant]` only — in src/kris/config/schema.py

**Checkpoint**: `kris init` generates correct config. `kris config validate` reports OpenSearch connection health. Legacy config triggers warning.

---

## Phase 4: US1 — Index Files into OpenSearch (Priority: P1) 🎯 MVP

**Goal**: `kris index` scans, extracts, chunks, embeds, and stores documents in OpenSearch with both vector embeddings and chunk text content.

**Independent Test**: Configure a source directory with text/code/markdown files. Run `kris index`. Verify OpenSearch contains documents with embedding vectors and text content. Verify SQLite embedding records reference OpenSearch document IDs.

### Tests for US1

- [x] T014 [US1] Write unit tests for OpenSearch bulk indexing and document deletion in tests/unit/test_worker_logging.py — mock opensearch-py helpers.bulk(), verify document structure includes embedding + content + metadata fields

### Implementation for US1

- [x] T015 [US1] Replace `embed_chunks()` Qdrant upsert with OpenSearch `helpers.bulk()` indexing (500-doc batches, UUID doc IDs, content + embedding + metadata per R5/R6) in src/kris/processing/embed.py
- [x] T016 [US1] Replace `delete_points()` Qdrant call with OpenSearch `delete()` by document ID in src/kris/processing/embed.py
- [x] T017 [US1] Update worker to pass OpenSearch config instead of qdrant_path in src/kris/processing/worker.py
- [x] T018 [US1] Update CLI index command to pass OpenSearch config to worker in src/kris/cli/index.py
- [x] T019 [US1] Write integration test for full index flow (scan → extract → chunk → embed → OpenSearch) in tests/integration/test_index_flow.py

**Checkpoint**: `kris index` writes documents to OpenSearch. SQLite embedding records have `opensearch_doc_id` and `index_name`. Incremental re-indexing works (no duplicates on repeat run).

---

## Phase 5: US2 — Query Files via OpenSearch (Priority: P1)

**Goal**: `kris query` and `kris retrieve` search OpenSearch via k-NN vector similarity with pre-filtering by source and file kind.

**Independent Test**: After indexing content, run `kris query "test question"`. Verify relevant chunks are retrieved via k-NN search, enriched with metadata, and synthesized into an answer. Verify `--source` and `--kind` filters work as pre-filters.

### Tests for US2

- [x] T020 [US2] Write unit tests for OpenSearch k-NN retrieval with pre-filtering (source_id, file_kind) in tests/unit/test_retriever.py — mock OpenSearch search response, verify query DSL uses k-NN with filter clause

### Implementation for US2

- [x] T021 [US2] Replace Qdrant `query_points()` with OpenSearch k-NN search in src/kris/query/retriever.py — implement pre-filtered ANN query with `filter` clause for source_id/file_kind, return scored results with chunk text, file path, kind, source, and score (FR-013, FR-014, FR-016)
- [x] T022 [US2] Update query engine to pass OpenSearch config instead of qdrant_path in src/kris/query/engine.py
- [x] T023 [US2] Update CLI query and retrieve commands to pass OpenSearch config in src/kris/cli/query.py
- [x] T024 [US2] Write integration test for query flow (index → query with filters → verify results) in tests/integration/test_query_flow.py

**Checkpoint**: `kris query` returns LLM-synthesized answers with citations. `kris retrieve` returns raw scored chunks. Pre-filtering by `--source` and `--kind` applies before vector search.

---

## Phase 6: US4 — Clean Up Indexed Content (Priority: P2)

**Goal**: `kris cleanup` removes OpenSearch documents for deleted or archived files, instead of Qdrant points.

**Independent Test**: Index files, delete source files, run `kris index` to mark missing, run `kris cleanup --missing --confirm`. Verify OpenSearch documents removed and SQLite embedding records cleaned up.

### Tests for US4

- [x] T025 [US4] Write unit tests for OpenSearch document deletion during cleanup in tests/unit/test_cleanup.py — mock OpenSearch delete, verify correct doc IDs targeted

### Implementation for US4

- [x] T026 [US4] Update cleanup command to delete from OpenSearch instead of Qdrant — change preview label "Qdrant points" → "Search documents" per contracts/cli.md in src/kris/cli/cleanup.py

**Checkpoint**: `kris cleanup --missing --confirm` removes OpenSearch documents. Preview shows "Search documents" count. Selectors (path, source, age) filter correctly.

---

## Phase 7: US5 — Diagnose System Health Including OpenSearch (Priority: P2)

**Goal**: `kris diagnose` reports OpenSearch cluster health, index statistics, and connectivity status.

**Independent Test**: Run `kris diagnose` with OpenSearch running — verify output includes cluster health, index name, doc count, store size. Run with OpenSearch stopped — verify clear connectivity error.

### Tests for US5

- [x] T027 [US5] Write unit tests for OpenSearch health reporting in tests/unit/test_diagnose.py — mock cluster health and index stats responses

### Implementation for US5

- [x] T028 [US5] Add OpenSearch health section to diagnose command (cluster name, status, index name, doc count, store size in Rich table) in src/kris/cli/diagnose.py — handle connection failure with actionable message per contracts/cli.md
- [x] T029 [US5] Update status command to remain functional with new backend (no Qdrant references) in src/kris/cli/status.py and tests/unit/test_status.py

**Checkpoint**: `kris diagnose` shows OpenSearch health section. `kris status` works without Qdrant dependency.

---

## Phase 8: US6 — Data Migration from Qdrant to OpenSearch (Priority: P2)

**Goal**: Existing users with Qdrant-indexed content can migrate to OpenSearch via documented re-index procedure.

**Independent Test**: Follow documented migration procedure on a kris installation with existing Qdrant data. Verify all content is re-indexed into OpenSearch and queries return equivalent results.

- [x] T030 [US6] Document migration procedure (update config, run `kris index` to re-embed) in docs/setup.md — include prerequisites, step-by-step, and verification commands
- [x] T031 [US6] Update docs/usage.md with new OpenSearch configuration examples and CLI behavior changes

**Checkpoint**: Migration documentation complete. User can follow steps to transition from Qdrant to OpenSearch.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Documentation updates, cleanup of all Qdrant remnants, final validation

- [x] T032 [P] Update docs/architecture.md to reflect OpenSearch backend replacing Qdrant — update component diagram, data flow, and technology references; record Qdrant→OpenSearch decision in docs/clarifications-needed.md
- [x] T033 [P] Update docs/data-model.md to reflect OpenSearch entities and updated EMBEDDING table schema
- [x] T034 Verify no Qdrant imports, references, or dead code remain in codebase — grep for `qdrant`, `Qdrant`, `QdrantConfig`, `qdrant_client` across all source and test files (SC-006)
- [x] T035 Run pre-commit checks: `ruff format --check`, `ruff check`, `ty check`, `pytest -q` — all must pass clean
- [x] T036 Update docs/specification.md to reflect OpenSearch backend transition (Constitution Principle I)
- [x] T037 Run quickstart.md validation — follow steps in specs/003-opensearch-transition/quickstart.md end-to-end to verify complete workflow

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **US3 Configure (Phase 3)**: Depends on Foundational (T003, T004 specifically)
- **US1 Index (Phase 4)**: Depends on Foundational (T007, T008 for client/index) — MVP target
- **US2 Query (Phase 5)**: Depends on US1 (needs indexed content to query)
- **US4 Cleanup (Phase 6)**: Depends on US1 (needs content to clean up)
- **US5 Diagnose (Phase 7)**: Depends on Foundational (T007 for client) — independent of US1/US2
- **US6 Migration (Phase 8)**: Depends on US1 (migration = re-indexing)
- **Polish (Phase 9)**: Depends on all user stories being complete

### User Story Dependencies

```
Phase 1 (Setup)
    │
Phase 2 (Foundational)
    │
    ├── Phase 3 (US3 Configure) ─────────────────────┐
    ├── Phase 4 (US1 Index) 🎯 MVP                   │
    │       │                                         │
    │       ├── Phase 5 (US2 Query)                   │
    │       ├── Phase 6 (US4 Cleanup)                 │
    │       └── Phase 8 (US6 Migration)               │
    │                                                 │
    └── Phase 7 (US5 Diagnose)                        │
                                                      │
Phase 9 (Polish) ◄────────────────────────────────────┘
```

### Within Each User Story

- Tests MUST be written and FAIL before implementation (TDD — Red-Green-Refactor)
- Config/model changes before service logic
- Service logic before CLI wiring
- Unit tests before integration tests
- Commit after each task or logical group

### Parallel Opportunities

**Phase 2** (4 parallel tasks):
- T003, T004, T005, T006 can all run in parallel (different files, no dependencies)

**Phase 3** (2 parallel tasks):
- T011, T012 can run in parallel after T010 (different CLI commands, same file but no conflicts)

**Phase 4** (2 parallel tasks):
- T017, T018 can run in parallel after T015/T016 (different files)

**Phase 5** (2 parallel tasks):
- T022, T023 can run in parallel after T021 (different files)

**Phase 9** (2 parallel tasks):
- T032, T033 can run in parallel (different doc files)

---

## Parallel Example: Foundational Phase

```
# Launch all independent foundational tasks together:
T003: "Replace QdrantConfig with OpenSearchConfig in src/kris/config/schema.py"
T004: "Update default config TOML in src/kris/config/defaults.py"
T005: "Rename Embedding fields in src/kris/catalog/models.py"
T006: "Add SQLite schema migration in src/kris/catalog/db.py"

# Then sequentially (depend on T003/T004):
T007: "Implement create_opensearch_client() in src/kris/processing/embed.py"
T008: "Implement ensure_index() in src/kris/processing/embed.py"

# Independent of T007/T008:
T009: "Add OpenSearch mock fixtures in tests/conftest.py"
```

---

## Implementation Strategy

### MVP First (US1 Index Only)

1. Complete Phase 1: Setup (dependency swap)
2. Complete Phase 2: Foundational (config, models, client, migration, fixtures)
3. Complete Phase 4: US1 Index (embed pipeline → OpenSearch)
4. **STOP and VALIDATE**: Run `kris index`, verify documents in OpenSearch
5. This is the minimum viable product — indexing works with OpenSearch

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US3 Configure → Config commands work, validate connection
3. **US1 Index → MVP! Indexing into OpenSearch works**
4. US2 Query → Full search pipeline operational (index + query)
5. US4 Cleanup → Maintenance operations work
6. US5 Diagnose → Operational health visibility
7. US6 Migration → Documentation for existing users
8. Polish → Docs updated, Qdrant fully removed, all checks pass

### Files Modified Per Story

| Story | Files | Test Files |
|-------|-------|------------|
| Foundational | schema.py, defaults.py, models.py, db.py, embed.py | conftest.py |
| US3 | config_cmd.py, schema.py | test_config.py |
| US1 | embed.py, worker.py, cli/index.py | test_worker_logging.py, test_index_flow.py |
| US2 | retriever.py, engine.py, cli/query.py | test_retriever.py, test_query_flow.py |
| US4 | cli/cleanup.py | test_cleanup.py |
| US5 | cli/diagnose.py, cli/status.py | test_diagnose.py, test_status.py |
| US6 | docs/setup.md, docs/usage.md | — |
| Polish | docs/architecture.md, docs/data-model.md | — |

---

## Notes

- All paths relative to repository root `/home/ken/src/kris/`
- OpenSearch deployment is external at `/home/ken/opensearch/` — kris connects, does not manage
- Integration tests (T019, T024) require running OpenSearch instance
- TDD approach: write test → verify it fails → implement → verify it passes → refactor
- Commit after each completed task or logical group of tasks
- Stop at any checkpoint to validate the story independently
