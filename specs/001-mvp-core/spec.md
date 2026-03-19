# Feature Specification: MVP Core — Local Scan, Index, Embed, Query

**Feature Branch**: `001-mvp-core`
**Created**: 2026-03-19
**Status**: Draft
**Input**: MVP: Local scan, index, embed, and query personal files via CLI

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Scan and Index Local Files (Priority: P1)

As a user, I want to point kris at one or more directories on my local
machine and have it scan, extract, chunk, and embed the text-based files
it finds, so that I have a searchable index of my personal data.

**Why this priority**: Without scanning and indexing, nothing else works.
This is the foundation of the entire system.

**Independent Test**: Configure a source pointing at a directory with
a mix of text, code, and markdown files. Run `kris index`. Verify that
files are cataloged in SQLite, chunks are created, and embeddings are
stored in Qdrant.

**Acceptance Scenarios**:

1. **Given** a configured source with `base_path` pointing to a directory
   containing text, code, and markdown files, **When** the user runs
   `kris index`, **Then** the scanner discovers all files, catalogs them
   in SQLite with correct file_kind, and creates processing tasks.

2. **Given** a directory with 100 mixed files, **When** `kris index`
   completes, **Then** text/code/markdown files have chunks and
   embeddings in Qdrant, and all files (including binary/unknown) have
   catalog entries with metadata.

3. **Given** a previously indexed directory where 3 files have changed
   and 2 are new, **When** the user runs `kris index` again, **Then**
   only the 5 changed/new files are reprocessed; unchanged files are
   skipped.

4. **Given** a file that exceeds the configured size limit (default
   100 MB), **When** the scanner encounters it, **Then** the file is
   cataloged with metadata but marked as `skipped` for processing.

---

### User Story 2 — Query My Files (Priority: P1)

As a user, I want to ask natural language questions about my indexed
files and get answers with source citations, so that I can find
information across my personal data without remembering where I put it.

**Why this priority**: Querying is the primary user-facing value.
Combined with US1, this delivers a complete vertical slice.

**Independent Test**: After indexing a set of files, run
`kris query "how does the config system work?"` and verify that the
response includes relevant content from the indexed files with file
path citations.

**Acceptance Scenarios**:

1. **Given** an indexed directory containing source code and markdown
   notes, **When** the user runs `kris query "how does authentication
   work?"`, **Then** the system returns an LLM-synthesized answer
   grounded in the indexed content with source file citations.

2. **Given** an indexed directory, **When** the user runs
   `kris query --show-sources "config parsing"`, **Then** the system
   shows both the synthesized answer and the individual source chunks
   that were used to generate it.

3. **Given** a query that has no relevant matches in the index,
   **When** the user runs `kris query "quantum physics equations"`,
   **Then** the system indicates that no relevant content was found
   rather than hallucinating an answer.

4. **Given** an indexed directory, **When** the user runs
   `kris retrieve "error handling"`, **Then** the system returns
   relevant chunks without LLM synthesis (retrieval-only mode).

---

### User Story 3 — Configure Sources and Scan Schedules (Priority: P2)

As a user, I want to configure which directories to scan and how
frequently each should be scanned, so that high-churn directories
(code) are scanned more often than stable archives (photos).

**Why this priority**: Configuration is essential for a usable system
but the MVP can initially work with a minimal config. This story
enriches the experience.

**Independent Test**: Create a config with two sources having different
scan intervals. Run `kris index` and verify both sources are scanned.
Verify that `kris status` shows per-source statistics.

**Acceptance Scenarios**:

1. **Given** a configuration file with two sources (e.g., `~/src` with
   60-minute interval and `/gratch/documents` with daily interval),
   **When** the user runs `kris index`, **Then** both sources are
   scanned and files from each are cataloged with the correct
   `source_id`.

2. **Given** no configuration file exists, **When** the user runs
   `kris init`, **Then** a default configuration file is created at
   the XDG-compliant location with sensible defaults and inline
   comments explaining each option.

3. **Given** a configuration with exclude patterns (e.g.,
   `node_modules`, `.git`), **When** the scanner runs, **Then**
   matching files and directories are skipped entirely.

---

### User Story 4 — View Index Status (Priority: P2)

As a user, I want to see the current state of my index — how many
files are cataloged, how many are indexed, how many failed — so that
I can understand what kris knows about my data.

**Why this priority**: Observability is important for trust. Users
need to know the system is working correctly, especially during
the initial "day zero" scan that may take days.

**Independent Test**: After indexing, run `kris status` and verify
the output shows file counts by source, by kind, and by processing
status.

**Acceptance Scenarios**:

1. **Given** an indexed directory with 50 text files, 30 code files,
   and 20 binary files, **When** the user runs `kris status`, **Then**
   the output shows totals per source, per file kind, and per
   processing status (complete, skipped, failed, pending).

2. **Given** an index with some failed files, **When** the user runs
   `kris status`, **Then** failed files are listed with their error
   reasons.

---

### User Story 5 — Content-Addressed Dedup (Priority: P3)

As a user, I want the system to recognize when the same file content
exists in multiple locations and share processing artifacts, so that
storage is not wasted and I can identify duplicates.

**Why this priority**: Dedup is architecturally important (it's baked
into the data model), but the user-facing duplicate detection tooling
can be basic in the MVP.

**Independent Test**: Copy a file to two different indexed directories.
Run `kris index`. Verify that only one set of chunks/embeddings exists
and that `kris status` can report the duplicate.

**Acceptance Scenarios**:

1. **Given** two configured sources where the same file (identical
   content) exists in both, **When** `kris index` processes both,
   **Then** only one set of chunks and embeddings is created, and
   both file catalog entries reference the same content_hash.

2. **Given** an index with duplicate files, **When** the user runs
   `kris duplicates`, **Then** the system lists groups of files that
   share the same content, with paths and sources.

---

### User Story 6 — Archive and Cleanup (Priority: P3)

As a user, I want files that are deleted from disk to be preserved
in the index (not auto-deleted), and I want CLI tools to review
and clean up archived entries when I choose.

**Why this priority**: The "nothing is lost" principle is
architecturally mandated, but the cleanup tooling can be basic
in the MVP.

**Independent Test**: Index a directory, delete a file from disk,
re-run `kris index`. Verify the file is marked `missing` but its
artifacts remain. Then use `kris cleanup` to remove it.

**Acceptance Scenarios**:

1. **Given** a previously indexed file that no longer exists on disk,
   **When** `kris index` runs, **Then** the file's visibility is
   changed to `missing` with a `disappeared_at` timestamp, and all
   artifacts (chunks, embeddings) are preserved.

2. **Given** missing files in the catalog, **When** the user runs
   `kris cleanup --older-than 30d`, **Then** files missing for more
   than 30 days are removed along with their artifacts, and the user
   is shown what will be removed before confirmation.

3. **Given** missing files in the catalog, **When** the user runs
   `kris cleanup --path "old-project/"`, **Then** only missing files
   matching the path pattern are removed.

---

### Edge Cases

- What happens when the scanner encounters a symlink loop?
  The scanner respects `follow_symlinks = false` by default and
  skips symlinks. If enabled, cycle detection prevents infinite loops.

- What happens when a file is modified during scanning?
  The scanner uses mtime + content_hash. If the hash computed during
  scan differs from a subsequent read during extraction, the file is
  re-queued for the next scan cycle.

- What happens when Qdrant is unavailable?
  Tasks requiring Qdrant fail and are marked for retry. The catalog
  and extraction steps still complete, so progress is not lost.

- What happens when VRAM is insufficient to load the embedding model?
  The system reports an error with the model's VRAM requirement and
  available VRAM, and suggests configuration changes.

- What happens with files that have no text content (e.g., empty files)?
  Empty files are cataloged but skipped for processing (no chunks
  to create).

- What happens when the SQLite database is corrupted?
  The system detects corruption on startup and reports the error.
  Recovery is manual (restore from backup or re-index).


## Requirements *(mandatory)*

### Functional Requirements

**Scanning & Catalog**

- **FR-001**: System MUST scan configured local directories recursively,
  discovering all files.
- **FR-002**: System MUST compute SHA-256 content hashes for change
  detection.
- **FR-003**: System MUST classify files by kind (text, code, markdown,
  image, config, binary, unknown, etc.) using extension and heuristics.
- **FR-004**: System MUST catalog every discovered file with metadata
  (path, size, mtime, kind, mime_type, permissions) regardless of
  whether it will be processed.
- **FR-005**: System MUST support incremental scanning — only new or
  changed files (by content_hash) trigger reprocessing.
- **FR-006**: System MUST respect configured exclude patterns
  (directories and file patterns).
- **FR-007**: System MUST support multiple configured sources, each
  with independent base_path and exclude patterns.
- **FR-008**: System MUST mark files exceeding the configured size
  limit as `skipped` while still recording their metadata.

**Content-Addressed Dedup**

- **FR-009**: System MUST use content_hash as the key for processing
  artifacts. Files with identical content across sources or paths
  MUST share chunks, embeddings, and summaries.
- **FR-010**: System MUST provide a way to list groups of files that
  share the same content (duplicate detection).

**Processing Pipeline**

- **FR-011**: System MUST extract text from text, code, markdown,
  and config files.
- **FR-012**: System MUST chunk extracted text using file-kind-aware
  strategies (code-aware chunking for code, semantic splitting for
  text/markdown).
- **FR-013**: System MUST generate vector embeddings for each chunk
  using a configured embedding model.
- **FR-014**: System MUST store embeddings in Qdrant with payload
  metadata (content_hash, file_kind, chunk_index). File paths and
  source IDs are resolved at query time by joining content_hash back
  to SQLite, ensuring deduped content returns all associated paths.
- **FR-015**: System MUST persist chunk records in SQLite with content,
  offsets, and strategy-specific metadata.
- **FR-016**: System MUST implement a task planner that generates
  appropriate processing tasks (extract → chunk → embed) based on
  file kind.
- **FR-017**: System MUST order tasks to minimize embedding model
  load/unload cycles.

**Archival & Cleanup**

- **FR-018**: System MUST mark files not seen in the latest scan as
  `missing` with a timestamp rather than deleting them or their
  artifacts.
- **FR-019**: System MUST provide CLI commands to clean up missing
  files using selectors (path pattern, age, source).
- **FR-020**: System MUST require user confirmation before deleting
  archived artifacts.

**Query & Retrieval**

- **FR-021**: System MUST support natural language queries via CLI
  that perform semantic search against embedded chunks.
- **FR-022**: System MUST synthesize answers using a local LLM with
  retrieved chunks as context.
- **FR-023**: System MUST display source citations (file path, chunk
  location) alongside synthesized answers.
- **FR-024**: System MUST support retrieval-only mode (return chunks
  without LLM synthesis).
- **FR-025**: System MUST indicate when no relevant content is found
  rather than generating unsupported answers.

**Configuration & CLI**

- **FR-026**: System MUST use XDG-compliant configuration paths.
- **FR-027**: System MUST provide an `init` command that creates a
  default configuration file.
- **FR-028**: System MUST provide a `status` command showing index
  statistics (files by source, kind, status).
- **FR-029**: System MUST provide a `config validate` command that
  checks configuration for errors.
- **FR-030**: System MUST log operations with configurable verbosity
  and rotating log files.

### Key Entities

- **Source**: A configured directory to scan, with its own base path,
  exclude patterns, and scan schedule. Identified by a stable user-
  assigned ID.

- **File**: A catalog entry for a discovered file at a specific path
  on a specific source. Tracks location, metadata, and visibility.
  Many files can reference the same content.

- **Content**: The substance of a file, identified by content_hash.
  Owns all processing artifacts. Supports a parent chain for
  environment context.

- **Task**: A unit of processing work (extract, chunk, embed) with
  status tracking, retry logic, and model affinity hints.

- **Chunk**: A semantically meaningful segment of extracted text,
  with offsets, strategy metadata, and content hash.

- **Embedding**: The linkage between a chunk and its vector
  representation in Qdrant, including the model used.


## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: User can scan a directory of 1,000 files and have all
  discoverable files cataloged within 60 seconds on local SSD storage.

- **SC-002**: User can run incremental re-index on a directory where
  fewer than 10 files changed and have processing complete within
  30 seconds (excluding model load time).

- **SC-003**: User can ask a natural language question and receive a
  sourced answer within 30 seconds (excluding model load time) for
  an index of 10,000 chunks.

- **SC-004**: All text, code, and markdown files under the configured
  size limit are processed with zero manual intervention after initial
  configuration.

- **SC-005**: Duplicate files across configured sources share
  processing artifacts — no redundant chunks or embeddings for
  identical content.

- **SC-006**: Files deleted from disk remain searchable until the user
  explicitly cleans them up.

- **SC-007**: A user unfamiliar with the system can go from
  installation to first successful query in under 10 minutes using
  only the setup guide and CLI help.

- **SC-008**: System handles a "day zero" initial scan of 100,000+
  files without crashing, with progress visible via `kris status`.


## Assumptions

- The user has a local NVIDIA GPU with sufficient VRAM (16 GB,
  4090 Super) for loading the embedding model and LLM simultaneously
  or via hot-swap.
- Qdrant runs locally (embedded or as a local service).
- The scanner binary (Rust) and the processing/query engine (Python)
  communicate via the shared SQLite catalog database.
- NAS paths mounted at `/gratch` are treated as local filesystem
  sources — no special NAS protocol handling.
- The initial embedding model is `BAAI/bge-base-en-v1.5` (768
  dimensions) unless configured otherwise.
- The LLM for synthesis is a local GGUF model loaded via llama-cpp.
- Scan schedules are defined in configuration but the MVP runs
  scanning on-demand via `kris index` (no background daemon).
- The MVP targets a single user on a single machine.
