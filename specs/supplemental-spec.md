# Supplemental Spec — Standalone Bugs & Issues

Items tracked here are independent of sprint feature specs.

---

## S001: Progress bar total exceeded during `kris index` (WI #20)

**Type**: bug | **Status**: active | **Size**: M | **Sprint**: 003-opensearch-transition

### Problem

`kris index` progress bar shows "489/354" — completed count exceeds the total.
Three interrelated issues in the worker/progress pipeline.

### Acceptance Criteria

- [x] Progress bar total reflects actual queued task count from DB, not `planned * 3`
- [x] Retried task attempts do not inflate the progress counter
- [x] `max_attempts=3` means exactly 3 attempts (fix off-by-one in stale `task.attempts` check)
- [x] Progress bar never shows completed > total

### Tasks

- [x] ST001 Fix progress bar total in `src/kris/cli/index.py` — query actual queued task count from DB instead of `planned * 3` (WI #20)
- [x] ST002 Fix retry double-counting in `src/kris/processing/worker.py` — track unique task completions, not cumulative attempt count (WI #20)
- [x] ST003 Fix off-by-one in `execute_task()` retry check — use `task.attempts + 1 >= task.max_attempts` or re-read from DB after increment (WI #20)
- [x] ST004 Add unit test: progress callback values never exceed initial queued task count (WI #20)

---

## S002: BertModel embeddings.position_ids warning during model load (WI #12)

**Type**: issue | **Status**: active | **Size**: S | **Sprint**: 003-opensearch-transition

### Problem

Loading BAAI/bge-base-en-v1.5 via sentence-transformers emits a noisy warning:
```
BertModel LOAD REPORT from: BAAI/bge-base-en-v1.5
embeddings.position_ids | UNEXPECTED
```
The warning is benign (position_ids removed from newer BertModel but still in checkpoint weights)
but looks alarming to users. Located in `src/kris/models/manager.py` `load_embedding_model()`.

### Acceptance Criteria

- [x] The position_ids warning is not visible at INFO log level during normal `kris index` / `kris query`
- [x] Fix is targeted (not blanket warning suppression)

### Tasks

- [x] ST005 Investigate whether a specific model revision or config eliminates the warning (WI #12)
- [x] ST006 If no upstream fix, add scoped `warnings.filterwarnings` around SentenceTransformer load in `src/kris/models/manager.py` targeting only "position_ids.*UNEXPECTED" (WI #12)
- [x] ST007 Add unit test verifying embedding model loads without warning output (WI #12)

---

## S003: llama.cpp n_ctx_per_seq warning during query (WI #14)

**Type**: issue | **Status**: active | **Size**: S | **Sprint**: 003-opensearch-transition

### Problem

During `kris query`, llama.cpp emits:
```
n_ctx_per_seq (4096) < n_ctx_train (131072)
```
The `n_ctx=4096` is hard-coded in `src/kris/models/manager.py` `load_llm()` line 82.
4096 tokens is likely sufficient for current query patterns, but the warning is noisy
and the value should be configurable for future needs.

### Acceptance Criteria

- [x] `n_ctx` is configurable via `[models.llm]` config section with a sensible default
- [x] The warning is suppressed or eliminated during normal usage
- [x] Existing behavior unchanged when `n_ctx` is not specified in config

### Tasks

- [x] ST008 Add `n_ctx` integer field (default 4096) to LLM model config in `src/kris/config/schema.py` (WI #14)
- [x] ST009 Update `load_llm()` in `src/kris/models/manager.py` to read `n_ctx` from model config (WI #14)
- [x] ST010 Investigate whether `verbose=False` should suppress this warning; if not, add targeted suppression (WI #14)
- [x] ST011 Add unit test verifying LLM loads with configured n_ctx value (WI #14)
- [x] ST012 Update default config template in `src/kris/config/defaults.py` to include `n_ctx` with comment (WI #14)

---

## Execution Plan

### Order & Dependencies

All three items are independent — no cross-dependencies. Recommended order by impact:

1. **S001 (Progress bar bug)** — Most visible, directly affects user experience.
   Execute ST003 → ST002 → ST001 → ST004 (fix core bug first, then counting, then display, then test).

2. **S003 (llama.cpp n_ctx)** — Config change + targeted suppression.
   Execute ST008 → ST012 → ST009 → ST010 → ST011 (schema → defaults → implementation → suppression → test).

3. **S002 (BertModel warning)** — Investigation-first.
   Execute ST005 → ST006 → ST007 (investigate → fix → test).

### Files Modified

| File | Items |
|------|-------|
| `src/kris/cli/index.py` | S001 (ST001) |
| `src/kris/processing/worker.py` | S001 (ST002, ST003) |
| `src/kris/catalog/tasks.py` | S001 (ST001 — add count query) |
| `src/kris/config/schema.py` | S003 (ST008) |
| `src/kris/config/defaults.py` | S003 (ST012) |
| `src/kris/models/manager.py` | S002 (ST006), S003 (ST009, ST010) |
| `tests/unit/test_worker_logging.py` | S001 (ST004) |
| `tests/unit/test_config.py` | S003 (ST011) |
| `tests/unit/test_config_cmd.py` | S002 (ST007) |
