# Quickstart: Production Hardening

**Feature**: 002-production-hardening

After this sprint, the following new and changed behaviors are available.

---

## Default Exclude Patterns

No action needed — default excludes are active automatically. Your first
scan will skip `.git`, `node_modules`, `__pycache__`, `target/`, `.venv`,
and other common build/cache directories.

To see the full default list, check your config:

```bash
kris config validate
```

To **opt out** of defaults for a specific source, add to `config.toml`:

```toml
[sources.raw-scan]
base_path = "/data/raw"
include_default_exclude_patterns = false
exclude_patterns = []  # only your own patterns apply
```

---

## Diagnosing Failures

After an indexing run, check what went wrong:

```bash
kris diagnose
```

This shows:
- **Failed files by extension** — which file types are failing
- **Skipped files by kind** — image, binary, archive files (expected skips)
- **Suggested excludes** — directory prefixes with many failures

Use the suggestions to refine your source's `exclude_patterns`.

---

## Qdrant Server Mode

For collections exceeding 20K points, switch to Qdrant server mode:

### 1. Start Qdrant via Docker

```bash
docker run -d --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v ~/.local/share/kris/qdrant-server:/qdrant/storage \
  qdrant/qdrant
```

### 2. Update config

```toml
[qdrant]
mode = "server"
url = "http://localhost:6333"
```

### 3. Re-index

```bash
kris index
```

Existing embedded data is not migrated — a re-index rebuilds the
vector index from the SQLite chunks (source of truth).

---

## VRAM Calibration

Measure actual VRAM usage for your configured models:

```bash
# Preview measurements without changing config
kris config update-model-sizes --dry-run

# Measure and update config.toml
kris config update-model-sizes
```

---

## Quieter Logs

Log output is now less noisy at the default INFO level:
- Per-file messages appear at DEBUG only
- Periodic summaries every ~3,000 items at INFO
- Final totals at completion

To see per-file detail:

```bash
kris index --log-level DEBUG
```

---

## Status Command

Failed files are hidden by default:

```bash
kris status                # shows count only
kris status --show-failed  # shows full table
kris status --json         # always includes failed_files array
```
