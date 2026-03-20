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
