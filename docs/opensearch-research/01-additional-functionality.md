# OpenSearch — Additional Functionality & Modalities for kris

## Executive Summary

Replacing Qdrant with OpenSearch consolidates kris's storage and search infrastructure into a single engine that natively supports vector search, full-text search, hybrid queries, and structured analytics. This eliminates the need for separate systems (Qdrant for vectors, SQLite FTS5 for full-text, custom code for RRF fusion) and unlocks capabilities that would otherwise require significant custom development.

---

## 1. Unified Hybrid Search (Semantic + Lexical)

**Current state**: kris uses Qdrant for vector similarity and plans SQLite FTS5 for BM25 full-text search (Sprint 003), with custom Reciprocal Rank Fusion code to merge results.

**What OpenSearch provides**:
- **Native hybrid query type** — combines `neural` (vector) and `match` (BM25) queries in a single request
- **Built-in score normalization** — `min_max` and `l2` normalization across heterogeneous score scales
- **Built-in score combination** — `arithmetic_mean`, `geometric_mean`, `harmonic_mean` with per-query weighting
- **Search pipelines** — declarative post-processing (normalization, reranking) without application code

**Impact on kris**: Sprint 003's "Hybrid search: semantic + BM25 full-text" becomes a configuration exercise rather than a multi-week development effort. No custom RRF implementation needed. Score fusion quality is benchmarked and maintained by the OpenSearch project (8–15% relevance improvement over BM25 alone per their BEIR benchmarks).

---

## 2. Native Full-Text Search & Code Search

**Current state**: Sprint 006 plans FTS5 + trigram indexing for literal text/regex search across the corpus. Research phase needed for trigram vs. suffix arrays, Tantivy integration, etc.

**What OpenSearch provides**:
- **BM25 full-text search** with configurable analyzers (standard, language-specific, whitespace, pattern)
- **N-gram / edge n-gram tokenizers** for substring matching (replaces trigram index plan)
- **Regex queries** (`regexp` query type) natively supported
- **Wildcard queries** for glob-pattern file content search
- **Per-field analyzers** — different analysis chains for code vs. prose vs. file paths
- **Highlighting** — return matched snippets with context, highlighted terms
- **Multi-field mapping** — index the same content with multiple analyzers (e.g., exact, stemmed, n-gram) and query across all

**Impact on kris**: Sprint 006's code search and literal indexing research phase can leverage OpenSearch's proven full-text infrastructure. The "build vs. embed Tantivy" question goes away. Regex search, substring search, and file content search become query-time features rather than index-time engineering projects.

---

## 3. Structured Metadata Queries & Aggregations

**Current state**: File metadata lives in SQLite. Queries like "show me all Python files > 100KB modified this week" require SQL queries joined with vector results.

**What OpenSearch provides**:
- **Rich query DSL** — boolean, range, term, exists, nested queries over structured fields
- **Aggregations** — bucket (terms, histogram, date_histogram, range), metric (avg, sum, min, max, percentiles, cardinality), pipeline aggregations
- **Filtered aggregations** — compute statistics over subsets (e.g., "average file size per file_kind for source X")
- **Date math** — native date range queries ("files modified in the last 7 days")

**Impact on kris**: The `kris status` command becomes much more powerful. Cross-source analytics (Sprint 012) — file distribution heatmaps, duplication statistics, temporal change patterns — become straightforward aggregation queries rather than custom SQL + Python post-processing. Status reporting, dashboarding, and operational monitoring can all be driven by OpenSearch aggregations.

---

## 4. Filtered Vector Search

**Current state**: Qdrant supports payload-based filtering, but kris resolves file paths and source IDs via SQLite join after vector search (lossy — filters applied post-retrieval).

**What OpenSearch provides**:
- **Pre-filtering** on k-NN queries — filter by file_kind, source_id, path pattern, date range *before* vector search
- **Post-filtering** — apply filters after k-NN retrieval
- **Efficient filtered ANN** — OpenSearch's Lucene-based k-NN integrates with the filter execution path for efficient filtered approximate nearest neighbor search

**Impact on kris**: Query-time source/kind filtering becomes exact rather than approximate. "Search only in Python files from the NAS" doesn't waste retrieval slots on non-matching documents. The current SQLite join enrichment step simplifies dramatically.

---

## 5. Ingest Pipelines

**Current state**: kris has a Python-based task pipeline (extract → chunk → embed) with custom task queue and worker management.

**What OpenSearch provides**:
- **Ingest pipelines** — declarative document transformations on write: split, rename, convert, script, ML inference
- **Neural ingest processors** — generate embeddings at ingest time using deployed models
- **Text chunking processor** — built-in document chunking
- **Pipeline chaining** — compose complex transformations declaratively

**Impact on kris**: While kris's task-based pipeline is more sophisticated (model affinity, retry, dependency ordering), OpenSearch ingest pipelines could simplify the embed step — potentially offloading embedding generation to OpenSearch itself for server-mode deployments. This is an optional optimization, not a required migration step.

---

## 6. Multi-Modal Search Foundation

**Current state**: Sprint 008 plans image captioning + caption embedding. Currently text-only.

**What OpenSearch provides**:
- **Multiple vector fields per document** — store text embeddings, code embeddings, and image caption embeddings in the same index
- **Nested k-NN fields** — multiple vectors per document with independent search
- **Cross-field queries** — search across text and caption vectors simultaneously

**Impact on kris**: The multi-model embedding architecture (Sprint 004) and multimodal search (Sprint 008) map naturally to OpenSearch's multi-vector-field support. A single chunk document can carry `text_embedding`, `code_embedding`, and `caption_embedding` fields, searched independently or together.

---

## 7. Dashboards & Visualization

**Current state**: Sprint 011 plans a Web UI for status, search, and browse. Would need to be built from scratch.

**What OpenSearch provides**:
- **OpenSearch Dashboards** (Kibana fork) — full-featured visualization, search, and dashboard platform
- **Discover** — interactive document exploration with full-text search and field filtering
- **Visualizations** — pie charts, bar charts, area charts, data tables, metrics, gauges
- **Saved searches/dashboards** — shareable, bookmarkable views
- **Dev Tools console** — direct query DSL interaction for diagnostics

**Impact on kris**: A read-only dashboard for kris (Sprint 011) could potentially be built entirely in OpenSearch Dashboards rather than a custom Web UI. Index statistics, file distribution, search testing, and content exploration are all native capabilities. This doesn't replace the CLI or API but provides an immediate visualization layer with zero custom frontend code.

---

## 8. Observability & Monitoring

**Current state**: kris uses rotating log files with configurable verbosity.

**What OpenSearch provides**:
- **Index-level metrics** — document count, store size, refresh/merge/search latency
- **Slow query logs** — automatic logging of queries exceeding configurable thresholds
- **Node stats** — JVM heap, thread pools, circuit breakers
- **Task management API** — monitor long-running tasks
- **Cluster health API** — green/yellow/red status

**Impact on kris**: Pipeline health monitoring (files processed, query latency, index health) becomes queryable infrastructure state rather than log scraping. The `kris diagnose` command could leverage OpenSearch cluster/index health for self-diagnostics.

---

## 9. Scalability Without Architecture Change

**Current state**: Qdrant embedded mode hits 20K point warnings (B008). Server mode requires Docker, separate process, separate management.

**What OpenSearch provides**:
- **Single-node Docker deployment** — one container handles everything (vectors + text + structured data)
- **Horizontal scaling** — add nodes for sharding/replication when needed (future-proof for multi-machine setups)
- **Index lifecycle management** — auto-rollover, size-based management
- **Snapshot/restore** — backup and recovery built in

**Impact on kris**: The Qdrant embedded-to-server migration pain (B008) goes away. OpenSearch runs as a single Docker service from day one. The 745K file scale and projected growth to millions of files is well within OpenSearch's design parameters. Horizontal scaling to multiple machines is available if needed, aligning with kris's planned remote agent architecture.

---

## 10. Neural Sparse Search (Bonus)

**What OpenSearch provides**:
- **Neural sparse encoding** — learned sparse representations (like SPLADE) alongside dense vectors
- **Sparse + dense hybrid** — combine traditional BM25, dense vector, and learned sparse signals

**Impact on kris**: A future enhancement avenue. Learned sparse models can capture keyword-aware semantic signals that pure dense vectors miss, potentially improving code search quality. Not critical for initial migration but available when needed.

---

## Summary: Sprint Impact Matrix

| Planned Sprint | Current Approach | With OpenSearch |
|----------------|-----------------|-----------------|
| 002 — Qdrant migration (B008) | Qdrant embedded → server Docker | Eliminated — OpenSearch handles both vectors and text from the start |
| 003 — Hybrid search | Custom FTS5 + custom RRF code | Native `hybrid` query + search pipeline normalization |
| 003 — Multi-collection fusion | Custom Python RRF | Native multi-field vector search, score combination |
| 004 — Multi-model embedding | Multiple Qdrant collections | Multiple k-NN fields in same index |
| 006 — Literal text search | FTS5 trigram research + custom index | Native BM25 + n-gram analyzers + regex queries |
| 007 — Code intelligence | Custom symbol index in SQLite | Structured fields + full-text fields in same index |
| 008 — Multimodal search | Caption embedding in separate Qdrant collection | Additional vector field per document |
| 011 — Web UI | Custom FastAPI + frontend | OpenSearch Dashboards for visualization; API still needed for CLI |
| 012 — Cross-source analytics | Custom SQL analytics | Aggregation framework, date histograms, bucket analytics |
