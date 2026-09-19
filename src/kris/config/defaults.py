"""Default configuration generation."""

from __future__ import annotations

from pathlib import Path

from kris.config.schema import default_config_path

DEFAULT_EXCLUDE_PATTERNS: list[str] = [
    # VCS
    ".git",
    ".hg",
    ".svn",
    # Python
    "__pycache__",
    ".venv",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "htmlcov",
    "*.pyc",
    "*.pyo",
    # Node.js
    "node_modules",
    ".next",
    ".svelte-kit",
    ".nuxt",
    # Rust
    "target",
    # Build artifacts
    "build",
    "dist",
    "out",
    # IDE/Editor
    ".idea",
    ".vscode",
    ".vs",
    # Coverage
    ".coverage",
    "coverage",
]

_DEFAULT_CONFIG_TOML = """\
# kris configuration
# See docs/setup.md for full documentation

# Log level: DEBUG, INFO, WARNING, ERROR
log_level = "INFO"

# Data directory (SQLite catalog lives here)
# Default: $XDG_DATA_HOME/kris (~/.local/share/kris)
# data_dir = ""

# Cache directory (model cache)
# Default: $XDG_CACHE_HOME/kris (~/.cache/kris)
# cache_dir = ""

# Default exclude patterns — merged with each source's exclude_patterns.
# Remove or edit entries to customize. Sources can opt out with
# include_default_exclude_patterns = false.
default_exclude_patterns = [
    ".git", ".hg", ".svn",
    "__pycache__", ".venv", ".tox", ".nox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "htmlcov", "*.pyc", "*.pyo",
    "node_modules", ".next", ".svelte-kit", ".nuxt",
    "target", "build", "dist", "out",
    ".idea", ".vscode", ".vs",
    ".coverage", "coverage",
]

# OpenSearch search backend configuration
[opensearch]
url = "https://localhost:9200"
username = "admin"
password = ""                    # or set KRIS_OPENSEARCH_PASSWORD env var
verify_certs = false             # true for production with real certificates
index_prefix = "kris"            # indices named: kris_chunks, etc.

# Sources — add your data directories here
# Each source has a unique ID and points to a directory on disk.
[sources.my-files]
name = "My Files"
type = "local"
base_path = "~/Documents"
exclude_patterns = [".git", "node_modules", "__pycache__", ".venv", "target"]
include_default_exclude_patterns = true

# Scan schedules for this source
[[sources.my-files.schedules]]
path_pattern = "**"
interval_minutes = 60
priority = 1

# Models configuration
[models.embedding]
name = "BAAI/bge-base-en-v1.5"
dimensions = 768
vram_gb = 0.5

[models.llm]
# name = "your-model-name"
# model_path = "/path/to/model.gguf"
# vram_gb = 8.0
# n_ctx = 4096                  # context window size (tokens)
"""


def generate_default_config(config_path: Path | None = None, force: bool = False) -> Path:
    """Write the default config TOML to disk. Returns the path written to.

    Raises FileExistsError if the file already exists and force=False.
    """
    if config_path is None:
        config_path = default_config_path()

    if config_path.exists() and not force:
        raise FileExistsError(f"Configuration file already exists: {config_path}")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_DEFAULT_CONFIG_TOML, encoding="utf-8")
    return config_path
