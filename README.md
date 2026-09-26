# kris

> **Archived 2026-09-25 — retired 2026-09-19, no successor.**
> kris (the successor to [krag](https://github.com/kenhia/krag)) was retired before it reached
> a stable release. Its last in-flight sprint was finished and merged as
> [PR #3](https://github.com/kenhia/kris/pull/3) before retirement, so the tracked tree here is
> complete; the untracked working notes were kept in a private archive, so nothing was lost.
> Retirement record: korg WI 2857; archive executed by korg WI 2858.
>
> **Do not run this.** It is unmaintained and its dependencies are frozen as of the last commit.

A personal data intelligence system for indexing, analyzing, and querying data across local machines, remote Linux hosts, and NAS storage.

> **Note**: kris is a personal learning and tooling project. While the goal is a fully functioning system, the primary purpose is to explore architectures for multi-source data indexing, semantic search, multi-LLM orchestration, and personal knowledge management. Expect experimentation, iteration, and evolving design decisions.

## what it does

kris scans files across heterogeneous sources, extracts and chunks content, generates embeddings, and provides semantic search with LLM-powered synthesis. It's designed to answer questions like:

- "Where's that script I wrote for parsing nginx logs?"
- "Summarize what I worked on this week across all my projects"
- "Find all references to the auth refactor across my notes and code"

## architecture at a glance

- **Rust scanner** — fast filesystem traversal with per-path scan schedules
- **SQLite catalog** — content-addressed file registry with dedup across sources
- **Task planner** — generates processing DAGs per file kind (text, code, images, etc.)
- **Python processing** — extraction, chunking, embedding, summarization via local LLMs
- **Qdrant** — vector storage with named spaces per embedding model
- **CLI + API** — query interfaces with LLM synthesis

Local-first. Nothing leaves your hardware unless you explicitly configure a remote LLM fallback.

## inspiration

kris is the successor to [krag](https://github.com/kenhia/krag), a local-first RAG system for indexing and querying personal file collections. krag proved out the core patterns — multi-model embedding, LLM hot-swap, semantic chunking, Qdrant storage — and kris expands on those lessons with multi-source support, a persistent task graph, content-addressed dedup, and multimodal pipelines.

## status

Architecture and design phase. See [`docs/`](docs/) for current documents:

- [Architecture](docs/architecture.md) — system design and component overview
- [Data Model](docs/data-model.md) — schemas, contracts, and storage design
- [Clarifications & Decisions](docs/clarifications-needed.md) — design decisions log

## license

Apache License 2.0 — see [LICENSE](LICENSE) for details.

## contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow, coding standards, and how to submit changes.
