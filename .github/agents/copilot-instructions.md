# kris Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-29

## Active Technologies
- Rust (stable) for scanner; Python 3.12+ for core + `qdrant-client`, `sentence-transformers`, `llama-cpp-python`, `typer`, `rich`, `tomlkit` (new); Rust: `walkdir`, `globset` (new), `rusqlite`, `clap` (002-production-hardening)
- SQLite (WAL mode) + Qdrant (embedded or server, configurable) (002-production-hardening)
- Python 3.12+, Rust (scanner — unchanged this sprint) + `opensearch-py>=3.0` (replaces `qdrant-client>=1.14`), `sentence-transformers`, `llama-cpp-python`, `rich`, `typer` (003-opensearch-transition)
- SQLite (catalog, task queue, chunk store — unchanged), OpenSearch (vectors + text — new) (003-opensearch-transition)

- Rust (stable, latest) for scanner; Python 3.12+ for core (managed by `uv`) + `sentence-transformers`, `llama-cpp-python`, `qdrant-client`, `typer`, `rich`, `py-tree-sitter`, `charset-normalizer`; Rust: `walkdir`, `sha2`, `rusqlite`, `serde`, `clap` (001-mvp-core)

## Project Structure

```text
src/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Rust (stable, latest) for scanner; Python 3.12+ for core (managed by `uv`): Follow standard conventions

## Recent Changes
- 003-opensearch-transition: Added Python 3.12+, Rust (scanner — unchanged this sprint) + `opensearch-py>=3.0` (replaces `qdrant-client>=1.14`), `sentence-transformers`, `llama-cpp-python`, `rich`, `typer`
- 002-production-hardening: Added Rust (stable) for scanner; Python 3.12+ for core + `qdrant-client`, `sentence-transformers`, `llama-cpp-python`, `typer`, `rich`, `tomlkit` (new); Rust: `walkdir`, `globset` (new), `rusqlite`, `clap`

- 001-mvp-core: Added Rust (stable, latest) for scanner; Python 3.12+ for core (managed by `uv`) + `sentence-transformers`, `llama-cpp-python`, `qdrant-client`, `typer`, `rich`, `py-tree-sitter`, `charset-normalizer`; Rust: `walkdir`, `sha2`, `rusqlite`, `serde`, `clap`

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
