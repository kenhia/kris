# Transition Plan: Qdrant → OpenSearch

## Overview

This plan covers the concrete steps to replace Qdrant with OpenSearch in the kris codebase. The migration is scoped to preserve all existing functionality while laying the foundation for OpenSearch-native capabilities in future sprints.

**Principle**: SQLite remains the canonical metadata store and scanner IPC layer. OpenSearch replaces Qdrant as the vector store *and* becomes the full-text search engine. This is additive, not a wholesale storage migration — SQLite and OpenSearch serve complementary roles.

---

## Phase 0: Infrastructure Setup

### 0.1 — OpenSearch Docker deployment

**Action**: Create a `docker-compose.yml` for local development and production use.

```yaml
# Minimal single-node OpenSearch for kris
services:
  opensearch:
    image: opensearchproject/opensearch:2.19.1
    environment:
      - discovery.type=single-node
      - DISABLE_SECURITY_PLUGIN=true    # local-only; no auth needed
      - OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m
    ports:
      - "9200:9200"
    volumes:
      - opensearch-data:/usr/share/opensearch/data

volumes:
  opensearch-data:
```

> **Security note**: `DISABLE_SECURITY_PLUGIN=true` is appropriate for localhost-only personal use. If remote access is ever needed, re-enable the security plugin and configure authentication. This matches kris's existing "local-only by default" security posture.

**Deliverable**: `docker-compose.yml` in repo root, documented in `docs/setup.md`.

### 0.2 — Python dependency swap

**Action**: Replace `qdrant-client` with `opensearch-py` in `pyproject.toml`.

```diff
- "qdrant-client>=1.14",
+ "opensearch-py>=3.0",
```

Run `uv lock` to regenerate the lockfile.

---

## Phase 1: OpenSearch Client & Index Management

### 1.1 — Create OpenSearch client factory

**File**: `src/kris/processing/opensearch_client.py` (new)

Replaces `create_qdrant_client()` from `embed.py`. Responsibilities:
- Create and return an `OpenSearch` client instance from config
- Health check on connection
- Index creation with proper mapping (k-NN vector field + metadata fields)

```python
from opensearchpy import OpenSearch

def create_opensearch_client(config: KrisConfig) -> OpenSearch:
    """Create an OpenSearch client from configuration."""
    return OpenSearch(
        hosts=[config.opensearch.url],
        use_ssl=False,
        verify_certs=False,
    )
```

### 1.2 — Define index mapping

**Index name**: `kris_chunks` (matches existing Qdrant collection name for conceptual continuity)

```python
INDEX_MAPPING = {
    "settings": {
        "index": {
            "knn": True,
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }
    },
    "mappings": {
        "properties": {
            "content_hash": {"type": "keyword"},
            "chunk_id": {"type": "keyword"},
            "chunk_index": {"type": "integer"},
            "content": {
                "type": "text",
                "analyzer": "standard",
            },
            "chunking_strategy": {"type": "keyword"},
            "file_kind": {"type": "keyword"},
            "source_id": {"type": "keyword"},
            "file_path": {"type": "keyword"},
            "embedding": {
                "type": "knn_vector",
                "dimension": 768,  # configured from model
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "lucene",
                },
            },
        }
    },
}
```

### 1.3 — `ensure_index()` function

Replaces `ensure_collection()`. Creates the index with the mapping if it doesn't exist.

---

## Phase 2: Embedding Pipeline Migration

### 2.1 — Rewrite `embed_chunks()` in `embed.py`

**Current flow**:
1. Load chunks from SQLite
2. Encode with sentence-transformers
3. Create Qdrant `PointStruct` objects
4. `client.upsert()` to Qdrant
5. Write `Embedding` records to SQLite

**New flow**:
1. Load chunks from SQLite (unchanged)
2. Encode with sentence-transformers (unchanged)
3. Build OpenSearch bulk index actions
4. `helpers.bulk()` to OpenSearch
5. Write `Embedding` records to SQLite (update field names)

Key changes:
- Replace `PointStruct` with OpenSearch document dicts
- Replace `client.upsert(collection_name=..., points=...)` with `helpers.bulk(client, actions)`
- Each document includes chunk text content alongside the vector (enabling future hybrid search)
- UUID generation for document `_id` works the same way

```python
actions = []
for row, vector in zip(rows, embeddings):
    doc_id = str(uuid.uuid4())
    actions.append({
        "_index": INDEX_NAME,
        "_id": doc_id,
        "_source": {
            "content_hash": content_hash,
            "chunk_id": row["id"],
            "chunk_index": row["chunk_index"],
            "chunking_strategy": row["chunking_strategy"],
            "content": row["content"],  # full-text searchable
            "embedding": vector.tolist(),
        },
    })

from opensearchpy import helpers
helpers.bulk(client, actions)
```

### 2.2 — Rewrite `delete_points()` → `delete_documents()`

Replace Qdrant point deletion with OpenSearch bulk delete:
```python
def delete_documents(client: OpenSearch, doc_ids: list[str]) -> int:
    actions = [{"_op_type": "delete", "_index": INDEX_NAME, "_id": did} for did in doc_ids]
    helpers.bulk(client, actions, raise_on_error=False)
    return len(doc_ids)
```

### 2.3 — Update `Embedding` model

In `src/kris/catalog/models.py`:
```diff
- qdrant_point_id: str
+ opensearch_doc_id: str
```

In `src/kris/catalog/db.py`, update the `embedding` table schema:
```diff
- qdrant_point_id TEXT NOT NULL
+ opensearch_doc_id TEXT NOT NULL
```

---

## Phase 3: Retriever Migration

### 3.1 — Rewrite `retrieve()` in `retriever.py`

**Current flow**:
1. Encode query with sentence-transformers
2. `client.query_points()` on Qdrant
3. Iterate results, enrich each with SQLite metadata via `_get_chunk_metadata()`

**New flow**:
1. Encode query with sentence-transformers (unchanged)
2. OpenSearch k-NN query:
   ```python
   body = {
       "query": {
           "knn": {
               "embedding": {
                   "vector": query_vector,
                   "k": top_k,
               }
           }
       },
       "_source": ["content_hash", "chunk_id", "chunk_index", "content",
                    "chunking_strategy", "file_kind", "source_id", "file_path"],
   }
   response = client.search(index=INDEX_NAME, body=body)
   ```
3. Build results from OpenSearch response `_source` fields
4. Enrich with SQLite for fields not in OpenSearch (source_name, ancestor context)

**Filter support** — pre_filter on k-NN:
```python
if source_filter or kind_filter:
    bool_filter = {"bool": {"must": []}}
    if source_filter:
        bool_filter["bool"]["must"].append({"term": {"source_id": source_filter}})
    if kind_filter:
        bool_filter["bool"]["must"].append({"term": {"file_kind": kind_filter}})
    body["query"]["knn"]["embedding"]["filter"] = bool_filter
```

### 3.2 — Simplify `_get_chunk_metadata()`

With file_kind, source_id, file_path, and chunk content now returned from OpenSearch, the SQLite join reduces to fetching `source.name` (for display) and any fields not indexed in OpenSearch.

---

## Phase 4: Configuration Migration

### 4.1 — Update config schema

In `src/kris/config/schema.py`:

```diff
- @dataclass
- class QdrantConfig:
-     mode: str = "embedded"
-     url: str = "http://localhost:6333"
-     api_key: str = ""

+ @dataclass
+ class OpenSearchConfig:
+     url: str = "http://localhost:9200"
+     index_prefix: str = "kris"
```

In `KrisConfig`:
```diff
- qdrant: QdrantConfig = field(default_factory=QdrantConfig)
+ opensearch: OpenSearchConfig = field(default_factory=OpenSearchConfig)
```

Remove the `qdrant_path` property. Add:
```python
@property
def opensearch_index(self) -> str:
    return f"{self.opensearch.index_prefix}_chunks"
```

### 4.2 — Update config TOML parsing

Update `load_config()` to parse `[opensearch]` instead of `[qdrant]`.

### 4.3 — Update `kris init` default config

Replace the `[qdrant]` section in the default config template.

---

## Phase 5: CLI & Command Updates

### 5.1 — `kris index`

Update to pass OpenSearch client instead of qdrant_path. The overall flow (plan tasks → execute pipeline) is unchanged.

### 5.2 — `kris query` / `kris retrieve`

Update to create OpenSearch client from config and pass to retriever.

### 5.3 — `kris cleanup`

Update `delete_points()` calls to `delete_documents()`.

### 5.4 — `kris status`

Consider: query OpenSearch for index stats (document count, store size) alongside SQLite catalog stats. This is an enhancement, not a migration requirement.

### 5.5 — `kris diagnose`

Add OpenSearch connectivity check alongside existing checks.

---

## Phase 6: Test Migration

### 6.1 — Unit tests

Tests that mock Qdrant client interactions need to mock OpenSearch client instead:
- `test_catalog.py` — if it tests embedding flows
- `test_extract.py`, `test_chunk.py` — likely unchanged (no Qdrant dependency)
- Any test importing from `qdrant_client` or mocking Qdrant

### 6.2 — Integration tests

- `test_index_flow.py` — needs OpenSearch running (Docker) or mocked
- `test_query_flow.py` — same
- `test_scanner.py` — likely unchanged (scanner doesn't touch Qdrant)

**Test strategy**: Use `pytest-docker` or a test fixture that starts OpenSearch in Docker for integration tests. For unit tests, mock the OpenSearch client.

---

## Phase 7: Data Migration (Existing Indexes)

### 7.1 — Re-indexing approach

Since kris already has incremental indexing, the simplest migration path is:
1. Stand up OpenSearch
2. Clear processing status in SQLite catalog (`UPDATE content SET processing_status = 'pending' WHERE processing_status = 'complete'`)
3. Run `kris index` — all content re-extracts, re-chunks, re-embeds into OpenSearch

This ensures OpenSearch documents include chunk text content (which Qdrant points don't have), creating a clean starting state for hybrid search.

### 7.2 — Qdrant data cleanup

After verifying OpenSearch indexing works:
1. Remove `~/.cache/kris/qdrant/` directory
2. Remove `qdrant-client` from environment if not done already

---

## Phase 8: Documentation Updates

Apply all changes cataloged in `02-architecture-changes.md`:
- `docs/architecture.md`
- `docs/data-model.md`
- `docs/specification.md`
- `docs/planning/sprint-planning.md`
- `specs/001-mvp-core/*`
- `specs/002-production-hardening/*` (B008 resolution)
- `specs/backlog.md` (close B008)
- `.github/agents/copilot-instructions.md`
- `CONTRIBUTING.md`
- `pyproject.toml`

---

## Execution Order & Dependencies

```
Phase 0 (Infrastructure)
  ├── 0.1 Docker setup
  └── 0.2 Dependency swap
          │
Phase 1 (Client & Index) ← depends on Phase 0
  ├── 1.1 Client factory
  ├── 1.2 Index mapping
  └── 1.3 ensure_index()
          │
Phase 2 (Embed pipeline) ← depends on Phase 1
  ├── 2.1 embed_chunks() rewrite
  ├── 2.2 delete_documents()
  └── 2.3 Model/schema updates
          │
Phase 3 (Retriever) ← depends on Phase 1
  ├── 3.1 retrieve() rewrite
  └── 3.2 Simplify metadata enrichment
          │
Phase 4 (Config) ← independent, can parallel Phase 1
  ├── 4.1 Schema dataclasses
  ├── 4.2 TOML parsing
  └── 4.3 kris init template
          │
Phase 5 (CLI) ← depends on Phases 2, 3, 4
  ├── 5.1–5.5 Command updates
          │
Phase 6 (Tests) ← depends on Phase 5
  ├── 6.1 Unit test migration
  └── 6.2 Integration test setup
          │
Phase 7 (Data) ← depends on Phase 6 passing
  ├── 7.1 Re-index
  └── 7.2 Qdrant cleanup
          │
Phase 8 (Docs) ← can parallel Phase 5+
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| OpenSearch Docker adds operational complexity vs. Qdrant embedded | Medium | Low | Single container, simple compose file, same as planned B008 Qdrant server migration |
| Re-indexing 745K+ files takes significant time | Medium | Medium | Incremental — only re-embed, don't re-extract/re-chunk if chunks exist in SQLite |
| OpenSearch k-NN recall differs from Qdrant HNSW | Low | Medium | Both use HNSW; Lucene engine in OpenSearch is well-tested. Benchmark before/after on a sample. |
| Memory footprint of OpenSearch JVM | Low | Low | 512MB–1GB JVM heap sufficient for single-user personal use at this scale |
| Test infrastructure needs Docker | Low | Low | Already needed for Qdrant server mode (B008). CI/CD pipelines commonly support Docker. |

---

## What This Replaces

| Removed | Replaced By |
|---------|-------------|
| `qdrant-client` Python package | `opensearch-py` Python package |
| `QdrantConfig` dataclass | `OpenSearchConfig` dataclass |
| `create_qdrant_client()` factory | `create_opensearch_client()` factory |
| `ensure_collection()` | `ensure_index()` |
| `PointStruct` creation in embed | OpenSearch bulk document dicts |
| `client.upsert()` | `helpers.bulk()` |
| `client.query_points()` | `client.search()` with k-NN query |
| `client.delete()` with `PointIdsList` | `helpers.bulk()` with delete actions |
| `~/.cache/kris/qdrant/` data directory | Docker volume `opensearch-data` |
| `qdrant_point_id` in EMBEDDING table | `opensearch_doc_id` in EMBEDDING table |
| Qdrant embedded mode fallback | N/A (OpenSearch always runs as server) |

---

## Estimated Scope

| Phase | Files Modified | New Files | Complexity |
|-------|---------------|-----------|------------|
| Phase 0 | 1 (pyproject.toml) | 1 (docker-compose.yml) | Trivial |
| Phase 1 | 0 | 1 (opensearch_client.py) | Low |
| Phase 2 | 2 (embed.py, models.py) + 1 (db.py) | 0 | Medium |
| Phase 3 | 1 (retriever.py) | 0 | Medium |
| Phase 4 | 2 (schema.py, defaults.py) | 0 | Low |
| Phase 5 | ~5 CLI commands | 0 | Low |
| Phase 6 | ~5 test files | 0 | Medium |
| Phase 7 | 0 | 0 | Operational |
| Phase 8 | ~10 docs | 0 | Low |
