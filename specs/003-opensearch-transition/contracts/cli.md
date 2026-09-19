# CLI Contract: OpenSearch Transition

**Feature**: 003-opensearch-transition

This document defines the CLI interface changes for the OpenSearch transition sprint.
No new commands are added — existing commands are modified to work with OpenSearch instead of Qdrant.

---

## Modified Command: `kris init`

No syntax change. The generated default `config.toml` changes:

**Before** (generated config includes):
```toml
[qdrant]
mode = "embedded"            # "embedded" or "server"
# url = "http://localhost:6333"  # required when mode = "server"
# api_key = ""                   # optional, for Qdrant Cloud
```

**After** (generated config includes):
```toml
[opensearch]
url = "https://localhost:9200"
username = "admin"
password = ""                    # or set KRIS_OPENSEARCH_PASSWORD env var
verify_certs = false             # true for production with real certificates
index_prefix = "kris"            # indices named: kris_chunks, etc.
```

---

## Modified Command: `kris config validate`

No syntax change. Behavior changes:

**Before**: Validates config structure only.

**After**: Additionally checks:
- OpenSearch connectivity (GET cluster health)
- OpenSearch authentication (valid credentials)
- Reports OpenSearch version and cluster status

### Human-readable output additions

```
OpenSearch
┌───────────────┬──────────────────────────────┐
│ URL           │ https://localhost:9200        │
│ Status        │ ✓ Connected                  │
│ Version       │ 2.19.1                       │
│ Cluster       │ kubs0-opensearch (green)     │
│ Index         │ kris_chunks (23,456 docs)    │
└───────────────┴──────────────────────────────┘
```

### Error output (connection failure)

```
OpenSearch
┌───────────────┬──────────────────────────────┐
│ URL           │ https://localhost:9200        │
│ Status        │ ✗ Connection refused         │
│ Hint          │ Is OpenSearch running?        │
│               │ Check: docker ps | grep       │
│               │   opensearch                  │
└───────────────┴──────────────────────────────┘
```

### Error output (auth failure)

```
OpenSearch
┌───────────────┬──────────────────────────────┐
│ URL           │ https://localhost:9200        │
│ Status        │ ✗ Authentication failed      │
│ Hint          │ Check username/password in    │
│               │ config.toml or set            │
│               │ KRIS_OPENSEARCH_PASSWORD      │
└───────────────┴──────────────────────────────┘
```

---

## Modified Command: `kris index`

No syntax change. Internal behavior changes:

- Embedding pipeline writes to OpenSearch instead of Qdrant
- Uses bulk indexing via `opensearch-py helpers.bulk()`
- Each indexed document contains both embedding vector and chunk text content

**Error output** (OpenSearch unreachable):
```
Error: Cannot connect to OpenSearch at https://localhost:9200.
Is the service running? Check: docker ps | grep opensearch
```

---

## Modified Command: `kris query`

```
Usage: kris query [OPTIONS] QUESTION
```

No syntax change. Internal behavior changes:

- Retrieval uses OpenSearch k-NN search instead of Qdrant `query_points()`
- Source/kind pre-filtering via OpenSearch query DSL (applied before vector search)

No visible output format change — same answer + citations display.

---

## Modified Command: `kris retrieve`

```
Usage: kris retrieve [OPTIONS] QUESTION
```

No syntax change. Internal behavior changes same as `kris query`.

No visible output format change — same chunks + scores display.

---

## Modified Command: `kris cleanup`

No syntax change. Internal behavior changes:

- Deletes documents from OpenSearch instead of Qdrant points
- Preview output label changes:

**Before**:
```
┌──────────────────┬───────┐
│ Qdrant points    │    42 │
└──────────────────┴───────┘
```

**After**:
```
┌──────────────────┬───────┐
│ Search documents │    42 │
└──────────────────┴───────┘
```

---

## Modified Command: `kris diagnose`

No syntax change. Output additions:

**Before**: Shows failure/skip diagnostics only.

**After**: Adds OpenSearch health section:

```
OpenSearch Health
┌───────────────┬──────────────────────────────┐
│ Cluster       │ kubs0-opensearch (green)     │
│ Index         │ kris_chunks                  │
│ Documents     │ 23,456                       │
│ Store size    │ 142.3 MB                     │
│ Health        │ green                        │
└───────────────┴──────────────────────────────┘
```

---

## Modified Command: `kris status`

No syntax change for this sprint. Status continues to pull statistics from SQLite.
Future sprints may add OpenSearch-derived statistics.

---

## Legacy Config Detection

When any command encounters a `[qdrant]` section in config.toml:

```
Warning: Configuration contains a [qdrant] section which is no longer supported.
kris now uses OpenSearch as its search backend.
Please replace [qdrant] with [opensearch] in your config.toml.
Run 'kris init' to see the new configuration format.
```

This is a warning, not an error — commands still function if `[opensearch]` is also present.
If `[opensearch]` is missing and only `[qdrant]` exists, it is an error.
