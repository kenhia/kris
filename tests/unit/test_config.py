"""Unit tests for config loading, validation, defaults, and XDG path resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from kris.config.defaults import DEFAULT_EXCLUDE_PATTERNS, generate_default_config
from kris.config.schema import (
    ConfigError,
    KrisConfig,
    QdrantConfig,
    SourceConfig,
    default_cache_dir,
    default_config_path,
    default_data_dir,
    get_effective_excludes,
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


MULTI_SOURCE_CONFIG = """\
[sources.home]
name = "Home"
base_path = "/home/user"
exclude_patterns = [".git", "node_modules"]

[[sources.home.schedules]]
path_pattern = "**"
interval_minutes = 30

[sources.nas]
name = "NAS"
base_path = "/mnt/nas"
exclude_patterns = [".git"]

[[sources.nas.schedules]]
path_pattern = "**/*.py"
interval_minutes = 120
priority = 2

[[sources.nas.schedules]]
path_pattern = "docs/**"
interval_minutes = 60
priority = 1
"""


class TestMultiSourceConfig:
    def test_loads_multiple_sources(self, tmp_path):
        path = _write_config(tmp_path / "config.toml", MULTI_SOURCE_CONFIG)
        config = load_config(path)
        assert len(config.sources) == 2
        assert "home" in config.sources
        assert "nas" in config.sources

    def test_per_source_exclude_patterns(self, tmp_path):
        path = _write_config(tmp_path / "config.toml", MULTI_SOURCE_CONFIG)
        config = load_config(path)
        assert config.sources["home"].exclude_patterns == [".git", "node_modules"]
        assert config.sources["nas"].exclude_patterns == [".git"]

    def test_per_source_schedules(self, tmp_path):
        path = _write_config(tmp_path / "config.toml", MULTI_SOURCE_CONFIG)
        config = load_config(path)
        assert len(config.sources["home"].schedules) == 1
        assert config.sources["home"].schedules[0].interval_minutes == 30
        assert len(config.sources["nas"].schedules) == 2
        assert config.sources["nas"].schedules[0].path_pattern == "**/*.py"
        assert config.sources["nas"].schedules[1].interval_minutes == 60

    def test_validate_multi_source_valid(self, tmp_path):
        path = _write_config(tmp_path / "config.toml", MULTI_SOURCE_CONFIG)
        config = load_config(path)
        errors = validate_config(config)
        assert errors == []


class TestGetEffectiveExcludes:
    """T008 — verify merge and opt-out behavior."""

    def test_merges_default_and_source_patterns(self):
        source = SourceConfig(
            name="Test",
            base_path="/tmp",
            exclude_patterns=[".scratch-agent", ".git"],  # .git is a duplicate
        )
        result = get_effective_excludes(source)
        # All defaults should be present
        for pat in DEFAULT_EXCLUDE_PATTERNS:
            assert pat in result
        # Source-specific pattern should be present
        assert ".scratch-agent" in result
        # No duplicates
        assert result.count(".git") == 1

    def test_opt_out_with_include_false(self):
        source = SourceConfig(
            name="Test",
            base_path="/tmp",
            exclude_patterns=[".git", "custom"],
            include_default_exclude_patterns=False,
        )
        result = get_effective_excludes(source)
        assert result == [".git", "custom"]
        # Should NOT contain defaults beyond what was explicitly listed
        assert "node_modules" not in result

    def test_defaults_only_when_no_source_patterns(self):
        source = SourceConfig(name="Test", base_path="/tmp")
        result = get_effective_excludes(source)
        assert result == DEFAULT_EXCLUDE_PATTERNS

    def test_preserves_order_defaults_first(self):
        source = SourceConfig(
            name="Test",
            base_path="/tmp",
            exclude_patterns=["zzz_custom"],
        )
        result = get_effective_excludes(source)
        # Defaults come first, then source-specific
        default_last_idx = result.index(DEFAULT_EXCLUDE_PATTERNS[-1])
        custom_idx = result.index("zzz_custom")
        assert custom_idx > default_last_idx


class TestQdrantConfig:
    """T009 — verify QdrantConfig defaults and validation."""

    def test_defaults(self):
        qc = QdrantConfig()
        assert qc.mode == "embedded"
        assert qc.url == "http://localhost:6333"
        assert qc.api_key == ""

    def test_server_mode(self):
        qc = QdrantConfig(mode="server", url="http://qdrant:6333", api_key="secret")
        assert qc.mode == "server"
        assert qc.url == "http://qdrant:6333"
        assert qc.api_key == "secret"

    def test_parsed_from_toml(self, tmp_path):
        content = """\
[sources.s1]
name = "S1"
base_path = "/tmp"

[qdrant]
mode = "server"
url = "http://myhost:6333"
api_key = "mykey"
"""
        path = _write_config(tmp_path / "config.toml", content)
        config = load_config(path)
        assert config.qdrant.mode == "server"
        assert config.qdrant.url == "http://myhost:6333"
        assert config.qdrant.api_key == "mykey"


class TestBackwardCompatibility:
    """T010 — config with no [qdrant] section or default_exclude_patterns loads with defaults."""

    def test_no_qdrant_section(self, tmp_path):
        content = """\
[sources.s1]
name = "S1"
base_path = "/tmp"
"""
        path = _write_config(tmp_path / "config.toml", content)
        config = load_config(path)
        assert config.qdrant.mode == "embedded"
        assert config.qdrant.url == "http://localhost:6333"

    def test_no_include_default_exclude_patterns(self, tmp_path):
        content = """\
[sources.s1]
name = "S1"
base_path = "/tmp"
exclude_patterns = [".git"]
"""
        path = _write_config(tmp_path / "config.toml", content)
        config = load_config(path)
        # Should default to True
        assert config.sources["s1"].include_default_exclude_patterns is True

    def test_existing_valid_config_still_loads(self, tmp_path):
        """The MVP-era VALID_CONFIG fixture still works without changes."""
        path = _write_config(tmp_path / "config.toml", VALID_CONFIG)
        config = load_config(path)
        assert "test-src" in config.sources
        assert config.qdrant.mode == "embedded"
        assert config.sources["test-src"].include_default_exclude_patterns is True


class TestCreateQdrantClient:
    """T012 — verify embedded vs server mode client creation."""

    def test_embedded_mode(self, tmp_path):
        from kris.processing.embed import create_qdrant_client

        config = KrisConfig(qdrant=QdrantConfig(mode="embedded"))
        client = create_qdrant_client(config, qdrant_path=tmp_path / "qdrant")
        # The embedded client should have been created with a path
        assert client is not None

    def test_server_mode(self):
        from unittest.mock import MagicMock, patch

        from kris.processing.embed import create_qdrant_client

        config = KrisConfig(
            qdrant=QdrantConfig(mode="server", url="http://testhost:6333", api_key="key123")
        )
        with patch("qdrant_client.QdrantClient") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            client = create_qdrant_client(config)
            mock_cls.assert_called_once_with(url="http://testhost:6333", api_key="key123")
            assert client is mock_instance

    def test_server_mode_connection_error(self):
        """T035 — server mode with unreachable URL produces actionable error."""
        from unittest.mock import MagicMock, patch

        from kris.processing.embed import create_qdrant_client

        config = KrisConfig(qdrant=QdrantConfig(mode="server", url="http://unreachable:6333"))
        with patch("qdrant_client.QdrantClient") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.get_collections.side_effect = Exception("Connection refused")
            mock_cls.return_value = mock_instance
            with pytest.raises(ConnectionError, match="Cannot connect to Qdrant server"):
                create_qdrant_client(config)
