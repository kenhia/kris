# Tasks: Production Hardening

**Input**: Design documents from `/specs/002-production-hardening/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli.md, quickstart.md

**Tests**: Included — constitution mandates TDD (Red-Green-Refactor).

**Organization**: Tasks grouped by user story. All five user stories are independent after the foundational phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add new dependencies and shared utilities needed across multiple stories.

- [x] T001 Add `globset` dependency to scanner/Cargo.toml
- [x] T002 [P] Add `tomlkit` dependency to pyproject.toml
- [x] T003 [P] Define `DEFAULT_EXCLUDE_PATTERNS` constant list in src/kris/config/defaults.py
- [x] T004 [P] Add `QdrantConfig` dataclass (mode, url, api_key) to src/kris/config/schema.py
- [x] T005 Add `default_exclude_patterns` field and `include_default_exclude_patterns` to `SourceConfig` in src/kris/config/schema.py
- [x] T006 Add `qdrant` field (`QdrantConfig`) to `KrisConfig` in src/kris/config/schema.py with backward-compatible defaults
- [x] T007 Implement `get_effective_excludes(config, source)` helper in src/kris/config/schema.py that merges default + source-specific patterns

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core changes that multiple user stories depend on.

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T008 Write unit test for `get_effective_excludes()` — verify merge, verify opt-out with `include_default_exclude_patterns=False` in tests/unit/test_config.py
- [x] T009 Write unit test for `QdrantConfig` defaults and validation in tests/unit/test_config.py
- [x] T010 [P] Write unit test for backward compatibility — config with no `[qdrant]` section or `default_exclude_patterns` loads with defaults in tests/unit/test_config.py
- [x] T011 Implement `create_qdrant_client(config)` factory function in src/kris/processing/embed.py — returns `QdrantClient(path=...)` for embedded, `QdrantClient(url=...)` for server mode
- [x] T012 Write unit test for `create_qdrant_client()` — verify embedded mode returns path-based client, server mode returns URL-based client in tests/unit/test_config.py
- [x] T013 Update generated default config TOML in src/kris/config/defaults.py to include `default_exclude_patterns`, `[qdrant]` section, and `include_default_exclude_patterns` per source

**Checkpoint**: Foundation ready — all config/schema changes in place, Qdrant factory available.

---

## Phase 3: User Story 1 — Clean First Scan (Priority: P1) 🎯 MVP

**Goal**: Default-excluded directories are not traversed or cataloged. Glob patterns supported.

**Independent Test**: Configure a source at a directory with Python/Node/Rust projects, run scanner, verify `.git`, `node_modules`, `__pycache__`, `target/` are absent from catalog.

### Tests for User Story 1

- [x] T014 [P] [US1] Write Rust unit test in scanner/src/walk.rs — verify `is_excluded()` matches exact names (`.git`, `node_modules`), glob patterns (`*.pyc`), and relative path patterns
- [x] T015 [P] [US1] Write Rust unit test — verify existing `.git`/`node_modules` exclusion tests still pass with new glob-based implementation
- [x] T016 [P] [US1] Write integration test in tests/integration/test_scanner.py — scan a temp directory with default excludes, verify excluded dirs not in catalog

### Implementation for User Story 1

- [x] T017 [US1] Refactor `is_excluded()` in scanner/src/walk.rs to build a `GlobSet` from patterns, match against entry name and relative path from root
- [x] T018 [US1] Update `walk_directory()` in scanner/src/walk.rs to pass the base path for relative-path matching
- [x] T019 [US1] Update `run_scanner()` in src/kris/scanner/runner.py to call `get_effective_excludes()` and pass the merged list via `--exclude` args
- [x] T020 [US1] Update `kris init` in src/kris/cli/config_cmd.py to generate config with default_exclude_patterns and include_default_exclude_patterns
- [x] T021 [US1] Update `kris config validate` to report effective excludes per source in src/kris/cli/config_cmd.py

**Checkpoint**: First scan of a dev directory excludes common artifacts automatically. SC-001 verifiable.

---

## Phase 4: User Story 2 — Failure Diagnostics (Priority: P1)

**Goal**: Users can see aggregated failure/skip data and get suggested exclude patterns.

**Independent Test**: Seed DB with known failures, run `kris diagnose`, verify grouped output.

### Tests for User Story 2

- [x] T022 [P] [US2] Write unit test for planner skip logic — non-extractable file kinds (`image`, `binary`, `archive`, `audio`, `video`, `unknown`) set content status to `skipped`, no tasks created in tests/unit/test_planner.py
- [x] T023 [P] [US2] Write unit test — extractable file kinds (`text`, `code`, `markdown`, `config`, `data`) still get 3 tasks in tests/unit/test_planner.py
- [x] T024 [P] [US2] Write unit test for `get_failed_by_extension()` SQL aggregation in tests/unit/test_diagnose.py
- [x] T025 [P] [US2] Write unit test for `get_skipped_by_kind()` SQL aggregation in tests/unit/test_diagnose.py
- [x] T026 [P] [US2] Write unit test for `get_failure_path_prefixes()` SQL aggregation in tests/unit/test_diagnose.py

### Implementation for User Story 2

- [x] T027 [US2] Define `EXTRACTABLE_KINDS` set in src/kris/planner/planner.py
- [x] T028 [US2] Add file-kind check to `plan_tasks_for_content()` in src/kris/planner/planner.py — query file_kind, set status `skipped` for non-extractable kinds
- [x] T029 [US2] Implement `get_failed_by_extension(conn, source)` in src/kris/catalog/files.py
- [x] T030 [P] [US2] Implement `get_skipped_by_kind(conn, source)` in src/kris/catalog/files.py
- [x] T031 [P] [US2] Implement `get_failure_path_prefixes(conn, min_count, source)` in src/kris/catalog/files.py
- [x] T032 [US2] Create `kris diagnose` command with Rich tables and JSON mode in src/kris/cli/diagnose.py
- [x] T033 [US2] Register `diagnose` command in src/kris/cli/app.py

**Checkpoint**: `kris diagnose` shows actionable failure breakdowns. SC-002 verifiable.

---

## Phase 5: User Story 3 — Qdrant Server Migration (Priority: P1)

**Goal**: Qdrant works in both embedded and server modes via config. Server mode handles 50K+ points.

**Independent Test**: Configure `[qdrant] mode = "server"`, start Docker Qdrant, run index + query, verify results.

### Tests for User Story 3

- [x] T034 [P] [US3] Write unit test for `create_qdrant_client()` — server mode with URL and optional api_key in tests/unit/test_config.py
- [x] T035 [P] [US3] Write unit test — server mode with unreachable URL produces actionable error message in tests/unit/test_config.py
- [x] T036 [P] [US3] Write integration test in tests/integration/test_qdrant_modes.py — embed and query cycle using embedded mode (default)

### Implementation for User Story 3

- [x] T037 [US3] Update `embed_chunks()` in src/kris/processing/embed.py to accept a `QdrantClient` instance instead of constructing one internally
- [x] T038 [US3] Update `run_worker()` in src/kris/processing/worker.py to create Qdrant client via `create_qdrant_client(config)` and pass to embed functions
- [x] T039 [US3] Update `Retriever` in src/kris/query/retriever.py to use `create_qdrant_client(config)` instead of hardcoded embedded path
- [x] T040 [US3] Add connection error handling in `create_qdrant_client()` — catch `ConnectionError`/`requests.exceptions.ConnectionError`, raise with actionable message in src/kris/processing/embed.py
- [x] T041 [US3] Add docker-compose snippet for Qdrant server to docs/setup.md

**Checkpoint**: System works with both Qdrant modes. SC-003 verifiable with Docker benchmarking.

---

## Phase 6: User Story 4 — VRAM Auto-Calibration (Priority: P2)

**Goal**: CLI command measures actual VRAM per model and updates config.toml preserving comments.

**Independent Test**: Run `kris config update-model-sizes --dry-run`, verify output table shows measured values.

### Tests for User Story 4

- [x] T042 [P] [US4] Write unit test for `measure_model_vram()` — mock `torch.cuda.memory_allocated()`, verify delta calculation in tests/unit/test_config_cmd.py
- [x] T043 [P] [US4] Write unit test for `--dry-run` — verify config file is NOT modified in tests/unit/test_config_cmd.py
- [x] T044 [P] [US4] Write unit test for no-GPU case — `torch.cuda.is_available()` returns False, command warns and exits in tests/unit/test_config_cmd.py
- [x] T045 [P] [US4] Write unit test for OOM handling — `RuntimeError` during load is caught, model reported as too large, remaining models still measured in tests/unit/test_config_cmd.py

### Implementation for User Story 4

- [x] T046 [US4] Implement `measure_model_vram(model_info)` in src/kris/models/manager.py — clear VRAM, measure delta around load, unload, return GB
- [x] T047 [US4] Implement `kris config update-model-sizes` subcommand in src/kris/cli/config_cmd.py — iterate models, measure, display Rich table
- [x] T048 [US4] Implement tomlkit config update logic in src/kris/cli/config_cmd.py — read with `tomlkit.parse()`, update `vram_gb` values, write back preserving comments
- [x] T049 [US4] Handle no-GPU case: check `torch.cuda.is_available()`, print warning, exit 0 in src/kris/cli/config_cmd.py
- [x] T050 [US4] Handle OOM: wrap model load in try/except `RuntimeError`, report model as too large, continue in src/kris/cli/config_cmd.py

**Checkpoint**: `kris config update-model-sizes` accurately measures and updates VRAM. SC-004 verifiable.

---

## Phase 7: User Story 5 — Quiet Logs and Status (Priority: P2)

**Goal**: INFO logs show batch summaries; `kris status` hides failed files by default.

**Independent Test**: Run `kris index` at INFO level, count INFO lines. Run `kris status` with failures in DB, verify one-line count.

### Tests for User Story 5

- [x] T051 [P] [US5] Write unit test for log batching — verify per-file messages are DEBUG, batch summary is INFO every LOG_BATCH_INTERVAL items in tests/unit/test_worker_logging.py
- [x] T052 [P] [US5] Write unit test for final summary log at worker completion in tests/unit/test_worker_logging.py
- [x] T053 [P] [US5] Write unit test for `kris status` default output — failed files hidden, one-line count shown in tests/unit/test_status.py
- [x] T054 [P] [US5] Write unit test for `kris status --show-failed` — full table displayed in tests/unit/test_status.py
- [x] T055 [P] [US5] Write unit test for `kris status --json` — `failed_files` array always included in tests/unit/test_status.py

### Implementation for User Story 5

- [x] T056 [US5] Define `LOG_BATCH_INTERVAL = 3000` constant in src/kris/processing/worker.py
- [x] T057 [US5] Add progress counters (`_items_processed`, `_chunks_created`, `_chunks_embedded`) to worker in src/kris/processing/worker.py
- [x] T058 [US5] Demote per-file `"Created N chunks for ..."` and `"Embedded N chunks for ..."` to `logger.debug()` in src/kris/processing/worker.py
- [x] T059 [US5] Add periodic INFO summary every `LOG_BATCH_INTERVAL` items and final summary at completion in src/kris/processing/worker.py
- [x] T060 [US5] Add `--show-failed` / `-f` `typer.Option` to `kris status` in src/kris/cli/status.py
- [x] T061 [US5] When `show_failed=False` and failures exist, print one-line count summary in src/kris/cli/status.py
- [x] T062 [US5] Ensure JSON output always includes `failed_files` regardless of `--show-failed` in src/kris/cli/status.py

**Checkpoint**: Logs are 90%+ quieter at INFO level. Status fits a single screen. SC-005 and SC-006 verifiable.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, cleanup, and validation across all stories.

- [x] T063 [P] Update docs/setup.md with Qdrant server Docker setup, default exclude pattern docs, VRAM calibration instructions
- [x] T064 [P] Update docs/usage.md with `kris diagnose`, `--show-failed`, `kris config update-model-sizes` commands
- [x] T065 [P] Update docs/specification.md with new commands and config fields
- [x] T066 Update docs/architecture.md with Qdrant server mode option in Artifact Storage section
- [x] T067 Run `ruff format --check && ruff check && ty check && pytest -q` — fix any issues
- [x] T068 Run `cd scanner && cargo fmt --check && cargo clippy --all-targets --all-features -- -D warnings && cargo test` — fix any issues
- [x] T069 Run quickstart.md validation — execute each step from specs/002-production-hardening/quickstart.md and verify behavior

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **User Stories (Phases 3–7)**: All depend on Phase 2 completion
  - **US1, US2, US3, US4, US5** are all independent — can proceed in any order or in parallel
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (Clean First Scan)**: Independent after Phase 2
- **US2 (Failure Diagnostics)**: Independent after Phase 2. Shares planner module with US1 scope but no code dependencies between them
- **US3 (Qdrant Server)**: Independent after Phase 2. Uses `create_qdrant_client()` from Phase 2
- **US4 (VRAM Calibration)**: Independent after Phase 2
- **US5 (Quiet Logs/Status)**: Independent after Phase 2

### Within Each User Story

- Tests MUST be written and FAIL before implementation (TDD)
- Implementation tasks in listed order (dependencies top-to-bottom)
- Story checkpoint before moving to next

### Parallel Opportunities

- Phase 1: T001 + T002 + T003 + T004 can run in parallel
- Phase 2: T008 + T009 + T010 can run in parallel; T012 after T011
- Phase 3–7: All five user stories can execute in parallel
- Within each story: All test tasks marked [P] run in parallel
- Phase 8: T063 + T064 + T065 run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all tests together:
Task T014: "Rust unit test for glob matching in scanner/src/walk.rs"
Task T015: "Rust unit test for backward compat in scanner/src/walk.rs"
Task T016: "Integration test for default excludes in tests/integration/test_scanner.py"

# Then implement sequentially:
Task T017: "Refactor is_excluded() with GlobSet in scanner/src/walk.rs"
Task T018: "Update walk_directory() for relative path matching"
Task T019: "Update run_scanner() to merge excludes"
Task T020: "Update kris init for new config sections"
Task T021: "Update config validate for effective excludes"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1 — Clean First Scan
4. **STOP and VALIDATE**: Scan `~/src/` with defaults, verify no artifacts from `.git`/`node_modules`/etc.
5. This alone delivers immediate value for daily use

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 (Clean First Scan) → Validate SC-001 → **MVP!**
3. US2 (Failure Diagnostics) → Validate SC-002
4. US3 (Qdrant Server) → Validate SC-003 (Docker Qdrant needed)
5. US5 (Quiet Logs/Status) → Validate SC-005, SC-006
6. US4 (VRAM Calibration) → Validate SC-004 (GPU needed)
7. Polish → Full sprint complete

### Suggested Priority Order

US1 → US2 → US3 → US5 → US4. Rationale: US1+US2 are the tightest pairing (excludes + diagnostics), US3 is the scalability gate, US5 is daily QoL, US4 can be done anytime with GPU access.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- TDD: write tests first, ensure they fail, then implement
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Total: 69 tasks (13 setup/foundational, 8 US1, 12 US2, 8 US3, 9 US4, 12 US5, 7 polish)
