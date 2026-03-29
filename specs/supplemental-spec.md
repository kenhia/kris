# Supplemental Spec — Standalone Bugs & Issues

Items tracked here are independent of sprint feature specs.

---

## S001: Progress bar total exceeded during `kris index` (WI #20)

**Type**: bug | **Status**: open | **Size**: M | **Sprint**: —

### Problem

`kris index` progress bar shows "489/354" — completed count exceeds the total.
Three interrelated issues in the worker/progress pipeline.

### Acceptance Criteria

- [ ] Progress bar total reflects actual queued task count from DB, not `planned * 3`
- [ ] Retried task attempts do not inflate the progress counter
- [ ] `max_attempts=3` means exactly 3 attempts (fix off-by-one in stale `task.attempts` check)
- [ ] Progress bar never shows completed > total

### Tasks

- [ ] ST001 Fix progress bar total in `src/kris/cli/index.py` — query actual queued task count from DB instead of `planned * 3` (WI #20)
- [ ] ST002 Fix retry double-counting in `src/kris/processing/worker.py` — track unique task completions, not cumulative attempt count (WI #20)
- [ ] ST003 Fix off-by-one in `execute_task()` retry check — use `task.attempts + 1 >= task.max_attempts` or re-read from DB after increment (WI #20)
- [ ] ST004 Add unit test: progress callback values never exceed initial queued task count (WI #20)
