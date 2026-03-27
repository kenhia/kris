"""Unit tests for kris init and kris config validate CLI commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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


class TestMeasureModelVram:
    """T042 — verify measure_model_vram uses driver-level mem_get_info."""

    def test_function_exists(self):
        from kris.models.manager import measure_model_vram

        assert callable(measure_model_vram)

    def test_uses_mem_get_info_for_delta(self):
        """Verify we measure via mem_get_info (driver-level), not memory_allocated."""
        from kris.models.registry import ModelInfo

        info = ModelInfo(
            model_id="llm",
            model_type="llm",
            name="test-llm",
            path_or_repo="/tmp/test.gguf",
        )

        mock_torch = MagicMock()
        mock_torch.cuda.mem_get_info.side_effect = [
            (10 * 1024**3, 16 * 1024**3),  # before: 10 GB free
            (2 * 1024**3, 16 * 1024**3),  # after: 2 GB free → 8 GB used
        ]

        with (
            patch.dict("sys.modules", {"torch": mock_torch}),
            patch("kris.models.manager.ModelManager"),
        ):
            from kris.models.manager import measure_model_vram

            result = measure_model_vram(info)

        assert result == 8.0
        mock_torch.cuda.mem_get_info.assert_called()


class TestConfigUpdateModelSizes:
    """T043, T044, T045 — dry-run, no-GPU, OOM handling."""

    def test_dry_run_no_config_change(self, tmp_path):
        """T043 — verify config file is NOT modified on dry-run."""
        config_path = tmp_path / "config.toml"
        config_content = (
            '[sources.test]\nname = "Test"\nbase_path = "/tmp/test"\n\n'
            '[models.embedding]\nname = "test"\ndimensions = 768\nvram_gb = 0.5\n'
        )
        config_path.write_text(config_content, encoding="utf-8")

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True

        with (
            patch.dict("sys.modules", {"torch": mock_torch}),
            patch("kris.models.manager.measure_model_vram", return_value=1.2),
        ):
            result = runner.invoke(
                app,
                ["config", "update-model-sizes", "--config", str(config_path), "--dry-run"],
            )

        assert result.exit_code == 0
        assert config_path.read_text(encoding="utf-8") == config_content

    def test_no_gpu_warns_and_exits(self, tmp_path):
        """T044 — torch.cuda.is_available() returns False, command warns and exits."""
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            '[sources.test]\nname = "Test"\nbase_path = "/tmp/test"\n',
            encoding="utf-8",
        )

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False

        with patch.dict("sys.modules", {"torch": mock_torch}):
            result = runner.invoke(
                app, ["config", "update-model-sizes", "--config", str(config_path)]
            )

        assert result.exit_code == 0
        assert "No CUDA GPU" in result.output

    def test_oom_handling_reports_error_continues(self, tmp_path):
        """T045 — OOM: error caught, model reported as too large, others still run."""
        config_path = tmp_path / "config.toml"
        config_content = (
            '[sources.test]\nname = "Test"\nbase_path = "/tmp/test"\n\n'
            '[models.embedding]\nname = "emb-model"\ndimensions = 768\nvram_gb = 0.5\n\n'
            '[models.llm]\nname = "big-llm"\nmodel_path = "/tmp/llm.gguf"\nvram_gb = 2.0\n'
        )
        config_path.write_text(config_content, encoding="utf-8")

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True

        def side_effect(info):
            if info.model_type == "llm":
                raise RuntimeError("CUDA out of memory")
            return 1.5

        with (
            patch.dict("sys.modules", {"torch": mock_torch}),
            patch("kris.models.manager.measure_model_vram", side_effect=side_effect),
        ):
            result = runner.invoke(
                app,
                ["config", "update-model-sizes", "--config", str(config_path), "--dry-run"],
            )

        assert result.exit_code == 0
        # Embedding should succeed, LLM should show error
        assert "emb-model" in result.output
        assert "CUDA out of memory" in result.output
