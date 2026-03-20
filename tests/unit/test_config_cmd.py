"""Unit tests for kris init and kris config validate CLI commands."""

from __future__ import annotations

from typer.testing import CliRunner

from kris.cli.app import app

runner = CliRunner()


class TestInitCommand:
    def test_init_creates_config(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config" / "kris" / "config.toml"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert config_path.exists()
        assert "kris configuration" in config_path.read_text(encoding="utf-8")

    def test_init_prints_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "config.toml" in result.stdout or "config.toml" in result.output

    def test_init_fails_if_exists(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config" / "kris" / "config.toml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("existing", encoding="utf-8")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 1

    def test_init_force_overwrites(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config" / "kris" / "config.toml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("old", encoding="utf-8")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        result = runner.invoke(app, ["init", "--force"])
        assert result.exit_code == 0
        assert "kris configuration" in config_path.read_text(encoding="utf-8")

    def test_init_json_output(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        result = runner.invoke(app, ["--json", "init"])
        assert result.exit_code == 0
        assert "config_path" in result.output


class TestConfigValidateCommand:
    def test_validate_valid_config(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            '[sources.test]\nname = "Test"\nbase_path = "/tmp/test"\n',
            encoding="utf-8",
        )
        result = runner.invoke(app, ["config", "validate", "--config", str(config_path)])
        assert result.exit_code == 0

    def test_validate_invalid_config(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            '[sources.test]\nname = "Test"\nbase_path = "relative/path"\n',
            encoding="utf-8",
        )
        result = runner.invoke(app, ["config", "validate", "--config", str(config_path)])
        assert result.exit_code == 1

    def test_validate_missing_file(self, tmp_path):
        result = runner.invoke(
            app, ["config", "validate", "--config", str(tmp_path / "missing.toml")]
        )
        assert result.exit_code == 1

    def test_validate_json_output(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            '[sources.test]\nname = "Test"\nbase_path = "/tmp/test"\n',
            encoding="utf-8",
        )
        result = runner.invoke(app, ["--json", "config", "validate", "--config", str(config_path)])
        assert result.exit_code == 0
        assert "valid" in result.output.lower() or "ok" in result.output.lower()
