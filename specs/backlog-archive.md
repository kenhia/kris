# Backlog Archive

> **MIGRATED**: Archived items have been moved to the kwi workitems database (project: `kris`, status: `closed`).
>
> | Backlog ID | kwi WI # | Title |
> |------------|----------|-------|
> | B006 | #6 | Embedding pipeline per-call overhead |
> | B007 | #7 | Query pipeline not using GPU for LLM inference |

Items moved from backlog into active sprints or completed.

---

## B006 — Embedding pipeline per-call overhead (moved to 001-mvp-core Phase 10)

**Origin**: First full indexing run of `~/src/krag` + `~/src/kris` (~39,087 items to embed) took ~4 hours. `nvtop` showed GPU RAM allocated (2 GiB) but minimal GPU compute — CPU-bound.

**Diagnosis**: PyTorch CUDA is available (`torch.cuda.is_available() == True`, CUDA 12.8). `SentenceTransformer` loads model on `cuda:0`. The bottleneck is **not** GPU vs CPU — it is per-content-hash overhead:
1. `QdrantClient(path=...)` instantiated on every `embed_chunks()` call (~13K times). Embedded-mode Qdrant opens/closes storage engine each time.
2. `model.encode()` called with tiny batches (1-5 chunks per content hash) instead of large batches. Benchmark: 335 texts/s single vs 4,290 texts/s batched (13x).

**Resolution**: Incorporated into `specs/001-mvp-core` as Phase 10 (tasks T084-T088, CT010). Key fix: create `QdrantClient` once in `run_worker()` and pass through.

**Moved**: 2026-03-20

---

## B007 — Query pipeline not using GPU for LLM inference (moved to 001-mvp-core Phase 11)

**Origin**: First `kris query` run — response quality was good but LLM inference appeared CPU-bound. `nvtop` showed no GPU compute during synthesis. The model manager specifies `n_gpu_layers=-1` but `llama-cpp-python` may have been installed without CUDA bindings, causing silent fallback to CPU.

**Resolution**: Incorporated into `specs/001-mvp-core` as Phase 11 (tasks T089-T091, CT011). Key actions: diagnose CUDA bindings, reinstall with CUDA if needed, log backend at load time.

**Moved**: 2026-03-20
