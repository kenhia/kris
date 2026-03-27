# Feature Specification: Production Hardening

**Feature Branch**: `002-production-hardening`
**Created**: 2026-03-25
**Status**: Draft
**Input**: Make the existing pipeline robust at real scale (745K+ files, 100K+ embeddings) before adding new capabilities. Address backlog items B002, B003, B004, B008, B010, B011.

## User Scenarios & Testing

### User Story 1 — Clean First Scan (Priority: P1)

As a user, I want my first scan of a development directory to exclude common build artifacts, caches, and virtual environments by default so that the pipeline focuses on meaningful content and avoids hundreds of encoding failures on binary files.

**Why this priority**: First-run experience defines whether the system feels usable. Currently, scanning a dev directory produces hundreds of spurious failures on `.ruff_cache`, `__pycache__`, `node_modules`, etc. This is the highest-impact quality-of-life improvement.

**Independent Test**: Configure a source pointing at a directory containing Python, Node.js, and Rust projects. Run `kris-scanner`. Verify that default-excluded directories are not traversed and do not appear in the catalog.

**Acceptance Scenarios**:

1. **Given** a fresh config with a source pointing at `~/src/`, **When** the scanner runs, **Then** files under `.git`, `node_modules`, `__pycache__`, `target/`, `.venv`, and other default-excluded directories are not cataloged.
2. **Given** a source with `include_default_exclude_patterns = false`, **When** the scanner runs, **Then** only the source's own `exclude_patterns` are applied and default excludes are ignored.
3. **Given** a source with additional `exclude_patterns` beyond the defaults, **When** the scanner runs, **Then** both the defaults and the source-specific patterns are merged (union) and applied.

---

### User Story 2 — Failure Diagnostics (Priority: P1)

As a user who has completed an indexing run, I want to see a summary of which file types and path patterns caused processing failures so I can refine my exclude patterns and understand what the system cannot process.

**Why this priority**: Tightly coupled with US1 — default excludes prevent the common failures, but this story provides the feedback loop for discovering site-specific exclusion needs.

**Independent Test**: After indexing a heterogeneous directory, run the diagnostic command and verify it groups failures by extension and shows actionable patterns.

**Acceptance Scenarios**:

1. **Given** an indexing run with failures on binary/image files, **When** the user runs `kris diagnose`, **Then** failures are grouped by file extension with counts, sorted by frequency.
2. **Given** failures across multiple path prefixes, **When** the diagnostic is run, **Then** common path prefixes are identified as suggested exclude candidates.
3. **Given** files with `file_kind` of `image`, `binary`, or `unknown`, **When** the planner creates tasks, **Then** extract tasks are not queued for these file kinds (they are marked `skipped` rather than `failed`).

---

### User Story 3 — Qdrant Server Migration (Priority: P1)

As a user whose index has grown beyond 20K embedded chunks, I want the system to use Qdrant in server mode so that vector search remains performant at scale and I no longer see local-mode warnings.

**Why this priority**: The current embedded Qdrant mode is not recommended for the projected scale (100K+ points). This is a scalability gate — if not addressed, query latency will degrade as the index grows.

**Independent Test**: Start kris with Qdrant server mode configured, run a query, and verify results are returned correctly. Benchmark latency at 20K and 50K+ points.

**Acceptance Scenarios**:

1. **Given** Qdrant is configured in server mode, **When** `kris index` runs, **Then** embeddings are stored in the Qdrant server instance.
2. **Given** Qdrant server mode, **When** `kris query` runs, **Then** semantic search results are returned with equivalent or better latency compared to local mode.
3. **Given** no Qdrant server running, **When** kris starts, **Then** a clear error message indicates the Qdrant server is unreachable.
4. **Given** embedded mode is still configured (e.g., for testing), **When** kris runs, **Then** embedded mode continues to work as before.

---

### User Story 4 — VRAM Auto-Calibration (Priority: P2)

As a user, I want to run a command that measures actual VRAM consumption for each configured model and updates my config automatically, removing guesswork from GPU resource planning.

**Why this priority**: Accurate VRAM sizing enables the model manager to make correct hot-swap vs. simultaneous-loading decisions. Important but not blocking — the system works with approximate values.

**Independent Test**: Run `kris config update-model-sizes`, verify it loads each model, measures VRAM, and updates `config.toml` with accurate values.

**Acceptance Scenarios**:

1. **Given** models configured in `config.toml` with estimated `vram_gb` values, **When** `kris config update-model-sizes` runs, **Then** each model is loaded, measured, and the config is updated with measured values.
2. **Given** `--dry-run` is specified, **When** the command runs, **Then** measured sizes are reported but the config file is not modified.
3. **Given** no GPU is available, **When** the command runs, **Then** a warning is displayed and the command exits without modifying config.

---

### User Story 5 — Quiet Logs and Status (Priority: P2)

As a user running an indexing or query session, I want log output to show meaningful progress summaries rather than per-file noise, and I want `kris status` to show a clean summary without overwhelming me with hundreds of failed file entries.

**Why this priority**: Quality-of-life improvement for daily use. Noisy logs and status output make it hard to spot real issues.

**Independent Test**: Run `kris index` on a large source, verify that INFO-level logs show periodic batch summaries. Run `kris status` and verify failed files are hidden by default.

**Acceptance Scenarios**:

1. **Given** an indexing run processing thousands of files, **When** running at INFO log level, **Then** per-file chunk/embed messages appear at DEBUG level only, and a batch summary appears every ~3,000 items processed.
2. **Given** indexing completes, **Then** a final summary line reports total chunks created and embedded.
3. **Given** `kris status` is run with failures in the catalog, **When** `--show-failed` is not specified, **Then** only a one-line count of failed files is shown.
4. **Given** `kris status --show-failed` is run, **Then** the full failed-files table is displayed as before.
5. **Given** `kris status --json` is run, **Then** the `failed_files` array is always included regardless of `--show-failed`.

---

### Edge Cases

- What happens when a user has no `exclude_patterns` configured at all? Default excludes still apply (unless explicitly opted out).
- What happens when Qdrant server is unreachable during indexing? Embedding tasks fail with clear error; already-cataloged files are unaffected.
- What happens when VRAM measurement loads a model that exceeds available GPU memory? The command catches the OOM error, reports the model as too large, and continues with remaining models.
- What happens when `config.toml` has comments? The VRAM update command preserves all comments and formatting (uses tomlkit or equivalent).

## Requirements

### Functional Requirements

- **FR-001**: The system MUST provide a built-in set of default exclude patterns covering common build artifacts, caches, and virtual environments.
- **FR-002**: Default exclude patterns MUST be merged with per-source `exclude_patterns` (union) before scanning.
- **FR-003**: Each source MUST support an `include_default_exclude_patterns` field (default: `true`) that allows opting out of defaults.
- **FR-004**: The planner MUST NOT queue `extract` tasks for files with `file_kind` of `image`, `binary`, `archive`, `audio`, `video`, or `unknown`.
- **FR-005**: Files skipped due to incompatible file kind MUST be marked with a distinct status (not `failed`).
- **FR-006**: The system MUST provide a `kris diagnose` command that aggregates processing failures by file extension and path prefix.
- **FR-007**: The system MUST support Qdrant in server mode (HTTP connection to a Qdrant instance) as an alternative to embedded/local mode.
- **FR-008**: The Qdrant backend mode MUST be configurable (embedded or server with connection URL).
- **FR-009**: The system MUST provide a `kris config update-model-sizes` command that measures and records actual VRAM consumption per model.
- **FR-010**: The VRAM measurement command MUST support `--dry-run` to report without modifying config.
- **FR-011**: Per-file processing log messages MUST be at DEBUG level; batch summaries at INFO level.
- **FR-012**: `kris status` MUST hide the failed-files table by default, showing only a count with a hint to use `--show-failed`.
- **FR-013**: `kris status --json` MUST always include the `failed_files` array.

### Key Entities

- **Default Exclude Patterns**: A built-in list of glob patterns for directories/files universally unwanted in indexing. Defined in code, overridable via config.
- **Processing Diagnostic**: An aggregated view of processing failures grouped by file extension and path prefix, surfaced via CLI.
- **Qdrant Backend Configuration**: Connection settings for Qdrant — mode (embedded/server), URL, API key (optional), collection naming.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A first-time scan of `~/src/` (containing Python, Node.js, and Rust projects) produces zero failures from default-excluded directories.
- **SC-002**: `kris diagnose` correctly identifies the top 5 file extensions causing failures and suggests actionable exclude patterns.
- **SC-003**: Query latency with Qdrant server mode at 50K+ points is equal to or better than embedded mode at 20K points.
- **SC-004**: `kris config update-model-sizes` measures VRAM within 10% of `nvtop`-observed values.
- **SC-005**: INFO-level log output during a 10K-file indexing run is reduced by at least 90% compared to current behavior.
- **SC-006**: `kris status` default output fits in a single terminal screen (< 40 lines) even with hundreds of failures in the catalog.

## Assumptions

- Qdrant server will be run via Docker on the same machine (localhost). Remote Qdrant deployments are out of scope.
- The `tomlkit` library (or equivalent) is available for comment-preserving TOML updates.
- The Rust scanner can receive the merged exclude-pattern list from the Python CLI via the existing SQLite-based IPC or command-line arguments.
- Backward compatibility: existing configs without the new fields continue to work with sensible defaults.
