# Research: MVP Core — Local Scan, Index, Embed, Query

**Date**: 2026-03-19
**Feature**: 001-mvp-core

---

## R1: PyO3 — Where Rust Extensions Benefit Python

**Decision**: Skip PyO3 for the MVP. Defer until profiling identifies bottlenecks.

**Rationale**: The Python side of kris is primarily I/O-bound (reading
SQLite, calling embedding models, calling LLMs). The CPU-intensive
filesystem traversal and SHA-256 hashing already happen in the Rust
scanner. Python's `hashlib` (C-backed), `sqlite3` (C-backed), and
tree-sitter bindings (C-backed) are already native-speed for their
respective operations. Introducing PyO3 adds build complexity (Rust
toolchain in Python wheel builds, platform-specific wheels, version
coordination) without a clear performance payoff for the MVP workload.

**Alternatives considered**:
- PyO3 for SHA-256: Unnecessary — `hashlib.sha256` is already C. The
  scanner already computes content hashes anyway; Python rarely
  re-hashes.
- PyO3 for file classification: Classification is a simple extension
  lookup + heuristic. Negligible CPU cost.
- PyO3 for chunking: `py-tree-sitter` is C-backed. Only worth
  reconsidering if profiling shows chunking as a bottleneck at scale.

**Condition to reconsider**: If profiling the "day zero" scan (100k+
files) reveals that Python-side processing is the bottleneck (not
model inference), evaluate PyO3 for the specific hot path identified.

---

## R2: Tree-sitter for Code-Aware Chunking

**Decision**: Use `py-tree-sitter` (official Python bindings) in the
Python core for code-aware chunking.

**Rationale**: Chunking happens in the Python processing pipeline after
text extraction. Using `py-tree-sitter` keeps all processing logic in
Python, which simplifies configuration (chunk sizes, overlap, strategies
are Python-side config). The C-backed bindings are fast enough for a
single-user system — tree-sitter parsing is not the bottleneck compared
to model inference. Moving chunking into the Rust scanner would violate
separation of concerns (scanner discovers files, Python processes them).

**Alternatives considered**:
- `tree-sitter-rs` via PyO3: Adds build complexity without meaningful
  performance gain.
- `tree-sitter-rs` in the Rust scanner: Forces chunking parameters
  into the scanner binary, coupling configuration and deployment.
  Chunking strategy evolution should be independent of scanner releases.

---

## R3: Embedding Model Library

**Decision**: Use `sentence-transformers` for the embedding pipeline.

**Rationale**: `sentence-transformers` is the de facto standard for local
embedding in Python. It seamlessly loads pre-trained models from
HuggingFace, handles GPU acceleration automatically, and provides a
simple `model.encode()` API. The MVP embedding model
(`BAAI/bge-base-en-v1.5`, 768 dimensions, ~0.5 GB VRAM) loads cleanly
through it. The library is actively maintained by HuggingFace.

**Alternatives considered**:
- ONNX Runtime: Lower-level, faster on CPU. Requires model conversion
  and more setup. Overkill for MVP.
- FastEmbed: CPU-only via ONNX. Good for lightweight setups but less
  flexible for GPU inference.

---

## R4: Local LLM Inference

**Decision**: Use `llama-cpp-python` for local LLM inference (query
synthesis).

**Rationale**: `llama-cpp-python` is the standard for embedding GGUF
models in Python. It provides an OpenAI-compatible API, supports CUDA
GPU acceleration, and has minimal dependencies. For a single-user CLI
tool, it's simpler than running a separate inference server.

**Alternatives considered**:
- vLLM: Production-grade inference server with paging and continuous
  batching. Overkill for single-user local MVP. Better suited for
  multi-client serving.
- SGLang: Similar to vLLM, focused on complex inference workflows.
  Unnecessary complexity for MVP.
- Ollama: Requires a separate daemon process. `llama-cpp-python`
  embeds directly, which is simpler for CLI invocation.

**Condition to reconsider**: If a server mode is added later (API
serving multiple clients), evaluate vLLM or Ollama as the inference
backend behind the API.

---

## R5: SQLite Concurrency — Rust Scanner + Python Core

**Decision**: Use standard `sqlite3` module with WAL mode and
`busy_timeout`. No special library needed for the MVP.

**Rationale**: WAL (Write-Ahead Logging) mode allows concurrent
readers and a single writer without blocking. The Rust scanner writes
FILE/CONTENT records; Python reads them and writes TASK/CHUNK/EMBEDDING
records. With `busy_timeout = 5000` (5 seconds), brief write contention
resolves automatically. This is a single-user local system — not a
high-concurrency scenario.

**Configuration**:
```sql
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;
```

**Alternatives considered**:
- `aiosqlite`: Async wrapper. The MVP CLI is synchronous; async adds
  complexity without benefit. Reconsider when adding FastAPI async
  endpoints.
- SQLAlchemy: ORM abstraction. For MVP, raw SQL via `sqlite3` is
  cleaner and more transparent. Reconsider if schema complexity grows.

---

## R6: Qdrant — Embedded vs. Service Mode

**Decision**: Use `qdrant-client` in **embedded mode** (persistent local
storage). No separate Qdrant server for the MVP.

**Rationale**: Embedded mode (`QdrantClient(path="...")`) provides the
same API as the server but runs in-process. For a single-user local
system, this eliminates network overhead, daemon management, and port
configuration. Data persists to disk at the configured path.

**Usage**:
```python
from qdrant_client import QdrantClient
client = QdrantClient(path="$XDG_CACHE_HOME/kris/qdrant")
```

**Alternatives considered**:
- Qdrant server (Docker or binary): Better for multi-client access
  and distributed setups. Unnecessary operational overhead for MVP.
- Qdrant Cloud: Violates local-first principle.

**Condition to reconsider**: Switch to service mode when adding the HTTP
API (multiple clients may query Qdrant concurrently) or when data volume
exceeds embedded mode's practical limits.

---

## R7: Project Layout — Monorepo with uv

**Decision**: Monorepo with Rust scanner as a subdirectory and Python
core at the project root, managed by `uv`.

**Rationale**: The architecture specifies a monorepo. Placing the
Python project at the root (with `pyproject.toml`) and the Rust
scanner in a `scanner/` subdirectory keeps the primary development
language front-and-center while cleanly separating the Rust build.
`uv` manages the Python environment, dependencies, and lockfile.
The Rust scanner builds independently via Cargo.

**Layout**:
```
kris/
├── pyproject.toml           # Python project root (uv-managed)
├── uv.lock
├── src/kris/                # Python package
│   ├── __init__.py
│   ├── cli/                 # CLI commands (Typer + Rich)
│   ├── catalog/             # SQLite catalog operations
│   ├── planner/             # Task planning
│   ├── processing/          # Extraction, chunking, embedding
│   ├── models/              # Model management
│   ├── query/               # Query engine, retrieval, synthesis
│   └── config/              # Configuration loading/validation
├── scanner/                 # Rust scanner binary
│   ├── Cargo.toml
│   └── src/
│       ├── main.rs
│       └── lib.rs
├── tests/                   # Python tests
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── docs/
├── specs/
└── Justfile                 # Build automation (build scanner, sync env, etc.)
```

**Build coordination**: A `Justfile` (or `Makefile`) provides unified
commands: `just build` (builds scanner + syncs Python), `just test`
(runs both Cargo test and pytest), `just check` (runs all linters).

---

## R8: Text Extraction Libraries

**Decision**: Use `charset-normalizer` for encoding detection and
built-in file reading for text extraction. Avoid heavy dependencies
like `textract` or `unstructured`.

**Rationale**: The MVP processes text, code, markdown, and config
files — all are directly readable as text. No PDF, DOCX, or other
binary-to-text conversion is needed for the MVP scope. Encoding
detection handles the edge case of non-UTF-8 files.

**Extraction by file kind**:
- text/markdown/config: Read as UTF-8, fall back to detected encoding
- code: Read as UTF-8 (source code is almost universally UTF-8)

**Condition to reconsider**: When adding PDF/DOCX support in later
phases, evaluate `pymupdf` (PDF) and `python-docx` (DOCX).
