# CLI Contract: kris MVP

**Feature**: 001-mvp-core

This document defines the CLI interface contract for the kris MVP.
All commands follow these conventions:

- Errors go to stderr, results to stdout
- `--json` flag available on all commands for machine-readable output
- `NO_COLOR` environment variable disables color output
- Exit code 0 on success, non-zero on failure
- `--help` available on all commands and subcommands
- `--verbose` / `-v` increases log verbosity (repeatable: `-vv`, `-vvv`)

---

## Commands

### `kris init`

Create a default configuration file.

```
kris init [--force]
```

| Flag | Description |
|------|-------------|
| `--force` | Overwrite existing config file |

**Output**: Path to created config file.
**Exit codes**: 0 = created, 1 = already exists (without `--force`).

---

### `kris index`

Scan configured sources and process new/changed files.

```
kris index [--source SOURCE_ID] [--dry-run]
```

| Flag | Description |
|------|-------------|
| `--source` | Scan only this source (default: all) |
| `--dry-run` | Show what would be processed without doing it |

**Output**: Progress bar during scan/processing. Summary on completion
showing files discovered, new, changed, processed, skipped, failed.

---

### `kris query`

Ask a natural language question and get an LLM-synthesized answer.

```
kris query QUESTION [--show-sources] [--top-k N] [--source SOURCE_ID]
           [--kind FILE_KIND]
```

| Flag | Description |
|------|-------------|
| `--show-sources` | Display source chunks alongside the answer |
| `--top-k N` | Number of chunks to retrieve (default: 10) |
| `--source` | Limit search to a specific source |
| `--kind` | Limit search to a specific file kind |

**Output**: Synthesized answer with source citations.
Format: answer text, then "Sources:" section listing file paths
and chunk excerpts.

---

### `kris retrieve`

Retrieve relevant chunks without LLM synthesis.

```
kris retrieve QUERY [--top-k N] [--source SOURCE_ID] [--kind FILE_KIND]
```

| Flag | Description |
|------|-------------|
| `--top-k N` | Number of chunks to return (default: 10) |
| `--source` | Limit search to a specific source |
| `--kind` | Limit search to a specific file kind |

**Output**: Ranked list of chunks with file path, chunk index,
relevance score, and chunk text.

---

### `kris status`

Show index statistics.

```
kris status [--source SOURCE_ID]
```

| Flag | Description |
|------|-------------|
| `--source` | Show status for a specific source only |

**Output**: Table showing:
- Files per source (total, by kind, by processing status)
- Chunks and embeddings count
- Last scan time per source
- Failed files (if any) with error reasons

---

### `kris config validate`

Validate the configuration file.

```
kris config validate [--config PATH]
```

| Flag | Description |
|------|-------------|
| `--config` | Path to config file (default: XDG location) |

**Output**: "Configuration valid" on success. List of validation
errors on failure.

---

### `kris duplicates`

List groups of files with identical content.

```
kris duplicates [--source SOURCE_ID] [--min-size SIZE]
```

| Flag | Description |
|------|-------------|
| `--source` | Limit to a specific source |
| `--min-size` | Minimum file size to report (e.g., `1KB`, `1MB`) |

**Output**: Groups of files sharing the same content hash, with
paths, sources, and sizes.

---

### `kris cleanup`

Remove artifacts for missing/archived files.

```
kris cleanup [--older-than DURATION] [--path PATTERN]
             [--source SOURCE_ID] [--dry-run] [--yes]
```

| Flag | Description |
|------|-------------|
| `--older-than` | Only files missing for longer than this (e.g., `30d`, `1w`) |
| `--path` | Only files matching this path pattern |
| `--source` | Only files from this source |
| `--dry-run` | Show what would be removed without doing it |
| `--yes` | Skip confirmation prompt |

**Output**: List of files and artifacts to be removed, then
confirmation prompt (unless `--yes`). Summary of removed items.

---

## JSON Output Format

When `--json` is passed, all commands emit structured JSON to stdout.

### Common envelope

```json
{
  "status": "ok",
  "command": "status",
  "data": { ... }
}
```

### Error envelope

```json
{
  "status": "error",
  "command": "index",
  "error": {
    "message": "Source 'foo' not found in configuration",
    "code": "SOURCE_NOT_FOUND"
  }
}
```
