# kris Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-19

## Active Technologies

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

- 001-mvp-core: Added Rust (stable, latest) for scanner; Python 3.12+ for core (managed by `uv`) + `sentence-transformers`, `llama-cpp-python`, `qdrant-client`, `typer`, `rich`, `py-tree-sitter`, `charset-normalizer`; Rust: `walkdir`, `sha2`, `rusqlite`, `serde`, `clap`

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
