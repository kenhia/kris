# kris — Usage Guide

## Commands Overview

| Command | Description |
|---------|-------------|
| `kris init` | Create default configuration file |
| `kris index` | Scan sources and process new/changed files |
| `kris query` | Ask questions about indexed files |
| `kris retrieve` | Get relevant chunks without LLM synthesis |
| `kris status` | View index statistics |
| `kris diagnose` | Show failure and skip diagnostics |
| `kris duplicates` | Find groups of identical files |
| `kris cleanup` | Remove artifacts for missing files |
| `kris config validate` | Validate configuration file |
| `kris config update-model-sizes` | Measure and update model VRAM usage |

## Global Flags

All commands support these flags:

```
--json          Output in JSON format (machine-readable)
--verbose / -v  Increase log verbosity (-v, -vv, -vvv)
--help          Show command help
```

The `NO_COLOR` environment variable disables colored output.

---

## Indexing

### Full index

```bash
kris index
```

Scans all configured sources and processes new or changed files.
Unchanged files are skipped automatically.

### Index a specific source

```bash
kris index --source my-code
```

### Dry run

```bash
kris index --dry-run
```

Shows what would be processed without making changes.

### How indexing works

1. **Scan** — The Rust scanner walks each source directory, computing
   SHA-256 hashes and cataloging file metadata in SQLite.
2. **Plan** — The task planner creates extract → chunk → embed tasks
   for new or changed content.
3. **Process** — The worker executes tasks: extracts text, chunks it
   using file-kind-aware strategies, and generates embeddings stored
   in OpenSearch.

Files with identical content across sources share processing artifacts
(content-addressed dedup).

---

## Querying

### Ask a question

```bash
kris query "how does the authentication module work?"
```

Returns an LLM-synthesized answer grounded in your indexed files,
with source citations.

### Show source chunks

```bash
kris query --show-sources "error handling patterns"
```

Displays the individual chunks used to build the answer.

### Filter by source or file kind

```bash
kris query --source my-code "database connection setup"
kris query --kind code "retry logic"
```

### Adjust retrieval depth

```bash
kris query --top-k 20 "configuration options"
```

### Retrieval-only mode

```bash
kris retrieve "database connection"
```

Returns matching chunks ranked by relevance without LLM synthesis.
Useful for exploring what the index contains.

```bash
kris retrieve --top-k 5 --source docs "API endpoints"
```

---

## Status

### View index status

```bash
kris status
```

Shows a table with per-source file counts, processing status,
chunk and embedding counts, and last scan time. Failed files are
hidden by default — only a count is shown.

### Show failed files

```bash
kris status --show-failed
```

Displays the full failed-files table with paths and error messages.

### Filter by source

```bash
kris status --source my-code
```

### JSON output

```bash
kris status --json
```

---

## Duplicate Detection

### Find duplicate files

```bash
kris duplicates
```

Lists groups of files that share identical content across all sources.

### Filter by source

```bash
kris duplicates --source my-code
```

### Filter by minimum size

```bash
kris duplicates --min-size 1KB
```

---

## Cleanup

Files deleted from disk are marked as `missing` during the next
index run. Their chunks and embeddings are preserved until you
explicitly clean them up.

### Preview what would be removed

```bash
kris cleanup --dry-run
```

### Remove missing files older than 30 days

```bash
kris cleanup --older-than 30d
```

### Remove by path pattern

```bash
kris cleanup --path "%old-project%"
```

### Remove from a specific source

```bash
kris cleanup --source my-code
```

### Skip confirmation prompt

```bash
kris cleanup --older-than 30d --yes
```

---

## Diagnostics

### View failure breakdowns

```bash
kris diagnose
```

Shows tables grouping processing failures by file extension,
skipped files by kind, and common failure path prefixes.

### Filter by source

```bash
kris diagnose --source my-code
```

### Adjust minimum count threshold

```bash
kris diagnose --min-count 5
```

### JSON output

```bash
kris diagnose --json
```

---

## Configuration

### Create default config

```bash
kris init
```

Creates `~/.config/kris/config.toml` with defaults. Use `--force`
to overwrite an existing file.

### Validate config

```bash
kris config validate
kris config validate --config /path/to/config.toml
```

Reports any configuration errors and shows effective exclude
patterns per source.

### Measure model VRAM

```bash
kris config update-model-sizes
```

Loads each configured model onto the GPU, measures actual VRAM
usage, and updates `vram_gb` values in `config.toml` (preserving
comments and formatting).

Preview without modifying config:

```bash
kris config update-model-sizes --dry-run
```

### Config file format

See [setup.md](setup.md) for the full configuration schema.

---

## JSON Output

All commands support `--json` for machine-readable output:

```bash
kris status --json
kris query --json "my question"
kris duplicates --json
```

The JSON envelope is:

```json
{
  "status": "ok",
  "command": "status",
  "data": { ... }
}
```

Errors use:

```json
{
  "status": "error",
  "error": { "message": "..." }
}
```

---

## Logging

Logs are written to `~/.local/share/kris/kris.log` with automatic
rotation (5 MB, 3 backups).

At INFO level (default), per-file processing messages are suppressed
and periodic batch summaries are shown every 3,000 items. A final
summary reports totals at completion.

Increase console verbosity for per-file detail:

```bash
kris -v index       # INFO level (batch summaries)
kris -vv index      # DEBUG level (per-file messages)
```

---

## Direct Scanner Usage

The Rust scanner binary (`kris-scanner`) can be invoked directly
for advanced use cases. Normally `kris index` handles scanning
automatically.

### Exploration scan (metadata only)

For large directory trees where you want file counts, size
distribution, and type breakdown without the cost of hashing
every file:

```bash
kris-scanner --db /path/to/catalog.db --source-id home --base-path /home/user --skip-hash
```

With `--skip-hash`, SHA-256 content hashing is bypassed. Files are
recorded with `content_hash = "skipped"` — they would need
re-scanning without this flag before processing (extract/chunk/embed).

### Full scan

```bash
kris-scanner --db /path/to/catalog.db --source-id home --base-path /home/user
```

Computes SHA-256 hashes for change detection. This is the mode
used by `kris index`.

---

## Development

```bash
just build    # Build scanner + sync Python deps
just test     # Run all tests
just check    # Full pre-commit check (fmt + lint + typecheck + test)
just fmt      # Format all code
just clean    # Remove build artifacts
```
