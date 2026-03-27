# CLI Contract: Production Hardening

**Feature**: 002-production-hardening

This document defines the CLI interface additions and modifications for
the production hardening sprint.

---

## New Command: `kris diagnose`

```
Usage: kris diagnose [OPTIONS]

  Analyze processing failures and skipped files to help refine exclude patterns.

Options:
  --config PATH   Config file path [default: $XDG_CONFIG_HOME/kris/config.toml]
  --source TEXT    Filter by source name
  --json          Output as JSON
  --help          Show this message and exit.
```

### Human-readable output

```
Processing Diagnostics
══════════════════════

Failed Files by Extension
┌───────────┬───────────┬───────┐
│ Extension │ File Kind │ Count │
├───────────┼───────────┼───────┤
│ .png      │ image     │   847 │
│ .ico      │ image     │   234 │
│ .woff2    │ binary    │    89 │
│ .bin      │ binary    │    42 │
│ (none)    │ unknown   │    18 │
└───────────┴───────────┴───────┘

Skipped Files by Kind
┌───────────┬───────┐
│ File Kind │ Count │
├───────────┼───────┤
│ image     │ 4,231 │
│ binary    │ 1,892 │
│ archive   │   341 │
│ audio     │   127 │
│ video     │    43 │
│ unknown   │   892 │
└───────────┴───────┘

Suggested Excludes (directories with 5+ failures)
┌──────────────────────┬───────┐
│ Path Prefix          │ Count │
├──────────────────────┼───────┤
│ .svelte-kit/         │   234 │
│ htmlcov/             │    89 │
│ .ruff_cache/         │    42 │
└──────────────────────┴───────┘
```

### JSON output

```json
{
  "failed_by_extension": [
    {"extension": ".png", "file_kind": "image", "count": 847}
  ],
  "skipped_by_kind": [
    {"file_kind": "image", "count": 4231}
  ],
  "suggested_excludes": [
    {"path_prefix": ".svelte-kit/", "count": 234}
  ]
}
```

---

## New Command: `kris config update-model-sizes`

```
Usage: kris config update-model-sizes [OPTIONS]

  Measure actual VRAM consumption for each configured model and update config.

Options:
  --config PATH   Config file path [default: $XDG_CONFIG_HOME/kris/config.toml]
  --dry-run       Report measurements without modifying config
  --help          Show this message and exit.
```

### Human-readable output

```
VRAM Measurement
════════════════

┌─────────────────────────┬────────────┬──────────┬─────────┐
│ Model                   │ Configured │ Measured │ Updated │
├─────────────────────────┼────────────┼──────────┼─────────┤
│ BAAI/bge-base-en-v1.5   │ 0.5 GB     │ 0.4 GB   │ ✓       │
│ Phi-3-medium-128k.gguf  │ 12.0 GB    │ 11.2 GB  │ ✓       │
└─────────────────────────┴────────────┴──────────┴─────────┘

Config updated: ~/.config/kris/config.toml
```

### With `--dry-run`

Same table but "Updated" column shows `—` and no "Config updated" line.

### No GPU available

```
⚠ No GPU detected. Cannot measure VRAM usage.
```
Exit code: 0 (not an error).

---

## Modified Command: `kris status`

### New option: `--show-failed` / `-f`

```
Usage: kris status [OPTIONS]

Options:
  --config PATH       Config file path
  --source TEXT        Filter by source name
  --show-failed / -f  Show full failed-files table [default: hidden]
  --json              Output as JSON
  --help              Show this message and exit.
```

### Default behavior (no `--show-failed`)

Failed-files table is replaced by a one-line summary:

```
42 files failed processing (use --show-failed to list them)
```

### With `--show-failed`

Full table displayed as in MVP.

### JSON output

Always includes `failed_files` array regardless of `--show-failed` flag.

---

## Modified Config: `kris init`

Generated default config includes the new sections:

```toml
# Default exclude patterns applied to all sources.
# Set include_default_exclude_patterns = false on a source to opt out.
default_exclude_patterns = [
    ".git", ".hg", ".svn",
    "__pycache__", ".venv", ".tox", ".nox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "htmlcov",
    "node_modules", ".next", ".svelte-kit", ".nuxt",
    "target", "build", "dist", "out",
    ".idea", ".vscode", ".vs",
    ".coverage", "coverage",
]

[qdrant]
mode = "embedded"
url = "http://localhost:6333"
```

---

## Scanner CLI (Rust) — unchanged interface

The scanner's `--exclude` argument already accepts multiple patterns.
The Python CLI merges default + source-specific patterns and passes
the full list. No scanner CLI changes needed — only the pattern
matching logic inside the scanner changes (glob support via `globset`).
