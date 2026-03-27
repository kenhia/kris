# kris Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-25

## Active Technologies
- Rust (stable) for scanner; Python 3.12+ for core + `qdrant-client`, `sentence-transformers`, `llama-cpp-python`, `typer`, `rich`, `tomlkit` (new); Rust: `walkdir`, `globset` (new), `rusqlite`, `clap` (002-production-hardening)
- SQLite (WAL mode) + Qdrant (embedded or server, configurable) (002-production-hardening)

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
- 002-production-hardening: Added Rust (stable) for scanner; Python 3.12+ for core + `qdrant-client`, `sentence-transformers`, `llama-cpp-python`, `typer`, `rich`, `tomlkit` (new); Rust: `walkdir`, `globset` (new), `rusqlite`, `clap`

- 001-mvp-core: Added Rust (stable, latest) for scanner; Python 3.12+ for core (managed by `uv`) + `sentence-transformers`, `llama-cpp-python`, `qdrant-client`, `typer`, `rich`, `py-tree-sitter`, `charset-normalizer`; Rust: `walkdir`, `sha2`, `rusqlite`, `serde`, `clap`

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
