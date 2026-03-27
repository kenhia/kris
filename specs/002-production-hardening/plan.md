# Implementation Plan: Production Hardening

**Branch**: `002-production-hardening` | **Date**: 2026-03-25 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-production-hardening/spec.md`

## Summary

Sprint 002 hardens the MVP pipeline for real-scale operation (745K+ files,
100K+ embeddings). Six workstreams: (A) default exclude patterns with glob
matching in the Rust scanner, (B) planner-level skip logic for
non-extractable file kinds, (C) `kris diagnose` CLI command,
(D) Qdrant server mode support, (E) VRAM auto-calibration CLI,
(F) log noise reduction and status UX. All changes are additive and
backward compatible — existing configs and data are unaffected.

## Technical Context

**Language/Version**: Rust (stable) for scanner; Python 3.12+ for core
**Primary Dependencies**: `qdrant-client`, `sentence-transformers`, `llama-cpp-python`, `typer`, `rich`, `tomlkit` (new); Rust: `walkdir`, `globset` (new), `rusqlite`, `clap`
**Storage**: SQLite (WAL mode) + Qdrant (embedded or server, configurable)
**Testing**: `pytest` (Python), `cargo test` (Rust)
**Target Platform**: Linux (x86_64), single-user local
**Project Type**: CLI tool + Rust scanner binary
**Performance Goals**: SC-001 through SC-006 (see spec)
**Constraints**: 16 GB VRAM (NVIDIA 4090 Super); backward compatible with MVP config/data
**Scale/Scope**: 745K+ files, 20K+ embeddings growing to 100K+

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-Driven Development | PASS | Spec at `specs/002-production-hardening/spec.md` — 13 FRs, 5 user stories, 6 success criteria |
| II. Architecture First | PASS | Plan aligns with `docs/architecture.md`; Qdrant config extends existing storage section; no architectural divergence |
| III. Test-Driven Development | PASS | Each phase includes test requirements; TDD Red-Green-Refactor applies |
| IV. Code Standards Gate | PASS | Python: ruff format, ruff check, ty check, pytest. Rust: cargo fmt, cargo clippy, cargo test |
| V. User Documentation | PASS | `quickstart.md` delivered; `docs/setup.md` and `docs/usage.md` updates are definition-of-done items |
| VI. Quality & Accessibility | PASS | Rich formatting, JSON output, stderr for errors, actionable error messages |
| VII. Simplicity | PASS | No new abstractions; glob via `globset`, Qdrant mode via existing client API, SQL aggregation for diagnostics |

**Post-Phase 1 re-check**: PASS — no violations introduced. Single new dependency (`tomlkit`) justified by comment-preserving TOML round-trip requirement; `globset` justified by pattern matching needs.

## Project Structure

### Documentation (this feature)

```text
specs/002-production-hardening/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0: R1–R7 decisions
├── data-model.md        # Phase 1: schema changes
├── quickstart.md        # Phase 1: user-facing guide
├── contracts/
│   └── cli.md           # Phase 1: CLI interface contract
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (files to modify/create)

```text
# Rust scanner
scanner/
├── Cargo.toml                    # Add globset dependency
└── src/
    └── walk.rs                   # Extend is_excluded() for glob matching

# Python — Config
src/kris/config/
├── schema.py                     # Add QdrantConfig, default_exclude_patterns, include_default_exclude_patterns
└── defaults.py                   # Add DEFAULT_EXCLUDE_PATTERNS constant, update generated TOML

# Python — Planner
src/kris/planner/
└── planner.py                    # Add file-kind skip logic in plan_tasks_for_content()

# Python — Processing
src/kris/processing/
├── embed.py                      # Qdrant client factory (embedded vs server)
└── worker.py                     # Log batching, DEBUG demotion

# Python — Query
src/kris/query/
└── retriever.py                  # Use same Qdrant client factory

# Python — CLI
src/kris/cli/
├── app.py                        # Register diagnose command
├── diagnose.py                   # NEW: kris diagnose command
├── config_cmd.py                 # Add update-model-sizes subcommand
├── status.py                     # Add --show-failed flag
└── index.py                      # Pass merged exclude patterns to scanner

# Python — Catalog
src/kris/catalog/
└── files.py                      # Add diagnostic aggregation queries

# Tests
tests/unit/
├── test_config.py                # Default excludes, Qdrant config, include_defaults flag
├── test_planner.py               # File-kind skip logic
├── test_diagnose.py              # NEW: diagnostic aggregation
├── test_status.py                # --show-failed behavior
└── test_worker_logging.py        # NEW: log level assertions
tests/integration/
├── test_scanner.py               # Glob pattern matching
└── test_qdrant_modes.py          # NEW: embedded vs server
```

**Structure Decision**: No new packages or modules beyond `src/kris/cli/diagnose.py`
and test files. All other changes are within existing modules. This follows
the MVP's established structure.

## Implementation Phases

### Phase A: Default Exclude Patterns (FR-001, FR-002, FR-003)

**Scope**: Config schema, defaults, scanner glob support, pattern merging.

**Workstream A1 — Rust scanner glob support**:
1. Add `globset` to `scanner/Cargo.toml`
2. Refactor `walk.rs::is_excluded()` to build a `GlobSet` from patterns
3. Match against entry name AND relative path from scan root
4. Tests: existing `.git`/`node_modules` tests still pass, new tests for `*.pyc`, `build`, path patterns

**Workstream A2 — Python config changes**:
1. Add `DEFAULT_EXCLUDE_PATTERNS` list to `config/defaults.py`
2. Add `QdrantConfig` dataclass and `default_exclude_patterns` field to `config/schema.py`
3. Add `include_default_exclude_patterns: bool = True` to `SourceConfig`
4. Implement `get_effective_excludes(source)` that merges defaults + source-specific
5. Update `defaults.py` generated TOML to include new sections
6. Update `config validate` to report effective excludes per source

**Workstream A3 — Pattern passing to scanner**:
1. In `cli/index.py` (or `scanner/runner.py`), compute effective excludes per source
2. Pass the merged list via existing `--exclude` CLI args to the Rust scanner
3. Integration test: scan a directory with default excludes active

### Phase B: Planner Skip Logic (FR-004, FR-005)

**Scope**: Planner changes, new `skipped` status.

1. Define `EXTRACTABLE_KINDS = {"text", "code", "markdown", "config", "data"}` in planner
2. In `plan_tasks_for_content()`, query file kind for the content hash
3. If file_kind not in EXTRACTABLE_KINDS: set `processing_status='skipped'`, return 0 tasks
4. Tests: verify skipped content gets no tasks, verify extractable kinds still get 3 tasks
5. Verify existing `pending → completed` flow unchanged for text/code/markdown

### Phase C: Diagnostic CLI (FR-006)

**Scope**: New `kris diagnose` command, catalog query functions.

1. Add aggregation functions to `catalog/files.py`:
   - `get_failed_by_extension(conn, source=None) → list[dict]`
   - `get_skipped_by_kind(conn, source=None) → list[dict]`
   - `get_failure_path_prefixes(conn, min_count=5, source=None) → list[dict]`
2. Create `cli/diagnose.py` with Rich table output and JSON mode
3. Register in `cli/app.py`
4. Tests: seed DB with known failures, verify aggregation output

### Phase D: Qdrant Server Mode (FR-007, FR-008)

**Scope**: Config, client factory, embed/retriever changes.

1. Add `QdrantConfig` dataclass: `mode`, `url`, `api_key`
2. Create `create_qdrant_client(config)` factory function (in `processing/embed.py` or shared util):
   - `mode="embedded"`: `QdrantClient(path=str(qdrant_path))`
   - `mode="server"`: `QdrantClient(url=config.qdrant.url, api_key=config.qdrant.api_key)`
3. Update `embed.py` to use factory instead of hardcoded path
4. Update `retriever.py` to use same factory
5. Update `worker.py` to pass config to embed functions
6. Error handling: catch connection errors in server mode, report actionable message
7. Tests: unit test factory with both modes; integration test with embedded mode; server mode tested manually (Docker dependency)

### Phase E: VRAM Auto-Calibration (FR-009, FR-010)

**Scope**: New config subcommand, tomlkit integration.

1. Add `tomlkit` to `pyproject.toml` dependencies
2. Implement `measure_model_vram(model_info) → float` in `models/manager.py`:
   - Clear VRAM, record `torch.cuda.memory_allocated()`
   - Load model
   - Record delta, unload model
   - Return delta in GB
3. Implement `kris config update-model-sizes` in `cli/config_cmd.py`:
   - Load config, iterate models
   - For each: call `measure_model_vram()`, collect results
   - If not `--dry-run`: read config file with `tomlkit`, update `vram_gb` values, write back
   - Print summary table
4. Handle no-GPU case: check `torch.cuda.is_available()`, warn and exit
5. Handle OOM: catch `RuntimeError`, report model as too large, continue
6. Tests: mock CUDA memory functions, verify config update logic, verify dry-run

### Phase F: Log Noise & Status UX (FR-011, FR-012, FR-013)

**Scope**: Worker logging, status command.

**Workstream F1 — Log batching**:
1. Define `LOG_BATCH_INTERVAL = 3000` constant in `worker.py`
2. Add counters: `_chunks_created`, `_chunks_embedded`, `_items_processed`
3. Demote per-file messages to `logger.debug()`
4. Every `LOG_BATCH_INTERVAL` items: emit `logger.info()` with running totals
5. At worker completion: emit final summary
6. Tests: capture log output, verify DEBUG vs INFO levels

**Workstream F2 — Status --show-failed**:
1. Add `show_failed: bool = typer.Option(False, "--show-failed", "-f")` to status command
2. When `show_failed=False` and failures exist: print one-line count
3. When `show_failed=True`: print full table (existing behavior)
4. JSON output unchanged (always includes `failed_files`)
5. Tests: verify default hides table, flag shows table, JSON unaffected

## Dependency Graph

```
Phase A (excludes) ──────────────┐
Phase B (planner skip) ──────────┤
Phase C (diagnose) ──────────────┤── All independent, can be
Phase D (Qdrant server) ─────────┤   developed in any order
Phase E (VRAM calibration) ──────┤
Phase F (log/status) ────────────┘
```

All six phases are independent — no ordering constraints between them.
Within each phase, the workstreams follow the order listed (config →
implementation → CLI → tests).

## Complexity Tracking

No constitution violations. No complexity justifications needed.

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| `globset` pattern semantics differ from user expectations | Medium | Document pattern syntax in `docs/usage.md`; ship conservative defaults |
| Qdrant server Docker setup friction | Low | Provide docker-compose snippet in `docs/setup.md`; embedded mode remains default |
| `tomlkit` round-trip fidelity | Low | Test with the project's actual `config.toml` including comments |
| VRAM measurement accuracy varies by model loading order | Low | Clear VRAM and empty cache before each measurement |

## Definition of Done

- [ ] All 13 functional requirements implemented and tested
- [ ] All 6 success criteria verified
- [ ] `docs/setup.md` updated with Qdrant server setup, docker-compose snippet
- [ ] `docs/usage.md` updated with `kris diagnose`, `--show-failed`, `update-model-sizes`
- [ ] `docs/specification.md` updated with new commands and config fields
- [ ] `docs/architecture.md` updated with Qdrant server mode option
- [ ] Pre-commit checks pass: `ruff format --check && ruff check && ty check && pytest -q`
- [ ] Rust checks pass: `cargo fmt --check && cargo clippy -- -D warnings && cargo test`
