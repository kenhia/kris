# Research: OpenSearch Transition

**Feature Branch**: `003-opensearch-transition`
**Date**: 2026-03-29
**Source**: Spec, existing codebase inventory, running OpenSearch deployment

---

## R1: OpenSearch Python Client Library

**Decision**: Use `opensearch-py` (v3.x) as the Python client.

**Rationale**: Official Python client maintained by the OpenSearch project. Mirrors the familiar Elasticsearch client API (fork of `elasticsearch-py`). Supports bulk operations, k-NN search, index management, and cluster health checks. 7K+ downstream dependents on PyPI. Used by LangChain, LlamaIndex, and other ML ecosystems.

**Alternatives considered**:
- Raw HTTP via `httpx`/`requests` — too low-level, would require reimplementing retry logic, bulk helpers, and k-NN query DSL.
- `elasticsearch-py` — compatible at the protocol level but diverging in newer API features and not officially supported by OpenSearch.

---

## R2: OpenSearch Deployment Model

**Decision**: Use the existing external OpenSearch deployment managed at `/home/ken/opensearch/docker-compose.yml`. kris does NOT embed or manage OpenSearch — it connects to it as an external service, similar to how it currently connects to Qdrant in server mode.

**Rationale**: The user already has a running OpenSearch + Dashboards stack with:
- Security plugin enabled (HTTPS, admin credentials)
- Data volume at `/ai/opensearch/data` (host bind mount)
- Performance Analyzer on port 9600
- Dashboards on port 5601
- Healthcheck configured

kris should not duplicate or override this deployment. The `docker-compose.yml` stays in `/home/ken/opensearch/` — not in the kris repo. kris's only concern is the connection URL and credentials, configured in `config.toml`.

**Alternatives considered**:
- Ship a kris-specific `docker-compose.yml` in the repo — rejected. The user has an existing deployment with specific volume paths and security config. kris should be a client, not an infrastructure manager. Documentation will reference the setup requirements instead.
- `DISABLE_SECURITY_PLUGIN=true` for simplicity — rejected. The existing deployment uses the security plugin, and kris should respect that. Supporting authenticated connections is minimal additional code in the client factory.

---

## R3: OpenSearch Authentication & TLS

**Decision**: Support HTTPS with username/password authentication. Disable certificate verification by default (self-signed demo certs on localhost).

**Rationale**: The running OpenSearch instance uses the security plugin with HTTPS and `OPENSEARCH_INITIAL_ADMIN_PASSWORD`. The demo certificates are self-signed, so `verify_certs=False` is appropriate for localhost. The `opensearch-py` client supports all of this natively:

```python
OpenSearch(
    hosts=[{"host": "localhost", "port": 9200}],
    http_auth=("admin", password),
    use_ssl=True,
    verify_certs=False,
    ssl_show_warn=False,
)
```

**Configuration schema**:
```toml
[opensearch]
url = "https://localhost:9200"
username = "admin"
password = ""          # read from env var KRIS_OPENSEARCH_PASSWORD if empty
verify_certs = false
index_prefix = "kris"
```

**Security note**: The password should not be committed to config files. Support reading from `KRIS_OPENSEARCH_PASSWORD` environment variable as a fallback when `password = ""`.

**Alternatives considered**:
- API key authentication — not supported by default OpenSearch security plugin without additional setup.
- Mutual TLS — over-engineered for localhost personal use.

---

## R4: k-NN Engine Selection

**Decision**: Use the **Lucene** k-NN engine with HNSW algorithm and `cosinesimil` space type.

**Rationale**: OpenSearch supports three k-NN engines: Lucene, Faiss, and NMSLIB. For kris's scale (~20K–100K vectors, single node):
- **Lucene** integrates natively with OpenSearch's filter execution path, enabling efficient pre-filtered ANN search. This is critical for source/kind filtering (FR-014).
- **Lucene** has no additional native library dependencies — simpler for single-node Docker deployments.
- **Lucene** engine supports `cosinesimil`, matching the cosine distance used by the current Qdrant collection.
- At kris's scale, all three engines perform comparably. Lucene is preferred for its filter integration.

**Alternatives considered**:
- **Faiss** — better for very large scale (millions+ vectors) with IVF indices. Overkill for kris's current scale. Consider if corpus grows beyond 1M chunks.
- **NMSLIB** — faster pure vector search but does not support pre-filtering on k-NN queries. Would force post-filtering, defeating FR-014.

---

## R5: Index Schema Design

**Decision**: Single index `kris_chunks` with the following mapping:

| Field | Type | Purpose |
|-------|------|---------|
| `embedding` | `knn_vector` (dim=768, cosinesimil, lucene/hnsw) | Semantic vector search |
| `content` | `text` (standard analyzer) | BM25 full-text search (future hybrid) |
| `content_hash` | `keyword` | Dedup key, content-addressed lookup |
| `chunk_id` | `keyword` | Cross-reference to SQLite chunk table |
| `chunk_index` | `integer` | Ordering within parent content |
| `chunking_strategy` | `keyword` | Algorithm used for chunking |
| `file_kind` | `keyword` | Filter: text, code, markdown, etc. |
| `source_id` | `keyword` | Filter: which source this came from |
| `file_path` | `keyword` | Display and filter: file location |

**Rationale**:
- Storing `content` as `text` alongside the vector enables future hybrid search (Sprint 004) without re-indexing.
- Structured metadata as `keyword` fields enables efficient pre-filtering on k-NN queries and term aggregations.
- Single index simplifies management. Multi-model embeddings (Sprint 005) can add additional `knn_vector` fields to the same index.

**Index settings**:
- `number_of_shards: 1` — single-node deployment, no benefit from multiple shards.
- `number_of_replicas: 0` — single-node, replicas impossible and wasteful.
- `index.knn: true` — enables k-NN plugin for the index.

**Alternatives considered**:
- Separate indices per source — unnecessary fragmentation. Pre-filtering by `source_id` keyword is efficient.
- Separate indices per embedding model — deferred to Sprint 005 when multi-model is introduced. Could use additional vector fields or separate indices then.

---

## R6: Bulk Indexing Strategy

**Decision**: Use `opensearchpy.helpers.bulk()` with batches of ~500 documents per call.

**Rationale**: The `helpers.bulk()` function handles chunked HTTP requests, error collection, and retries. Batch size of 500 balances memory usage against HTTP overhead, well within OpenSearch's default `http.max_content_length` of 100MB. For a typical 768-dim float32 embedding (~3KB) plus metadata (~1KB), 500 documents ≈ 2MB per batch.

**Alternatives considered**:
- Single-document `index()` calls — too slow for re-indexing (N HTTP round-trips).
- Very large batches (5000+) — risk of hitting HTTP body size limits and memory pressure in single-node deployments.

---

## R7: SQLite Schema Migration Strategy

**Decision**: Rename `qdrant_point_id` → `opensearch_doc_id` and `collection_name` → `index_name` in the EMBEDDING table via `ALTER TABLE RENAME COLUMN`.

**Rationale**: SQLite 3.25+ (2018-09) supports `ALTER TABLE ... RENAME COLUMN`. kris requires Python 3.12+, which bundles SQLite ≥ 3.39. The rename is non-destructive — existing data rows are preserved with their current values (which are UUIDs, equally valid as OpenSearch doc IDs).

**Migration sequence**:
1. Check if old column name exists (for idempotency)
2. `ALTER TABLE embedding RENAME COLUMN qdrant_point_id TO opensearch_doc_id`
3. `ALTER TABLE embedding RENAME COLUMN collection_name TO index_name`

**Alternatives considered**:
- Drop and recreate the table — destructive, loses existing cross-references.
- Add new columns and copy data — unnecessarily complex for a simple rename.
- Don't rename (keep `qdrant_point_id` forever) — confusing for future maintenance.

---

## R8: Data Migration Path

**Decision**: Re-index by resetting processing status in SQLite, then running `kris index`. No direct Qdrant-to-OpenSearch data migration.

**Rationale**: Direct migration would require reading from Qdrant and writing to OpenSearch — but the OpenSearch documents need the `content` text field, which Qdrant points don't carry (they only have vectors). Re-indexing also ensures the chunks are written with the correct OpenSearch mapping. Since kris has incremental processing (`extract → chunk → embed`), only the `embed` step needs to re-run if chunks already exist in SQLite.

**Optimization**: Only reset the embed task status, not extract/chunk. The re-embed reads existing chunks from SQLite and writes to OpenSearch, avoiding re-reading source files.

**Alternatives considered**:
- Export Qdrant vectors, merge with SQLite chunk text, import to OpenSearch — fragile, more code to write than re-indexing, and not reusable.

---

## R9: Error Handling Patterns

**Decision**: Wrap OpenSearch client operations with specific exception handling, providing actionable error messages.

**Key error scenarios**:

| Error | Detection | User Message |
|-------|-----------|-------------|
| Connection refused | `ConnectionError` from `opensearch-py` | "Cannot connect to OpenSearch at {url}. Is the service running? Check `docker ps` for the opensearch container." |
| Authentication failed | HTTP 401 from cluster health check | "OpenSearch authentication failed. Check username/password in config.toml or KRIS_OPENSEARCH_PASSWORD env var." |
| Index mapping conflict | `RequestError` on index creation | "OpenSearch index '{name}' exists with incompatible mapping (expected {dim}-dim vectors, found {actual}). Delete the index or use a different index_prefix." |
| Bulk indexing partial failure | Failed items in `helpers.bulk()` response | "Indexed {success}/{total} documents. {failed} failed: {first_error}. Re-run `kris index` to retry." |
| Disk full | `RequestError` with `flood_stage` | "OpenSearch disk is full. Free space on the data volume or increase disk allocation." |

---

## R10: What kris Does NOT Ship

**Decision**: kris does NOT include a `docker-compose.yml` for OpenSearch in its repository.

**Rationale**: The OpenSearch deployment is external infrastructure, managed separately. This is consistent with how production databases are managed — the application connects, it doesn't deploy.

**What kris does ship**:
- Configuration schema (`[opensearch]` section in config.toml)
- Connection validation (`kris config validate`)
- Diagnostic checks (`kris diagnose`)
- Documentation: prerequisites (OpenSearch must be running) and example Docker setup in `docs/setup.md`
