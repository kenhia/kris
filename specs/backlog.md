# Backlog

> **MIGRATED**: All backlog items have been moved to the kwi workitems database (project: `kris`).
> Use `kwi list --project kris` or the `mcp_kwi_list_work_items` tool to view current items.
> B-numbers are preserved in work item titles for traceability.
>
> | Backlog ID | kwi WI # | Title |
> |------------|----------|-------|
> | B001 | #8 | Parallelize Rust scanner |
> | B002 | #9 | Reduce per-file chunk/embed log noise |
> | B003 | #10 | Default exclude patterns with per-source opt-out |
> | B004 | #11 | Record and surface encoding failures for exclude tuning |
> | B005 | #12 | Handle BertModel embeddings.position_ids warning |
> | B008 | #13 | Qdrant local mode warning / server migration |
> | B009 | #14 | llama.cpp n_ctx_per_seq warning |
> | B010 | #15 | CLI command to measure and update model VRAM sizes |
> | B011 | #16 | Add --show-failed switch to kris status |

## Agent Instructions

**Highest Bxxx Entry**: 11

New backlog items should be created directly in kwi using `mcp_kwi_create_work_item`.
B-numbers are no longer assigned — use kwi work item IDs instead.

---

## B001 — Parallelize Rust scanner

**Origin**: Phase 3 observation — `kris-scanner` is single-threaded; CPU utilization during scans is limited to one core.

**Current behavior**: The scanner walks directories, classifies, hashes, and writes to SQLite sequentially in a single thread.

**Opportunity**: The scan of `/home/ken` (163K files) and `/gratch` (581K files) would benefit from parallelism. Hashing and file I/O are the bottlenecks — classification and catalog writes are fast.

**Options to explore**:
- **Rayon** (`par_iter`): Parallelize hashing across files while keeping SQLite writes serial (SQLite is single-writer). Simplest option.
- **Async (tokio)**: Useful if I/O-bound rather than CPU-bound, but adds complexity. Likely overkill for local filesystem scans.
- **Channel-based pipeline**: Walk thread → hash pool → catalog writer. Separates concerns, keeps SQLite writes sequential.

**Constraints**:
- SQLite writes must remain serialized (single connection, WAL mode helps readers but not writers)
- Need to measure whether bottleneck is hashing (CPU) or filesystem I/O before choosing approach
- `--skip-hash` mode is already fast — parallelism matters most for full-hash scans

**Priority**: Low — `--skip-hash` is a sufficient workaround for MVP.

---

## B002 — Reduce per-file chunk/embed log noise

**Origin**: Observed during indexing — log file fills with per-content-hash INFO lines from `kris.processing.worker`:

```
INFO  kris.processing.worker — Created 1 chunks for 8c92515a147a
INFO  kris.processing.worker — Created 1 chunks for 83aac450dbd5
```

**Desired behavior**:
1. Demote the per-hash `"Created N chunks for ..."` and `"Embedded N chunks for ..."` messages to DEBUG.
2. Track a running total of chunks created / chunks embedded across the processing run.
3. Emit a single INFO line every 3,000 chunks (configurable constant), e.g. `"Created 3000 chunks"` / `"Embedded 3000 chunks"`.
4. At the end of the processing run, emit a final INFO line with the remainder, e.g. `"Created 87 chunks — indexing complete."`.

**Scope**: `src/kris/processing/worker.py` — the `execute_task` and `process_all_tasks` functions. The per-hash log moves to `logger.debug`; a simple counter + modulo check handles the periodic INFO.

Note: the `3000` figure should be derived from a constant within code so that it can be "tuned".

**Priority**: Low — cosmetic / log hygiene.

---

## B003 — Default exclude patterns with per-source opt-out

**Origin**: First real indexing run — `.ruff_cache`, `htmlcov`, `.svelte-kit`, and build artifact directories produced hundreds of encoding failures on binary cache/image files. These are universally unwanted across any source.

**Current behavior**: Each `sources.<name>` has its own `exclude_patterns` list. There are no global defaults, so every source must independently exclude common junk directories.

**Desired behavior**:
1. Add a top-level `default_exclude_patterns` list to the config schema (or hard-code a sensible built-in set). Suggested defaults:

   ```
   .ruff_cache, .mypy_cache, __pycache__, .pytest_cache,
   .git, .hg, .svn,
   node_modules, .svelte-kit, .next,
   target, build, dist,
   .venv, .tox, .nox,
   htmlcov, .coverage,
   *.pyc, *.pyo
   ```

2. At scan time, merge `default_exclude_patterns` with `sources.<name>.exclude_patterns` (union).
3. Add a boolean field `include_default_exclude_patterns` on `sources.<name>` that defaults to `true` when absent. When set to `false`, only the source's own `exclude_patterns` are used.

**Scope**:
- `src/kris/config/schema.py` — add `default_exclude_patterns` to `KrisConfig`, add `include_default_exclude_patterns` to `SourceConfig`
- `src/kris/config/defaults.py` — define the built-in default list
- `scanner/src/main.rs` (or wherever excludes are applied) — merge the two lists before filtering
- `src/kris/cli/init.py` — include the new field in the generated default config with comments

**Priority**: Medium — prevents noisy failures on first run for any source pointing at a development directory.

---

## B004 — Record and surface encoding failures for exclude tuning

**Origin**: First indexing run — many files fail with `"Cannot detect encoding for ..."` (binary caches, images, icons). These failures are recorded in the task table as `failed`, but the user has no easy way to discover *which extensions or paths* are causing them in order to refine exclude patterns.

**Problem**: Today a user must run `kris status`, eyeball the Failed Files table, and manually spot patterns. At scale (hundreds of failures) this is impractical.

**Ideas to explore** (needs research before committing to an approach):

1. **Store failure metadata in SQLite** — add a column (e.g. `error_detail` or `failure_reason`) to the file/task record, plus the file extension. This would allow SQL queries like:
   ```sql
   SELECT extension, COUNT(*) FROM file WHERE processing_status = 'failed' GROUP BY extension ORDER BY COUNT(*) DESC;
   ```

2. **CLI command or flag** — something like `kris status --failed-extensions` or a dedicated `kris diagnose` command that aggregates failed files by extension and/or path prefix, showing the user which patterns to add to `exclude_patterns`.

3. **Relationship to B003** — once default excludes exist (B003), this becomes a tool for discovering *additional* site-specific excludes the user should add. Complementary, not overlapping.

4. **Distinguish "expected skip" vs "unexpected failure"** — binary/image files failing encoding is expected behavior (they shouldn't be text-extracted). Consider whether the scanner or planner should avoid queuing extract tasks for files whose `file_kind` is `image`, `binary`, etc., rather than letting them fail during extraction. This may reduce the noise at the source.

**Open questions**:
- Should the scanner classify more aggressively (skip known binary extensions before task creation)?
- Should failures be queryable via CLI, or is direct SQLite access sufficient for power users?
- Is a new `processing_status` value (e.g. `skipped_binary`) more appropriate than `failed` for files that were never candidates for text extraction?

**Priority**: Medium — improves the config-tuning feedback loop, especially for new users onboarding large heterogeneous source trees.

---

## B005 — Handle BertModel `embeddings.position_ids` UNEXPECTED warning properly

**Origin**: During `kris index`, the sentence-transformers / safetensors load of `BAAI/bge-base-en-v1.5` emits:

```
BertModel LOAD REPORT from: BAAI/bge-base-en-v1.5
Key                     | Status     |
------------------------+------------+
embeddings.position_ids | UNEXPECTED |

Notes:
- UNEXPECTED: can be ignored when loading from different task/architecture
```

This is a known issue — `position_ids` was removed from newer HuggingFace BertModel implementations but the weight file still contains the key. It's benign for this model.

**Problem**: In `krag`, this was addressed by blanket-suppressing warnings at the logging/warnings level, which silenced this noise but also potentially hid other legitimate notices. That approach should not be repeated.

**Investigation needed**:
1. **Understand the root cause** — research what `embeddings.position_ids` UNEXPECTED means in the context of `BAAI/bge-base-en-v1.5`. Is this a model packaging issue (stale key in weights), a version mismatch between the model checkpoint and the `transformers` library, or a configuration we can correct (e.g. pinning a specific model revision, using a different checkpoint, or passing a config option)?
2. **Identify the source** — trace where the warning originates (safetensors loader, transformers `PreTrainedModel.from_pretrained`, or sentence-transformers wrapper).
3. **Look for a corrective fix first** — can we load the model in a way that avoids the mismatch entirely? For example: a newer/older model revision, a `transformers` config flag, or a different loading path that handles this key correctly.
4. **Check `krag`'s approach** — review the `krag` repo to document what suppression was applied and confirm it was overly broad. Avoid repeating.
5. **Only if no corrective fix exists**, consider targeted suppression — a scoped `warnings.filterwarnings` matching only this specific message, not a blanket silencing.

**Priority**: Low — cosmetic / stderr noise. The warning is harmless but looks alarming to users.

---

## B008 — Qdrant local mode warning for large collections

**Origin**: During `kris query`, Qdrant emits:
```
UserWarning: Local mode is not recommended for collections with more than 20,000 points.
Collection <kris_chunks> contains 20343 points.
Consider using Qdrant in Docker or Qdrant Cloud for better performance with large datasets.
```

**Context**: kris uses Qdrant in embedded/local mode (`QdrantClient(path=...)`). The collection has exceeded 20K points after indexing two source repos. As more sources are added, this will grow significantly (potentially 100K+ points).

**Investigation needed**:
1. Research whether this warning indicates actual performance degradation or is just advisory
2. Benchmark query latency at current scale — is it acceptable?
3. Evaluate options:
   - **Suppress the warning** if performance is acceptable (targeted `warnings.filterwarnings`)
   - **Switch to Qdrant server mode** (Docker container) for production use, keeping embedded for tests
   - **Make the backend configurable** — embedded for small installs, server mode for large collections
4. This may tie into the architecture's planned evolution (Qdrant is already the chosen vector store)

**Priority**: Medium — functional but noisy; will become a real performance question at scale.

---

## B009 — llama.cpp n_ctx_per_seq warning

**Origin**: During `kris query`, llama.cpp emits:
```
llama_context: n_ctx_per_seq (4096) < n_ctx_train (131072) — the full capacity of the model will not be utilized
```

**Context**: `src/kris/models/manager.py` hard-codes `n_ctx=4096` in `load_llm()`. The loaded model was trained with 131K context. 4096 is a reasonable default for VRAM conservation, but the warning is noisy.

**Investigation needed**:
1. Determine whether 4096 tokens is sufficient for typical query contexts (retrieved chunks + prompt template). If typical prompts are well under 4K, this is fine.
2. Consider making `n_ctx` configurable in `models.llm` config section rather than hard-coded.
3. Evaluate whether the warning can be suppressed via llama.cpp's `verbose` parameter (already set to `False`, so this may require a different approach).
4. Check if setting `verbose=False` should already suppress this — if not, file upstream or find the correct suppression.

**Priority**: Low — cosmetic. 4096 context is likely sufficient for MVP query patterns.

---

## B010 — CLI command to measure and update model VRAM sizes in config

**Origin**: User observation — `vram_gb` in `config.toml` is a manual guess. Actual VRAM usage (observed via `nvtop`) differs from the configured value (e.g. config says 12.0 GB, actual is ~11.2 GB / 11472 MiB). Accurate sizing matters for the model manager's VRAM budget decisions (hot-swap vs simultaneous loading).

**Current behavior**: Users must guess `vram_gb` when configuring models. There is no tooling to measure actual VRAM consumption.

**Desired behavior**: A CLI command (e.g. `kris config update-model-sizes`) that:
1. Reads the current config to find all configured models (embedding + LLM)
2. For each model, loads it onto the GPU and measures actual VRAM usage (e.g. via `torch.cuda.memory_allocated()` for embedding models, or llama.cpp's reported buffer sizes for GGUF models)
3. Updates the `vram_gb` field in `config.toml` with the measured value
4. Reports a summary:
   ```
   Model                          Configured    Measured    Updated
   BAAI/bge-base-en-v1.5          0.5 GB        0.4 GB      ✓
   Phi-3-medium-128k              12.0 GB       11.2 GB     ✓
   ```
5. Unloads each model before loading the next (VRAM budget)

**Implementation notes**:
- Embedding models (sentence-transformers): use `torch.cuda.memory_allocated()` before/after loading
- LLM models (llama-cpp): parse the `CUDA0 model buffer size` from llama.cpp's load output, or use `torch.cuda.memory_allocated()` delta
- Must handle the case where no GPU is available (skip sizing, warn user)
- Consider `--dry-run` flag that reports sizes without writing to config
- TOML writing: need a library that preserves comments and formatting (e.g. `tomlkit`) or a targeted regex replacement on the `vram_gb` line

**Priority**: Medium — improves accuracy of VRAM budget decisions; removes guesswork from config setup.

---

## B011 — Add --show-failed switch to `kris status` and suppress failed files by default

**Origin**: User observation — `kris status` unconditionally prints a "Failed Files" table that can be very long (hundreds of encoding failures, unsupported file types, etc.), drowning out the useful summary.

**Current behavior**: `kris status` always displays the full failed-files table when any failures exist (see `src/kris/cli/status.py` lines ~116-131). There is no way to hide it, and no way to show it on demand if it were hidden.

**Desired behavior**:
1. By default, `kris status` shows only the summary table plus a one-line count like `42 files failed (use --show-failed to list them)`.
2. `kris status --show-failed` (or `-f`) displays the full failed-files table as it does today.
3. JSON output (`--json`) always includes the `failed_files` array regardless of the flag — filtering is a display concern.

**Implementation notes**:
- Add `--show-failed` / `-f` `typer.Option` boolean flag, default `False`.
- When flag is off and `len(failed) > 0`, print a summary line with count instead of the table.
- When flag is on, print the table as today.
- No changes to JSON output.

**Priority**: Low — cosmetic improvement; the data is already available, just noisy by default.
