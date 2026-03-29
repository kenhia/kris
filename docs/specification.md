# kris — MVP Core Specification

Canonical specification for the kris personal data intelligence system
MVP (feature branch `001-mvp-core`). Consolidates user stories,
functional requirements, configuration schema, and success criteria.

## Overview

kris scans local directories (including NAS mount paths), extracts
and chunks text-based files, generates vector embeddings, and answers
natural language queries via CLI with LLM-synthesized responses
grounded in the indexed content.

## User Stories

### US1: Scan and Index Local Files (P1)

Scan configured directories, discover files, extract text, chunk
content, and embed chunks into OpenSearch. All files are cataloged with
metadata regardless of processing eligibility. Incremental — only
new or changed files are reprocessed.

### US2: Query My Files (P1)

Ask natural language questions and receive LLM-synthesized answers
with source file citations. Supports retrieval-only mode (chunks
without synthesis). Indicates when no relevant content is found.

### US3: Configure Sources and Scan Schedules (P2)

Configure multiple sources with independent base paths, exclude
patterns, and scan schedule definitions. `kris init` creates a
default configuration; `kris config validate` checks it.

### US4: View Index Status (P2)

`kris status` shows file counts by source, file kind, and processing
status. Failed files are listed with error reasons.

### US5: Content-Addressed Dedup (P3)

Files with identical content share processing artifacts via
content_hash. `kris duplicates` lists groups of files sharing the
same content.

### US6: Archive and Cleanup (P3)

Deleted files are marked `missing` — artifacts preserved until the
user explicitly cleans them up via `kris cleanup` with selectors
(path pattern, age, source).

## Functional Requirements

### Scanning & Catalog

| ID | Requirement |
|----|-------------|
| FR-001 | Scan configured local directories recursively |
| FR-002 | Compute SHA-256 content hashes for change detection |
| FR-003 | Classify files by kind using extension and heuristics |
| FR-004 | Catalog every file with metadata regardless of processability |
| FR-005 | Incremental scanning — only changed files trigger reprocessing |
| FR-006 | Respect configured exclude patterns |
| FR-007 | Support multiple sources with independent configuration |
| FR-008 | Mark oversized files as `skipped` while recording metadata |

### Content-Addressed Dedup

| ID | Requirement |
|----|-------------|
| FR-009 | Use content_hash as key — identical content shares artifacts |
| FR-010 | Provide duplicate listing grouped by content |

### Processing Pipeline

| ID | Requirement |
|----|-------------|
| FR-011 | Extract text from text, code, markdown, and config files |
| FR-012 | Chunk text using file-kind-aware strategies (AST for code) |
| FR-013 | Generate vector embeddings per chunk |
| FR-014 | Store embeddings in OpenSearch; resolve paths via SQLite join |
| FR-015 | Persist chunk records in SQLite |
| FR-016 | Task planner generates extract → chunk → embed tasks by kind |
| FR-017 | Order tasks to minimize model load/unload cycles |

### Archival & Cleanup

| ID | Requirement |
|----|-------------|
| FR-018 | Mark missing files with timestamp, preserve artifacts |
| FR-019 | CLI cleanup commands with path, age, and source selectors |
| FR-020 | Require user confirmation before deleting artifacts |

### Query & Retrieval

| ID | Requirement |
|----|-------------|
| FR-021 | Natural language queries via CLI with semantic search |
| FR-022 | LLM synthesis using retrieved chunks as context |
| FR-023 | Source citations (file path, chunk location) in answers |
| FR-024 | Retrieval-only mode without LLM synthesis |
| FR-025 | Indicate when no relevant content is found |

### Configuration & CLI

| ID | Requirement |
|----|-------------|
| FR-026 | XDG-compliant configuration paths |
| FR-027 | `init` command creates default configuration |
| FR-028 | `status` command with index statistics |
| FR-029 | `config validate` command |
| FR-030 | Rotating log files with configurable verbosity |

## Configuration Schema

Configuration lives at `$XDG_CONFIG_HOME/kris/config.toml`.

```toml
# Sources — one or more directories to scan
[sources.my-code]
name = "Source Code"
type = "local"
base_path = "~/src"
exclude_patterns = ["target", "node_modules", ".git", ".venv"]
include_default_exclude_patterns = true  # merge with built-in 33 patterns

[[sources.my-code.schedules]]
path_pattern = "**"
interval_minutes = 60
priority = 1

# Models
[models.embedding]
name = "BAAI/bge-base-en-v1.5"
dimensions = 768
vram_gb = 0.5

[models.llm]
name = "my-local-llm"
model_path = "/path/to/model.gguf"
vram_gb = 8.0

# OpenSearch vector store
[opensearch]
url = "https://localhost:9200"
username = "admin"
password = ""
verify_certs = false
index_prefix = "kris"

# Storage (optional — defaults to XDG paths)
data_dir = ""     # default: ~/.local/share/kris
cache_dir = ""    # default: ~/.cache/kris
log_level = "INFO"
```

### Key Entities

| Entity | Description |
|--------|-------------|
| **Source** | Configured directory with base path, excludes, schedules |
| **File** | Catalog entry at a specific path on a specific source |
| **Content** | File substance identified by SHA-256 hash; owns artifacts |
| **Task** | Processing work unit (extract, chunk, embed) with retry |
| **Chunk** | Segment of extracted text with offsets and strategy metadata |
| **Embedding** | Chunk ↔ OpenSearch vector linkage with model identifier |

## Data Storage

| Location | Default Path | Contents |
|----------|-------------|----------|
| Config | `~/.config/kris/` | `config.toml` |
| Data | `~/.local/share/kris/` | `catalog.db`, `kris.log` |
| Cache | `~/.cache/kris/` | (vector data stored in OpenSearch) |

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Scanner | Rust (walkdir, sha2, rusqlite, clap) |
| Scanner ↔ Core IPC | SQLite (shared catalog.db) |
| Processing & CLI | Python (Typer, Rich, sentence-transformers, llama-cpp-python) |
| Code chunking | tree-sitter |
| Vector store | OpenSearch (external service) |
| Metadata store | SQLite (WAL mode) |
| Configuration | TOML |

## CLI Commands

| Command | Description |
|---------|-------------|
| `kris init` | Create default config file |
| `kris index` | Scan sources, extract, chunk, embed |
| `kris query <text>` | Semantic search + LLM synthesis |
| `kris retrieve <text>` | Semantic search without LLM |
| `kris status` | Show index statistics (use `--show-failed` for failure table) |
| `kris diagnose` | Show failure/skip aggregations and suggested excludes |
| `kris config validate` | Validate configuration and show effective excludes |
| `kris config update-model-sizes` | Measure GPU VRAM per model and update config |
| `kris duplicates` | List content-addressed duplicates |
| `kris cleanup` | Remove archived file artifacts |

All commands support `--json` for structured output. Global flags:
`--verbose` / `-v` (repeatable), `--config <path>`.

## Success Criteria

| ID | Criterion |
|----|-----------|
| SC-001 | Scan 1,000 files cataloged within 60s on local SSD |
| SC-002 | Incremental re-index (<10 changed files) within 30s excl. model load |
| SC-003 | Query answered within 30s excl. model load for 10,000 chunks |
| SC-004 | All eligible files processed with zero manual intervention |
| SC-005 | Duplicate files share artifacts — no redundant chunks/embeddings |
| SC-006 | Deleted files remain searchable until explicit cleanup |
| SC-007 | Installation to first query in under 10 minutes using docs |
| SC-008 | Day-zero scan of 100,000+ files without crashing |

## Assumptions

- NVIDIA GPU with 16 GB VRAM (4090 Super) for model loading
- OpenSearch runs as an external service
- Scanner (Rust) and core (Python) share SQLite catalog
- NAS paths mounted at `/gratch` treated as local sources
- Default embedding model: BAAI/bge-base-en-v1.5 (768 dimensions)
- LLM synthesis via local GGUF model (llama-cpp-python)
- Scanning is on-demand via `kris index` (no background daemon in MVP)
- Single user, single machine
