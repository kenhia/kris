"""Default configuration generation."""

from __future__ import annotations

from pathlib import Path

from kris.config.schema import default_config_path

_DEFAULT_CONFIG_TOML = """\
# kris configuration
# See docs/setup.md for full documentation

# Log level: DEBUG, INFO, WARNING, ERROR
log_level = "INFO"

# Data directory (SQLite catalog lives here)
# Default: $XDG_DATA_HOME/kris (~/.local/share/kris)
# data_dir = ""

# Cache directory (Qdrant storage, model cache)
# Default: $XDG_CACHE_HOME/kris (~/.cache/kris)
# cache_dir = ""

# Sources — add your data directories here
# Each source has a unique ID and points to a directory on disk.
[sources.my-files]
name = "My Files"
type = "local"
base_path = "~/Documents"
exclude_patterns = [".git", "node_modules", "__pycache__", ".venv", "target"]

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
