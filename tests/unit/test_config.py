"""Unit tests for config loading, validation, defaults, and XDG path resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from kris.config.defaults import generate_default_config
from kris.config.schema import (
    ConfigError,
    KrisConfig,
    default_cache_dir,
    default_config_path,
    default_data_dir,
    load_config,
    validate_config,
)


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """Set XDG dirs to temp paths."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return tmp_path


def _write_config(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


VALID_CONFIG = """\
log_level = "DEBUG"

[sources.test-src]
name = "Test Source"
type = "local"
base_path = "/tmp/test-data"
exclude_patterns = [".git", "__pycache__"]

[[sources.test-src.schedules]]
path_pattern = "**"
interval_minutes = 30
priority = 1

[models.embedding]
name = "BAAI/bge-base-en-v1.5"
dimensions = 768
vram_gb = 0.5
"""


class TestXDGPaths:
    def test_default_config_path(self, config_dir):
        assert default_config_path() == config_dir / "config" / "kris" / "config.toml"

    def test_default_data_dir(self, config_dir):
        assert default_data_dir() == config_dir / "data" / "kris"

    def test_default_cache_dir(self, config_dir):
        assert default_cache_dir() == config_dir / "cache" / "kris"


class TestLoadConfig:
    def test_loads_valid_config(self, tmp_path):
        path = _write_config(tmp_path / "config.toml", VALID_CONFIG)
        config = load_config(path)
        assert "test-src" in config.sources
        assert config.sources["test-src"].name == "Test Source"
        assert config.sources["test-src"].base_path == "/tmp/test-data"
        assert config.log_level == "DEBUG"

    def test_schedule_parsing(self, tmp_path):
        path = _write_config(tmp_path / "config.toml", VALID_CONFIG)
        config = load_config(path)
        schedules = config.sources["test-src"].schedules
        assert len(schedules) == 1
        assert schedules[0].interval_minutes == 30
        assert schedules[0].path_pattern == "**"

    def test_exclude_patterns(self, tmp_path):
        path = _write_config(tmp_path / "config.toml", VALID_CONFIG)
        config = load_config(path)
        assert ".git" in config.sources["test-src"].exclude_patterns

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "missing.toml")

    def test_invalid_toml_raises(self, tmp_path):
        path = _write_config(tmp_path / "bad.toml", "this is [not valid toml")
        with pytest.raises(ConfigError, match="Invalid TOML"):
            load_config(path)

    def test_missing_source_name_raises(self, tmp_path):
        content = """\
[sources.bad]
base_path = "/tmp"
"""
        path = _write_config(tmp_path / "config.toml", content)
        with pytest.raises(ConfigError, match="missing required field 'name'"):
            load_config(path)

    def test_missing_source_base_path_raises(self, tmp_path):
        content = """\
[sources.bad]
name = "Bad Source"
"""
        path = _write_config(tmp_path / "config.toml", content)
        with pytest.raises(ConfigError, match="missing required field 'base_path'"):
            load_config(path)

    def test_tilde_expansion(self, tmp_path):
        content = """\
[sources.home]
name = "Home"
base_path = "~/Documents"
"""
        path = _write_config(tmp_path / "config.toml", content)
        config = load_config(path)
        assert "~" not in config.sources["home"].base_path
        assert config.sources["home"].base_path == str(Path.home() / "Documents")

    def test_default_model_config(self, tmp_path):
        content = """\
[sources.s1]
name = "S1"
base_path = "/tmp"
"""
        path = _write_config(tmp_path / "config.toml", content)
        config = load_config(path)
        assert config.models.embedding.name == "BAAI/bge-base-en-v1.5"
        assert config.models.embedding.dimensions == 768

    def test_empty_sources(self, tmp_path):
        path = _write_config(tmp_path / "config.toml", 'log_level = "INFO"\n')
        config = load_config(path)
        assert config.sources == {}


class TestValidateConfig:
    def test_valid_config_no_errors(self, tmp_path):
        path = _write_config(tmp_path / "config.toml", VALID_CONFIG)
        config = load_config(path)
        errors = validate_config(config)
        assert errors == []

    def test_no_sources_error(self):
        config = KrisConfig()
        errors = validate_config(config)
        assert any("No sources configured" in e for e in errors)

    def test_relative_base_path_error(self, tmp_path):
        content = """\
[sources.rel]
name = "Relative"
base_path = "relative/path"
"""
        path = _write_config(tmp_path / "config.toml", content)
        config = load_config(path)
        errors = validate_config(config)
        assert any("must be absolute" in e for e in errors)

    def test_invalid_interval_error(self, tmp_path):
        content = """\
[sources.bad]
name = "Bad"
base_path = "/tmp"

[[sources.bad.schedules]]
interval_minutes = 0
"""
        path = _write_config(tmp_path / "config.toml", content)
        config = load_config(path)
        errors = validate_config(config)
        assert any("interval_minutes must be >= 1" in e for e in errors)


class TestKrisConfigProperties:
    def test_db_path(self, config_dir):
        config = KrisConfig()
        assert config.db_path == Path(config.data_dir) / "catalog.db"

    def test_qdrant_path(self, config_dir):
        config = KrisConfig()
        assert config.qdrant_path == Path(config.cache_dir) / "qdrant"


class TestGenerateDefaultConfig:
    def test_creates_config_file(self, tmp_path):
        path = tmp_path / "config.toml"
        result = generate_default_config(path)
        assert result == path
        assert path.exists()

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "a" / "b" / "config.toml"
        generate_default_config(path)
        assert path.exists()

    def test_raises_if_exists(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text("existing", encoding="utf-8")
        with pytest.raises(FileExistsError):
            generate_default_config(path)

    def test_force_overwrites(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text("old content", encoding="utf-8")
        generate_default_config(path, force=True)
        assert "kris configuration" in path.read_text(encoding="utf-8")

    def test_generated_config_is_loadable(self, tmp_path):
        path = tmp_path / "config.toml"
        generate_default_config(path)
        config = load_config(path)
        assert "my-files" in config.sources
