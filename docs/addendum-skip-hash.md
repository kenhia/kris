# Scanner Addendum: `--skip-hash` Flag

**Date**: 2026-03-19
**Component**: `kris-scanner` (Rust binary)
**Status**: Implemented, pending rollback into base docs

## Change

Added `--skip-hash` CLI flag to `kris-scanner` that bypasses SHA-256 content hashing during scans. When enabled, files are recorded with `content_hash = "skipped"` instead of computing the actual hash.

## Motivation

During exploration/magnitude-estimation scans of large directory trees (`/home/ken` ~hundreds of thousands of files, `/gratch` ~millions), the single-threaded SHA-256 hashing dominates scan time since it must read every byte of every file. For exploration purposes (file counts, size distribution, type breakdown), only metadata (size, mtime, file_kind, permissions) is needed — the walk + stat + classify steps are effectively free by comparison.

## Usage

```bash
# Fast exploration scan (metadata only)
kris-scanner --db /krag/kris/scan.db --source-id home --base-path /home/ken --skip-hash

# Full scan with content hashing (default, for production indexing)
kris-scanner --db /krag/kris/scan.db --source-id home --base-path /home/ken
```

## Implementation Details

- **Files changed**: `scanner/src/main.rs` (CLI arg), `scanner/src/lib.rs` (scan logic)
- When `--skip-hash` is set, the literal string `"skipped"` is used as `content_hash`
- All other behavior (walk, classify, catalog upsert, mark missing) is unchanged
- Content records are still created with `content_hash = "skipped"` — these would need re-scanning with full hashing before processing (extract/chunk/embed)

## Rollback Notes

When integrating into base docs:
- Update `plan.md` scanner section to mention the `--skip-hash` option
- Update `spec.md` FR list if exploration/audit scanning becomes a formal feature
- Consider adding `--skip-hash` support to the Python `scanner/runner.py` and `kris index` CLI
- Consider future `kris scan` command (exploration-only, no processing pipeline)
