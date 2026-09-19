"""Configuration schema and TOML loading/validation."""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


def _xdg_config_home() -> Path:
    """Return XDG_CONFIG_HOME, defaulting to ~/.config."""
    import os

    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def _xdg_data_home() -> Path:
    """Return XDG_DATA_HOME, defaulting to ~/.local/share."""
    import os

    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def _xdg_cache_home() -> Path:
    """Return XDG_CACHE_HOME, defaulting to ~/.cache."""
    import os

    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))


def default_config_path() -> Path:
    return _xdg_config_home() / "kris" / "config.toml"


def default_data_dir() -> Path:
    return _xdg_data_home() / "kris"


def default_cache_dir() -> Path:
    return _xdg_cache_home() / "kris"


@dataclass
class OpenSearchConfig:
    url: str = "https://localhost:9200"
    username: str = "admin"
    password: str = ""
    verify_certs: bool = False
    index_prefix: str = "kris"


@dataclass
class ScheduleConfig:
    path_pattern: str = "**"
    interval_minutes: int = 60
    priority: int = 1


@dataclass
class SourceConfig:
    name: str
    base_path: str
    source_type: str = "local"
    exclude_patterns: list[str] = field(default_factory=list)
    include_default_exclude_patterns: bool = True
    schedules: list[ScheduleConfig] = field(default_factory=list)


@dataclass
class EmbeddingModelConfig:
    name: str = "BAAI/bge-base-en-v1.5"
    dimensions: int = 768
    vram_gb: float = 0.5


@dataclass
class LLMModelConfig:
    name: str = ""
    model_path: str = ""
    vram_gb: float = 8.0
    n_ctx: int = 4096


@dataclass
class ModelsConfig:
    embedding: EmbeddingModelConfig = field(default_factory=EmbeddingModelConfig)
    llm: LLMModelConfig = field(default_factory=LLMModelConfig)


@dataclass
class KrisConfig:
    sources: dict[str, SourceConfig] = field(default_factory=dict)
    models: ModelsConfig = field(default_factory=ModelsConfig)
    opensearch: OpenSearchConfig = field(default_factory=OpenSearchConfig)
    data_dir: str = ""
    cache_dir: str = ""
    log_level: str = "INFO"

    def __post_init__(self):
        if not self.data_dir:
            self.data_dir = str(default_data_dir())
        if not self.cache_dir:
            self.cache_dir = str(default_cache_dir())

    @property
    def db_path(self) -> Path:
        return Path(self.data_dir) / "catalog.db"

    @property
    def opensearch_index(self) -> str:
        return f"{self.opensearch.index_prefix}_chunks"


class ConfigError(Exception):
    """Raised when configuration is invalid."""


def _parse_schedule(raw: dict) -> ScheduleConfig:
    return ScheduleConfig(
        path_pattern=raw.get("path_pattern", "**"),
        interval_minutes=raw.get("interval_minutes", 60),
        priority=raw.get("priority", 1),
    )


def _parse_source(source_id: str, raw: dict) -> SourceConfig:
    name = raw.get("name")
    if not name:
        raise ConfigError(f"Source '{source_id}' is missing required field 'name'")
    base_path = raw.get("base_path")
    if not base_path:
        raise ConfigError(f"Source '{source_id}' is missing required field 'base_path'")

    schedules_raw = raw.get("schedules", [])
    schedules = [_parse_schedule(s) for s in schedules_raw]

    return SourceConfig(
        name=name,
        base_path=str(Path(base_path).expanduser()),
        source_type=raw.get("type", "local"),
        exclude_patterns=raw.get("exclude_patterns", []),
        include_default_exclude_patterns=raw.get("include_default_exclude_patterns", True),
        schedules=schedules,
    )


def _parse_models(raw: dict) -> ModelsConfig:
    embedding_raw = raw.get("embedding", {})
    llm_raw = raw.get("llm", {})
    return ModelsConfig(
        embedding=EmbeddingModelConfig(
            name=embedding_raw.get("name", "BAAI/bge-base-en-v1.5"),
            dimensions=embedding_raw.get("dimensions", 768),
            vram_gb=embedding_raw.get("vram_gb", 0.5),
        ),
        llm=LLMModelConfig(
            name=llm_raw.get("name", ""),
            model_path=llm_raw.get("model_path", ""),
            vram_gb=llm_raw.get("vram_gb", 8.0),
            n_ctx=llm_raw.get("n_ctx", 4096),
        ),
    )


def _parse_opensearch(raw: dict) -> OpenSearchConfig:
    import os

    password = raw.get("password", "")
    if not password:
        password = os.environ.get("KRIS_OPENSEARCH_PASSWORD", "")
    return OpenSearchConfig(
        url=raw.get("url", "https://localhost:9200"),
        username=raw.get("username", "admin"),
        password=password,
        verify_certs=raw.get("verify_certs", False),
        index_prefix=raw.get("index_prefix", "kris"),
    )


def get_effective_excludes(source: SourceConfig) -> list[str]:
    """Merge default exclude patterns with source-specific patterns.

    Returns the union (deduplicated, order preserved) of the default patterns
    and the source's own exclude_patterns. If the source has
    include_default_exclude_patterns=False, only its own patterns are returned.
    """
    from kris.config.defaults import DEFAULT_EXCLUDE_PATTERNS

    if not source.include_default_exclude_patterns:
        return list(source.exclude_patterns)

    seen: set[str] = set()
    merged: list[str] = []
    for pattern in DEFAULT_EXCLUDE_PATTERNS + source.exclude_patterns:
        if pattern not in seen:
            seen.add(pattern)
            merged.append(pattern)
    return merged


def load_config(config_path: str | Path | None = None) -> KrisConfig:
    """Load and validate configuration from a TOML file."""
    if config_path is None:
        config_path = default_config_path()
    config_path = Path(config_path)

    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")

    text = config_path.read_text(encoding="utf-8")
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Invalid TOML in {config_path}: {e}") from e

    sources = {}
    for source_id, source_raw in raw.get("sources", {}).items():
        sources[source_id] = _parse_source(source_id, source_raw)

    # Legacy [qdrant] detection (T013)
    has_qdrant = "qdrant" in raw
    has_opensearch = "opensearch" in raw
    if has_qdrant and not has_opensearch:
        raise ConfigError(
            "Found legacy [qdrant] config section but no [opensearch] section. "
            "Please migrate to [opensearch]. See docs/setup.md for migration steps."
        )
    if has_qdrant and has_opensearch:
        logger.warning(
            "Config contains both [qdrant] and [opensearch] sections. "
            "The [qdrant] section is ignored — remove it to silence this warning."
        )

    models = _parse_models(raw.get("models", {}))
    opensearch = _parse_opensearch(raw.get("opensearch", {}))

    return KrisConfig(
        sources=sources,
        models=models,
        opensearch=opensearch,
        data_dir=raw.get("data_dir", ""),
        cache_dir=raw.get("cache_dir", ""),
        log_level=raw.get("log_level", "INFO"),
    )


def validate_config(config: KrisConfig) -> list[str]:
    """Validate a loaded config. Returns a list of error messages (empty = valid)."""
    errors: list[str] = []

    if not config.sources:
        errors.append("No sources configured. Add at least one [sources.<id>] section.")

    for source_id, source in config.sources.items():
        source_path = Path(source.base_path)
        if not source_path.is_absolute():
            errors.append(
                f"Source '{source_id}': base_path must be absolute (got '{source.base_path}')"
            )

        for i, schedule in enumerate(source.schedules):
            if schedule.interval_minutes < 1:
                errors.append(f"Source '{source_id}' schedule {i}: interval_minutes must be >= 1")

    return errors
