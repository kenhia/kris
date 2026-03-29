# Feature Specification: OpenSearch Transition

**Feature Branch**: `003-opensearch-transition`
**Created**: 2026-03-29
**Status**: Draft
**Input**: User description: "Replace Qdrant with OpenSearch as unified vector + full-text search backend"

## Overview

Replace Qdrant (the dedicated vector database) with OpenSearch as kris's unified search backend. OpenSearch handles vector similarity search (k-NN), full-text search (BM25), and structured metadata queries in a single engine. This consolidation simplifies the architecture, eliminates the Qdrant embedded-mode scaling limitation (B008), and lays the foundation for hybrid search, literal code search, and dashboard capabilities in future sprints.

SQLite remains the canonical metadata store, scanner IPC layer, and task queue. OpenSearch is additive — it replaces Qdrant and absorbs the planned FTS5 role, but does not replace SQLite's catalog function.

## User Scenarios & Testing *(mandatory)*

### US1 — Index Files into OpenSearch (Priority: P1)

As a user, I run `kris index` and my files are scanned, extracted, chunked, embedded, and stored in OpenSearch with both vector embeddings and chunk text content — so that I can later search them via both semantic and keyword queries.

**Why this priority**: Without indexing into OpenSearch, no other functionality works. This is the write path — the foundation for everything else.

**Independent Test**: Configure a source directory with a mix of text, code, and markdown files. Run `kris index`. Verify that OpenSearch contains documents with both embedding vectors and text content for each chunk. Verify that SQLite catalog and chunk records are consistent with OpenSearch document count.

**Acceptance Scenarios**:

1. **Given** a configured source with text/code/markdown files and OpenSearch running, **When** the user runs `kris index`, **Then** chunks are embedded and indexed into OpenSearch with both vector and text fields, and embedding records in SQLite reference the OpenSearch document IDs.
2. **Given** files that were previously indexed, **When** the user runs `kris index` again with no changes, **Then** no duplicate documents are created in OpenSearch and the operation completes quickly (incremental behavior preserved).
3. **Given** a file that has changed since last index, **When** the user runs `kris index`, **Then** old embeddings for that content are removed from OpenSearch and new ones are created.
4. **Given** OpenSearch is not running, **When** the user runs `kris index`, **Then** a clear error message indicates that OpenSearch is unreachable and suggests how to start it.

---

### US2 — Query Files via OpenSearch (Priority: P1)

As a user, I run `kris query "how does the auth module work?"` and receive an LLM-synthesized answer with source citations — with retrieval now powered by OpenSearch vector search instead of Qdrant.

**Why this priority**: Query is the primary user-facing feature. If indexing works but querying doesn't, the system provides no value.

**Independent Test**: After indexing, run `kris query` with a natural language question. Verify that relevant chunks are retrieved via OpenSearch k-NN search, enriched with file metadata, and synthesized into an answer with source citations. Compare result quality against the same query on the Qdrant-backed system.

**Acceptance Scenarios**:

1. **Given** indexed files in OpenSearch, **When** the user runs `kris query "question"`, **Then** relevant chunks are retrieved via vector similarity search, enriched with metadata, and an LLM-synthesized answer with file path citations is displayed.
2. **Given** indexed files in OpenSearch, **When** the user runs `kris retrieve "question"`, **Then** matching chunks are returned with scores, file paths, and kinds — without LLM synthesis.
3. **Given** indexed files, **When** the user queries with `--source` or `--kind` filters, **Then** only chunks matching those filters are returned (pre-filtering on the search query, not post-retrieval).
4. **Given** no indexed content, **When** the user runs `kris query`, **Then** a helpful message indicates no content has been indexed yet.

---

### US3 — Configure OpenSearch Connection (Priority: P1)

As a user, I configure kris to connect to my OpenSearch instance via `config.toml` — replacing the previous Qdrant configuration section.

**Why this priority**: Configuration is required for both indexing and querying. Users must be able to specify where OpenSearch is running.

**Independent Test**: Run `kris init` and verify the generated config contains an `[opensearch]` section with sensible defaults. Edit the URL, run `kris config validate`, and verify it reports the connection status.

**Acceptance Scenarios**:

1. **Given** a fresh install, **When** the user runs `kris init`, **Then** the generated `config.toml` contains an `[opensearch]` section with a default URL, optional username/password fields, and a default index prefix of `kris`.
2. **Given** a config with `[opensearch] url = "https://localhost:9200"`, **When** the user runs `kris config validate` with OpenSearch running, **Then** the validator confirms the connection is healthy.
3. **Given** a config with a `[qdrant]` section (legacy), **When** the user runs any command, **Then** an informative warning or error explains the Qdrant configuration is no longer supported and directs the user to update to `[opensearch]`.
4. **Given** a config with an unreachable OpenSearch URL, **When** the user runs `kris config validate`, **Then** the validator reports the connection failure with an actionable message.

---

### US4 — Clean Up Indexed Content (Priority: P2)

As a user, I run `kris cleanup` to remove artifacts for deleted or archived files — with cleanup now targeting OpenSearch documents instead of Qdrant points.

**Why this priority**: Cleanup is important for long-term operation but not required for initial indexing/querying functionality.

**Independent Test**: Index files, delete some source files, run `kris index` to mark them missing, then run `kris cleanup --missing`. Verify OpenSearch documents for those files are removed and SQLite embedding records are cleaned up.

**Acceptance Scenarios**:

1. **Given** files marked as missing in the catalog, **When** the user runs `kris cleanup --missing --confirm`, **Then** corresponding chunks and embeddings are deleted from OpenSearch and SQLite embedding records are removed.
2. **Given** cleanup selectors (path pattern, source, age), **When** the user runs `kris cleanup` with selectors, **Then** only matching content is removed from OpenSearch.
3. **Given** a cleanup request without `--confirm`, **When** the user runs `kris cleanup`, **Then** a preview of what would be deleted is shown without making changes.

---

### US5 — Diagnose System Health Including OpenSearch (Priority: P2)

As a user, I run `kris diagnose` and see system health information that includes OpenSearch connectivity, index statistics, and document counts — so I can troubleshoot issues.

**Why this priority**: Diagnostics support operational health but are not on the critical path for core functionality.

**Independent Test**: Run `kris diagnose` with OpenSearch running and verify it reports index health, document count, and store size. Run with OpenSearch stopped and verify a clear connectivity error is shown.

**Acceptance Scenarios**:

1. **Given** OpenSearch is running and has indexed content, **When** the user runs `kris diagnose`, **Then** the output includes OpenSearch cluster health, index name, document count, and store size.
2. **Given** OpenSearch is not running, **When** the user runs `kris diagnose`, **Then** the output clearly indicates OpenSearch is unreachable with connection details and suggested remediation.

---

### US6 — Data Migration from Qdrant to OpenSearch (Priority: P2)

As a user who has existing indexed content in Qdrant, I can re-index my content into OpenSearch without losing data — so the transition is seamless.

**Why this priority**: Existing users need a migration path, but since kris has incremental re-indexing, this is an operational procedure rather than new feature code.

**Independent Test**: Start with a working kris installation with Qdrant-indexed content. Follow the migration procedure. Verify all previously indexed content is searchable in OpenSearch with equivalent quality.

**Acceptance Scenarios**:

1. **Given** existing content indexed in Qdrant, **When** the user follows the documented migration procedure (reset processing status + `kris index`), **Then** all content is re-indexed into OpenSearch and queries return equivalent results.
2. **Given** a completed migration, **When** the user queries content that was previously indexed, **Then** result quality is comparable to the Qdrant-based system (same content retrieved for the same queries).

---

### Edge Cases

- What happens when OpenSearch is running but the index doesn't exist yet? The system must create the index with the correct mapping automatically on first use.
- What happens when the OpenSearch index mapping needs to change (e.g., embedding dimension changes)? The system should detect the mismatch and report an actionable error.
- What happens when OpenSearch runs out of disk space during bulk indexing? The error should be caught and reported with the number of successfully indexed documents and the failure reason.
- What happens when the user has both `[qdrant]` and `[opensearch]` sections in config? The system should use `[opensearch]` and warn about the deprecated `[qdrant]` section.
- What happens when OpenSearch is temporarily unavailable during a long indexing run? The system should report the failure for affected batches and allow resumption.
- What happens when the configured embedding model dimensions don't match the existing OpenSearch index mapping? The system should detect the conflict before attempting to index.

## Requirements *(mandatory)*

### Functional Requirements

#### Infrastructure & Deployment

- **FR-001**: System MUST document OpenSearch prerequisites (running instance on localhost, HTTPS, authentication) in `docs/setup.md`.
- **FR-002**: System MUST validate that OpenSearch is reachable and authenticated before any indexing or querying operation, consistent with kris's local-first security posture.
- **FR-003**: System MUST replace the `qdrant-client` dependency with `opensearch-py` in the project's dependency specification.

#### Client & Index Management

- **FR-004**: System MUST provide a client factory that creates an OpenSearch connection from the configuration.
- **FR-005**: System MUST verify OpenSearch connectivity on client creation and produce actionable error messages on failure.
- **FR-006**: System MUST automatically create the search index with the correct mapping (vector field, text field, metadata fields) if it does not exist.
- **FR-007**: System MUST configure the vector field for k-NN similarity search using cosine similarity, with dimension derived from the configured embedding model.

#### Embedding Pipeline

- **FR-008**: System MUST index chunks into OpenSearch with both the embedding vector and the chunk text content in the same document.
- **FR-009**: System MUST include structured metadata fields (content_hash, chunk_id, chunk_index, chunking_strategy, file_kind, source_id, file_path) in each indexed document.
- **FR-010**: System MUST use bulk indexing operations for efficiency when writing multiple documents.
- **FR-011**: System MUST generate a unique document ID for each indexed chunk and record it in the SQLite embedding table.
- **FR-012**: System MUST support deletion of documents from OpenSearch by document ID for cleanup operations.

#### Retrieval

- **FR-013**: System MUST perform vector similarity search (k-NN) against OpenSearch for semantic queries.
- **FR-014**: System MUST support pre-filtering on k-NN queries by source and file kind, applied before vector search rather than after.
- **FR-015**: System MUST enrich search results with file metadata (source name, ancestor context) from SQLite for fields not stored in OpenSearch.
- **FR-016**: System MUST return scored results with chunk text, file path, file kind, source ID, and relevance score.

#### Configuration

- **FR-017**: System MUST replace the `[qdrant]` configuration section with an `[opensearch]` section containing URL, authentication credentials, and index prefix settings.
- **FR-018**: System MUST default to `https://localhost:9200` for the OpenSearch URL and `kris` for the index prefix. Authentication credentials (username, password) MUST be configurable for secured clusters.
- **FR-019**: System MUST update `kris init` to generate configuration with the new `[opensearch]` section.
- **FR-020**: System MUST update `kris config validate` to check OpenSearch connectivity.
- **FR-021**: System MUST produce a warning or error when a legacy `[qdrant]` configuration section is detected.

#### Data Model

- **FR-022**: System MUST update the SQLite embedding table schema to reference OpenSearch document IDs instead of Qdrant point IDs (rename `qdrant_point_id` to `opensearch_doc_id`, `collection_name` to `index_name`).
- **FR-023**: System MUST handle schema migration for existing SQLite databases that have the old column names.

#### CLI Commands

- **FR-024**: System MUST update `kris index` to write embeddings to OpenSearch instead of Qdrant.
- **FR-025**: System MUST update `kris query` and `kris retrieve` to search OpenSearch instead of Qdrant.
- **FR-026**: System MUST update `kris cleanup` to delete documents from OpenSearch instead of Qdrant.
- **FR-027**: System MUST update `kris diagnose` to report OpenSearch health, index statistics, and connectivity status.
- **FR-028**: System MUST update `kris status` to remain functional with the new backend (no degradation in reported statistics).

#### Testing

- **FR-029**: System MUST provide unit tests with mocked OpenSearch client interactions for all modified modules.
- **FR-030**: System MUST provide integration tests that verify the full index-then-query cycle against OpenSearch.

#### Documentation

- **FR-031**: System MUST update architecture, data model, and setup documentation to reflect the OpenSearch backend.
- **FR-032**: System MUST document the migration procedure for users with existing Qdrant-indexed content.

### Key Entities

- **OpenSearch Document**: A single indexed chunk containing: embedding vector, chunk text content, content_hash, chunk_id, chunk_index, file_kind, source_id, file_path, chunking_strategy. Uniquely identified by a document `_id`.
- **OpenSearch Index**: A named collection of documents with a defined mapping (field types, vector dimensions, analyzers). Default name: `{prefix}_chunks` where prefix defaults to `kris`.
- **Embedding Record** (SQLite): Cross-reference linking a SQLite chunk record to its OpenSearch document. Fields: id, chunk_id, model_id, index_name, opensearch_doc_id.
- **OpenSearch Configuration**: Connection settings: URL, username, password, SSL verification, index prefix. Stored in `[opensearch]` section of `config.toml`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All existing CLI commands (`index`, `query`, `retrieve`, `cleanup`, `status`, `diagnose`) work with OpenSearch as the backend — no functional regression from the Qdrant-based system.
- **SC-002**: Semantic search queries return results of equivalent relevance to the Qdrant-based system (same top-5 results for a set of test queries, allowing for minor score differences).
- **SC-003**: Indexing performance supports the existing corpus scale (20K+ chunks) without timeout or memory errors.
- **SC-004**: Source and file-kind filtering on queries operates as pre-filtering (applied before vector search), not post-filtering.
- **SC-005**: OpenSearch documents contain both embedding vectors and chunk text, enabling future hybrid search without re-indexing.
- **SC-006**: The Qdrant Python dependency (`qdrant-client`) is fully removed — no Qdrant imports remain in the codebase.
- **SC-007**: All unit and integration tests pass with the OpenSearch backend.
- **SC-008**: Actionable error messages are displayed when OpenSearch is unreachable, with remediation guidance.
- **SC-009**: A documented migration procedure allows an existing user to transition from Qdrant to OpenSearch in under 30 minutes of hands-on time (excluding re-indexing duration).

## Assumptions

- OpenSearch runs as a Docker container on the same machine as kris. Network latency is negligible (localhost).
- OpenSearch is deployed with the security plugin enabled, using HTTPS and admin credentials. The existing deployment at `/home/ken/opensearch` manages the Docker container and data volume (`/ai/opensearch/data`).
- Re-indexing existing content (rather than attempting a Qdrant-to-OpenSearch data migration) is the preferred migration strategy, since it also populates the new full-text fields that Qdrant documents don't have.
- The embedding model and dimensions remain unchanged during the transition. The same `BAAI/bge-base-en-v1.5` (768 dimensions) model is used.
- OpenSearch JVM memory of 512MB–1GB is sufficient for the current corpus scale (~20K–50K chunks). This may need tuning as the corpus grows.
- The existing SQLite catalog, task queue, and chunk storage remain unchanged. Only the embedding/retrieval layer and its cross-references are modified.
