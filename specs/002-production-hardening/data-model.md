# Data Model: Production Hardening

**Feature**: 002-production-hardening
**Source**: Extends [001-mvp-core/data-model.md](../001-mvp-core/data-model.md)

This sprint modifies no tables but adds new status values, a new config
section, and a new constant set. All changes are additive and backward
compatible with the MVP schema.

---

## Schema Changes

### CONTENT table — new `processing_status` value

The `processing_status` field gains a new value: `skipped`.

| Value | Meaning |
|-------|---------|
| `pending` | New or changed, awaiting task planning |
| `processing` | Tasks have been created and are running |
| `completed` | All tasks finished successfully |
| `failed` | One or more tasks failed after max retries |
| **`skipped`** | **Content not eligible for extraction (e.g., binary, image, archive). Metadata preserved; no tasks created.** |

The planner sets this value when `file_kind` is not extractable.

### FILE table — no changes

The `file_kind` field (set by the Rust scanner) is already sufficient.
No new columns needed.

### TASK table — no changes

Tasks are simply not created for skipped content. The existing schema
handles all other cases.

---

## Configuration Model Changes

### New: `[qdrant]` section

```toml
[qdrant]
mode = "embedded"          # "embedded" | "server"
url = "http://localhost:6333"  # used when mode = "server"
# api_key = ""             # optional, for authenticated instances
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | string | `"embedded"` | `"embedded"` for local file-based Qdrant, `"server"` for HTTP connection |
| `url` | string | `"http://localhost:6333"` | Qdrant server URL (only used when `mode = "server"`) |
| `api_key` | string? | `null` | Optional API key for authenticated Qdrant instances |

### New: `default_exclude_patterns` (top-level)

```toml
default_exclude_patterns = [
    ".git", ".hg", ".svn",
    "__pycache__", ".venv", ".tox", ".nox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "htmlcov",
    "node_modules", ".next", ".svelte-kit", ".nuxt",
    "target", "build", "dist", "out",
    ".idea", ".vscode", ".vs",
    ".coverage", "coverage",
]
```

Merged (union) with each source's `exclude_patterns` before scanning.

### New: `include_default_exclude_patterns` per source

```toml
[sources.code]
base_path = "/home/ken/src"
include_default_exclude_patterns = true  # default: true
exclude_patterns = [".scratch-agent"]    # source-specific additions
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `include_default_exclude_patterns` | bool | `true` | When `false`, only the source's own `exclude_patterns` are used |

---

## Diagnostic Query Model

The `kris diagnose` command uses SQL aggregation — no new tables.

### Failure by extension

```sql
SELECT
    CASE
        WHEN instr(f.path, '.') > 0
        THEN substr(f.path, length(f.path) - length(replace(f.path, '.', '')) + 1)
        ELSE '(no extension)'
    END AS extension,
    f.file_kind,
    COUNT(*) AS count
FROM file f
JOIN content c ON f.content_hash = c.content_hash
WHERE c.processing_status = 'failed'
GROUP BY extension, f.file_kind
ORDER BY count DESC;
```

### Skipped by file kind

```sql
SELECT f.file_kind, COUNT(*) AS count
FROM file f
JOIN content c ON f.content_hash = c.content_hash
WHERE c.processing_status = 'skipped'
GROUP BY f.file_kind
ORDER BY count DESC;
```

### Path prefix analysis

```sql
SELECT
    substr(f.path, 1, instr(substr(f.path, 2), '/') + 1) AS top_dir,
    COUNT(*) AS failed_count
FROM file f
JOIN content c ON f.content_hash = c.content_hash
WHERE c.processing_status = 'failed'
GROUP BY top_dir
HAVING failed_count >= 5
ORDER BY failed_count DESC;
```
