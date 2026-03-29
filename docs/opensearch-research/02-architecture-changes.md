# Architecture & Planning Doc Changes for OpenSearch Migration

## Overview

This document catalogs every architecture and planning document that references Qdrant or assumes the Qdrant + SQLite FTS5 dual-storage model, and describes the specific changes needed in each.

---

## 1. docs/architecture.md

### Section: High-Level Architecture (Mermaid diagram)

**Current**: `QDRANT["Qdrant<br/>(Vectors)"]` in the Storage subgraph. Data flow shows `EMBED --> QDRANT` and `QUERY --> QDRANT`.

**Change**: Replace `QDRANT` node with `OPENSEARCH["OpenSearch<br/>(Vectors + Full-Text + Structured)"]`. Update data flows:
- `EMBED --> OPENSEARCH`
- `EXTRACT --> OPENSEARCH` (full-text content now also indexed in OpenSearch)
- `CHUNK --> SQLITE` remains (chunk records as source of truth) but chunk content also flows to OpenSearch
- `QUERY --> OPENSEARCH` (single search backend)
- `QUERY --> SQLITE` remains for catalog metadata not stored in OpenSearch

### Section: Artifact Storage (Section 6)

**Current table**:
| Artifact Type | Storage | Rationale |
|---|---|---|
| Vectors/embeddings | Qdrant | Purpose-built for vector similarity search |

**Change**: Replace with:
| Artifact Type | Storage | Rationale |
|---|---|---|
| Vectors/embeddings | OpenSearch | k-NN vector search with filtered ANN |
| Chunk full-text content | OpenSearch | BM25 + hybrid search in same index as vectors |
| File metadata (searchable) | OpenSearch | Enables aggregations, filtered search, dashboards |
| File metadata (canonical) | SQLite | Source of truth for catalog, scanner IPC, task state |
| Chunk records (canonical) | SQLite | Source of truth, linked to files |
| Summaries | SQLite + OpenSearch | SQLite for storage, OpenSearch for search |

**Current "Qdrant collection strategy"** and **"Qdrant deployment modes"** subsections — replace entirely with OpenSearch index strategy:
- Index design: `kris_chunks` index with k-NN vector fields, full-text fields, and structured metadata fields
- Mapping: `text_embedding` (k-NN), `content` (text with BM25 analyzer), `content_hash`, `chunk_index`, `file_kind`, `source_id`, `file_path`, etc.
- Deployment: single-node Docker (default), multi-node cluster (optional for scale)

### Section: Query & Serve Layer (Section 7)

**Current**: Retriever queries Qdrant for vector similarity, then enriches with SQLite metadata.

**Change**: Retriever queries OpenSearch with hybrid query (vector + BM25), receiving both vector-similar and keyword-matching results in a single scored, normalized response. SQLite enrichment reduces to catalog-only lookups (ancestors, processing state) — file paths, kinds, source IDs come from OpenSearch directly.

**Query modes** section — update:
- **Semantic search**: k-NN query against OpenSearch vector fields
- **Hybrid search**: Native `hybrid` query type combining k-NN + BM25 (replaces "BM25 or SQLite FTS" note)
- **Full-text search**: BM25 `match` / `multi_match` queries against OpenSearch text fields
- Remove "SQLite FTS" references
- **Multi-collection fusion** → **Multi-field fusion**: search across multiple vector fields (text, code) in same index

### Section: Technology Stack table

**Current**:
| Vector store | Qdrant | Proven in krag, named vectors, filtered search |

**Change**:
| Search & vector store | OpenSearch | Unified vector search, full-text search, hybrid queries, aggregations, dashboards |

### Section: MVP Scope / MVP Delivers

**Current**: "Store vectors in Qdrant with file metadata"

**Change**: "Store vectors and searchable content in OpenSearch; canonical metadata in SQLite"

### Section: Relationship to krag table

**Current**: `QdrantVectorStore (named vectors, filtered ops)` → `Vector storage`

**Change**: `QdrantVectorStore (named vectors, filtered ops)` → `OpenSearch index (hybrid vector + text search)`

---

## 2. docs/data-model.md

### EMBEDDING entity

**Current**:
```
EMBEDDING {
    string id PK
    string chunk_id FK
    string model_id FK
    string collection_name
    string qdrant_point_id
}
```

**Change**: Rename `qdrant_point_id` to `opensearch_doc_id` (the OpenSearch document `_id` that corresponds to this embedding). Update `collection_name` to `index_name`. The EMBEDDING table in SQLite remains as a cross-reference between the SQLite chunk records and their OpenSearch indexed counterparts.

```
EMBEDDING {
    string id PK
    string chunk_id FK
    string model_id FK
    string index_name
    string opensearch_doc_id
}
```

### ER diagram

Update the EMBEDDING entity box in the Mermaid ER diagram to reflect the renamed fields.

---

## 3. docs/specification.md (MVP Core Spec)

### FR-014

**Current**: "Store embeddings in Qdrant; resolve paths via SQLite join"

**Change**: "Store embeddings and searchable chunk content in OpenSearch; canonical metadata in SQLite"

### Configuration Schema

**Current**:
```toml
[qdrant]
mode = "embedded"
# url = "http://localhost:6333"
# api_key = ""
```

**Change**:
```toml
[opensearch]
url = "http://localhost:9200"
# username = ""     # optional, for secured clusters
# password = ""     # optional, for secured clusters
index_prefix = "kris"  # indices will be named kris_chunks, etc.
```

### US1 description

**Current**: "embed chunks into Qdrant"

**Change**: "embed chunks into OpenSearch"

---

## 4. docs/planning/sprint-planning.md

### Sprint 002 — Production Hardening

**Current**: "Qdrant migration from local/embedded mode to server mode (B008)"

**Change**: Replace with "OpenSearch deployment — Docker-based single-node search backend (replaces Qdrant)" or remove if the OpenSearch migration is done as a pre-sprint-002 effort.

### Sprint 003 — Summarization & Hybrid Search

**Current**:
- "Hybrid search: semantic + BM25 full-text (SQLite FTS5)"
- Foundation note about FTS5 index design for Sprint 006

**Change**:
- "Hybrid search: semantic + BM25 full-text (OpenSearch native hybrid query)"
- Update foundation note: OpenSearch replaces FTS5 — full-text index design leverages OpenSearch analyzers and mapping. The n-gram/trigram tokenizer strategy applies to OpenSearch analyzer configuration rather than SQLite FTS5 tokenizer choice.
- "Multi-collection query fusion (Reciprocal Rank Fusion)" → "Multi-field vector search with built-in score normalization"

### Sprint 004 — HTTP API & Multi-Model

**Current**: Multi-model embedding support references Qdrant collections implicitly.

**Change**: Multi-model maps to multiple k-NN fields in the same OpenSearch index (e.g., `text_embedding`, `code_embedding`). Update the API `/search` endpoint note to reference OpenSearch hybrid queries.

### Sprint 006 — Code Search & Literal Indexing

**Current**: Research phase for trigram vs. suffix array, Tantivy vs. FTS5.

**Change**: Research phase significantly reduced — OpenSearch provides BM25, n-gram tokenizers, regex queries natively. The research becomes "which analyzers and tokenizers to configure" rather than "which engine to use."

**Current**: "Literal text search via FTS5 (extend Sprint 003 foundation to standalone search queries)"

**Change**: "Literal text search via OpenSearch full-text queries (extend Sprint 003 hybrid search foundation)"

### Sequencing Rationale

**Current**: References FTS5 foundation from Sprint 003.

**Change**: References OpenSearch full-text index from Sprint 003. The rationale strengthens — since OpenSearch handles both vector and full-text from the start, the dependency chain simplifies.

---

## 5. specs/001-mvp-core/

### spec.md

- FR-014: Update Qdrant references to OpenSearch
- Configuration schema: Replace `[qdrant]` section with `[opensearch]`
- Any references to "embedded mode" for vector store

### plan.md

- Tech stack references to Qdrant
- Deployment notes referencing Qdrant embedded/server modes
- Architecture diagrams if they reference Qdrant

### data-model.md

- EMBEDDING entity: `qdrant_point_id` → `opensearch_doc_id`, `collection_name` → `index_name`

### contracts/cli.md

- Any CLI error messages or help text referencing Qdrant

---

## 6. specs/002-production-hardening/

### spec.md, plan.md, tasks.md

- B008 (Qdrant local mode warning) — either remove entirely or replace with OpenSearch deployment task
- Any references to Qdrant server mode migration

---

## 7. specs/backlog.md

### B008 — Qdrant local mode warning for large collections

**Current**: Full investigation item about Qdrant embedded mode 20K point warning.

**Change**: Close as "resolved by OpenSearch migration" or archive. The issue doesn't exist with OpenSearch — it runs as a server from day one with no embedded mode limitations.

---

## 8. .github/agents/copilot-instructions.md

**Current**: Multiple references to `qdrant-client` in tech stack listings for both 001-mvp-core and 002-production-hardening.

**Change**: Replace `qdrant-client` with `opensearch-py` in all tech stack listings. Update the "SQLite + Qdrant" storage description to "SQLite + OpenSearch."

---

## 9. CONTRIBUTING.md

**Current**: "retriever/Qdrant" in integration boundary list.

**Change**: "retriever/OpenSearch"

---

## 10. pyproject.toml

**Current**: `"qdrant-client>=1.14"` in dependencies.

**Change**: Replace with `"opensearch-py>=3.0"`.

---

## Summary: Change Impact

| Document | Severity | Changes |
|----------|----------|---------|
| docs/architecture.md | **High** | Diagrams, storage section, query layer, tech stack table, MVP scope |
| docs/data-model.md | **Medium** | EMBEDDING entity fields, ER diagram |
| docs/specification.md | **Medium** | FR-014, config schema, US1 |
| docs/planning/sprint-planning.md | **High** | Sprint 002, 003, 004, 006 descriptions; sequencing rationale |
| specs/001-mvp-core/* | **Medium** | Spec, plan, data model, contracts |
| specs/002-production-hardening/* | **Low** | B008 removal/replacement |
| specs/backlog.md | **Low** | Close/archive B008 |
| .github/agents/copilot-instructions.md | **Low** | Tech stack references |
| CONTRIBUTING.md | **Low** | Integration boundary reference |
| pyproject.toml | **Low** | Dependency swap |
