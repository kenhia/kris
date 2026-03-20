# Backlog

Items captured during MVP development for future consideration.

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
