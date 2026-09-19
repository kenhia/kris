# Quickstart: OpenSearch Transition

**Feature**: 003-opensearch-transition

After this sprint, kris uses OpenSearch instead of Qdrant for all vector and text search operations.

---

## Prerequisites

OpenSearch must be running before using kris. Verify with:

```bash
docker ps | grep opensearch
```

If you already have an OpenSearch deployment (e.g., at `/home/ken/opensearch/`), ensure the container is running and accessible at `https://localhost:9200`.

---

## Update Configuration

### 1. Regenerate config (new install)

```bash
kris init
```

The generated `config.toml` now includes an `[opensearch]` section instead of `[qdrant]`.

### 2. Migrate existing config

Replace the `[qdrant]` section in your `config.toml`:

**Remove:**
```toml
[qdrant]
mode = "embedded"
```

**Add:**
```toml
[opensearch]
url = "https://localhost:9200"
username = "admin"
password = ""                    # or set KRIS_OPENSEARCH_PASSWORD env var
verify_certs = false             # true for production with real certificates
index_prefix = "kris"            # indices named: kris_chunks, etc.
```

### 3. Validate connection

```bash
kris config validate
```

This now checks OpenSearch connectivity, authentication, and reports cluster health.

---

## Re-index Content

Existing Qdrant-indexed content must be re-indexed into OpenSearch. The SQLite catalog and chunks are preserved — only the embedding step re-runs.

```bash
kris index
```

The first run after transition will:
1. Create the `kris_chunks` index in OpenSearch (if it doesn't exist)
2. Re-embed all chunks into OpenSearch with both vectors and text content
3. Update SQLite embedding records with OpenSearch document IDs

---

## Verify

Run a query to confirm search is working:

```bash
kris query "test query about your content"
```

Check system health:

```bash
kris diagnose
```

The diagnose output now includes an OpenSearch health section showing cluster status, index name, document count, and store size.

---

## What Changed

| Before (Qdrant) | After (OpenSearch) |
|------------------|--------------------|
| `[qdrant]` config section | `[opensearch]` config section |
| Embedded or server mode | External service (Docker) |
| Vectors only | Vectors + full text in same document |
| `qdrant-client` dependency | `opensearch-py` dependency |
| `qdrant_point_id` in SQLite | `opensearch_doc_id` in SQLite |

---

## Troubleshooting

**"Cannot connect to OpenSearch"** — Check that the OpenSearch container is running: `docker ps | grep opensearch`

**"Authentication failed"** — Verify credentials in `config.toml` or set the `KRIS_OPENSEARCH_PASSWORD` environment variable.

**"Legacy [qdrant] configuration detected"** — Remove the `[qdrant]` section from `config.toml` and replace with `[opensearch]` as shown above.
