# Research: Production Hardening

**Feature**: 002-production-hardening
**Date**: 2026-03-25

---

## R1: Exclude Pattern Matching Strategy

**Decision**: Extend the Rust scanner's `is_excluded()` to support glob patterns via the `globset` crate, in addition to the existing exact-name matching.

**Rationale**: The current scanner only matches directory/file names exactly (`name == pattern`). This handles `.git` and `node_modules` but cannot match patterns like `*.pyc`, `*.pyo`, or path-based patterns. Users expect glob semantics from exclude patterns (consistent with `.gitignore` conventions). The `globset` crate provides compiled, fast glob matching with `*`, `**`, `?`, `[...]` support and is widely used in the Rust ecosystem (same lib underpins `ripgrep`).

**Alternatives considered**:
- **Regex**: More powerful but harder for users to write exclude patterns. Glob is the convention.
- **Keep exact-name-only**: Would require enumerating every directory name variant. `*.pyc` pattern impossible.
- **Path-based patterns only**: Would break existing exact-name excludes. Glob subsumes both.

**Implementation notes**:
- Build a `GlobSet` once per scan from the merged exclude list
- Match against both the entry name (for directory names like `.git`) and the relative path from source root (for patterns like `**/build/Release`)
- Existing exact-name matches continue to work as-is since `globset` treats patterns without wildcards as exact matches

---

## R2: Default Exclude Patterns — Which Patterns to Include

**Decision**: Ship a built-in set of ~25 patterns covering Python, Node.js, Rust, C/C++, Java, .NET, Go, and general VCS/IDE directories. Define in Python (`config/defaults.py`) and pass to the scanner alongside per-source patterns.

**Rationale**: Surveyed common `.gitignore` templates from github/gitignore. The goal is to exclude directories that are: (a) generated/cached, (b) contain no user-authored content, and (c) cause encoding failures when processed. Conservative set — users can always opt out per-source.

**Default set** (directory names and globs):
```
# VCS
.git, .hg, .svn

# Python
__pycache__, .venv, .tox, .nox, .mypy_cache, .pytest_cache, .ruff_cache, htmlcov, *.pyc, *.pyo

# Node.js
node_modules, .next, .svelte-kit, .nuxt

# Rust
target

# Build artifacts
build, dist, out

# IDE/Editor
.idea, .vscode, .vs

# Coverage
.coverage, coverage
```

**Alternatives considered**:
- **Larger set** (include `.DS_Store`, `Thumbs.db`, etc.): These are files, not directories, and are handled gracefully by the pipeline. Keep the default set focused on directories that cause noise.
- **No defaults, rely on per-source**: Poor first-run experience was the original motivation (B003).

---

## R3: Qdrant Server Mode — Connection Strategy

**Decision**: Support both embedded and server modes via a Qdrant configuration section in `config.toml`. Default remains embedded for simple installs and tests. Server mode uses HTTP connection to a running Qdrant instance.

**Rationale**: Qdrant's Python client supports both modes through the same `QdrantClient` API:
- Embedded: `QdrantClient(path=str(qdrant_path))`
- Server: `QdrantClient(url="http://localhost:6333")`

The switch is a client construction change — all subsequent operations (upsert, query, delete) use the same API. This makes the migration straightforward.

**Alternatives considered**:
- **gRPC connection**: Qdrant supports gRPC (port 6334) for potentially higher throughput. However, HTTP is simpler, easier to debug, and sufficient for single-user local operation.
- **Qdrant Cloud**: Out of scope — kris is local-first.
- **Drop embedded entirely**: Embedded mode is valuable for testing and small installs. Keep both.

**Docker setup**: Qdrant Docker image (`qdrant/qdrant`) runs on `localhost:6333` (HTTP) / `6334` (gRPC). Storage volume mounted at `/qdrant/storage`. A `docker-compose.yml` snippet will be provided in setup docs.

**Data migration**: Existing embedded data can be migrated by:
1. Start Qdrant server
2. Read all points from embedded client, write to server client
3. Or: simply re-index (the catalog and SQLite chunks are the source of truth; Qdrant is a derived index)

---

## R4: VRAM Measurement Approach

**Decision**: Use `torch.cuda.memory_allocated()` delta for PyTorch models (sentence-transformers) and parse llama.cpp's VRAM reporting for GGUF models. Write config updates using `tomlkit` to preserve comments and formatting.

**Rationale**: 
- **PyTorch models**: `torch.cuda.memory_allocated()` accurately reports tensor memory on the device. Take a before/after measurement around model load.
- **llama.cpp models**: The library logs buffer sizes during load. With `verbose=True` temporarily, capture the `CUDA0 model buffer size` line. Alternatively, use the `torch.cuda` delta approach since llama-cpp-python allocates through CUDA.
- **tomlkit**: Unlike `tomllib` (read-only) or `tomli_w` (loses comments), `tomlkit` round-trips TOML with comment preservation. Already compatible with the project's TOML config approach.

**Alternatives considered**:
- **nvidia-smi parsing**: External process, less accurate for per-model measurement, timing-dependent.
- **pynvml**: Direct NVML bindings — more accurate but adds a dependency. `torch.cuda` is already available.

---

## R5: Planner File-Kind Skip Logic

**Decision**: Add file-kind checks to the planner's `plan_tasks_for_content()` function. Files with non-extractable kinds (`image`, `binary`, `archive`, `audio`, `video`, `unknown`) get their content status set to `skipped` instead of generating extract/chunk/embed tasks. A new status value `skipped` is added alongside `pending`, `processing`, `completed`, `failed`.

**Rationale**: Currently the planner queues extract tasks for all pending content regardless of file kind. Binary files then fail during extraction with encoding errors, consuming retries and producing noisy `failed` status entries. The scanner already classifies file kinds accurately — the planner should respect this classification.

**Alternatives considered**:
- **Skip in worker**: Would still create task records, consume queue capacity, and require retries before giving up. Wasteful.
- **New task type `skip`**: Overcomplicates the task model. The planner simply not creating tasks and marking content `skipped` is the simplest approach.

**Impact on diagnostics**: Files with `processing_status='skipped'` should be distinguishable from `failed` in status/diagnostic output. The `kris diagnose` command will report skipped vs. failed separately.

---

## R6: Diagnostic Aggregation Approach

**Decision**: Implement `kris diagnose` as a SQL-driven aggregation over the file and task tables, grouping by file extension and path prefix. No new tables needed — existing data is sufficient.

**Rationale**: The catalog already stores `path`, `file_kind`, and each task's `error` text. Aggregation queries can:
1. Group failed files by extension: `SELECT substr(path, instr(path, '.')) as ext, COUNT(*) FROM file WHERE processing_status='failed' GROUP BY ext ORDER BY COUNT(*) DESC`
2. Group by path prefix (first 2-3 directory components): useful for identifying entire directories that should be excluded
3. Show skipped vs. failed breakdown

**Alternatives considered**:
- **Dedicated `failure_log` table**: Adds write overhead during processing. The existing task.error + file metadata is sufficient.
- **File-system-level analysis**: Would require re-reading files. SQL aggregation is instant.

---

## R7: Log Batching Constants

**Decision**: Use a configurable constant `LOG_BATCH_INTERVAL = 3000` for periodic INFO summaries. Demote per-file messages to DEBUG. Emit a final summary at worker completion.

**Rationale**: A 3,000-item interval produces ~3-7 INFO lines for a typical source scan (10K-20K processable files). Frequent enough to show progress, rare enough to not overwhelm. The constant is defined in the worker module, not in config — this is an implementation detail, not a user-facing setting.

**Pattern**:
```
DEBUG  Created 3 chunks for 8c92515a14
DEBUG  Embedded 3 chunks for 8c92515a14
...
INFO   Processed 3,000 items (1,247 chunks created, 1,247 chunks embedded)
...
INFO   Indexing complete: 10,432 items processed (4,891 chunks created, 4,891 chunks embedded)
```
