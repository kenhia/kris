"""kris init / config validate CLI commands."""

from __future__ import annotations

from typing import Annotated

import typer

from kris.cli.app import app, console, is_json_output, print_error, print_json_response
from kris.config.defaults import generate_default_config
from kris.config.schema import ConfigError, get_effective_excludes, load_config, validate_config

config_app = typer.Typer(name="config", help="Configuration management commands.")
app.add_typer(config_app)


@app.command()
def init(
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite existing config file"),
    ] = False,
) -> None:
    """Create a default configuration file."""
    json_output = is_json_output()
    try:
        path = generate_default_config(force=force)
        if json_output:
            print_json_response("init", {"config_path": str(path)})
        else:
            console.print(f"[green]Created config:[/green] {path}")
    except FileExistsError as e:
        print_error(str(e))
        raise typer.Exit(1) from None


@config_app.command("validate")
def config_validate(
    config_path: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to config file"),
    ] = None,
) -> None:
    """Validate the configuration file."""
    json_output = is_json_output()
    try:
        config = load_config(config_path)
    except ConfigError as e:
        if json_output:
            print_json_response("config validate", {"valid": False, "errors": [str(e)]})
        else:
            print_error(str(e))
        raise typer.Exit(1) from None

    errors = validate_config(config)
    if errors:
        if json_output:
            print_json_response("config validate", {"valid": False, "errors": errors})
        else:
            console.print("[red]Configuration invalid:[/red]")
            for err in errors:
                console.print(f"  - {err}")
        raise typer.Exit(1) from None

    if json_output:
        print_json_response("config validate", {"valid": True, "errors": []})
    else:
        console.print("[green]Configuration valid.[/green]")
        for source_id, source in config.sources.items():
            excludes = get_effective_excludes(source)
            console.print(f"  Source '{source_id}': {len(excludes)} effective exclude patterns")


@config_app.command("update-model-sizes")
def config_update_model_sizes(
    config_path: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to config file"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show measurements without updating config"),
    ] = False,
) -> None:
    """Measure actual VRAM per model and update config.toml."""
    json_output = is_json_output()

    try:
        config = load_config(config_path)
    except ConfigError as e:
        print_error(str(e))
        raise typer.Exit(1) from None

    # Check GPU availability
    try:
        import torch

        if not torch.cuda.is_available():
            msg = "No CUDA GPU available. Cannot measure VRAM."
            if json_output:
                print_json_response("config update-model-sizes", {"error": msg, "models": []})
            else:
                console.print(f"[yellow]{msg}[/yellow]")
            return
    except ImportError:
        msg = "torch not installed. Cannot measure VRAM."
        print_error(msg)
        raise typer.Exit(1) from None

    from kris.models.manager import measure_model_vram
    from kris.models.registry import ModelRegistry

    registry = ModelRegistry()
    registry.load_from_config(config)

    results = []
    for info in registry.list_all():
        try:
            vram_gb = measure_model_vram(info)
            results.append(
                {"model_id": info.model_id, "name": info.name, "vram_gb": vram_gb, "error": None}
            )
        except RuntimeError as e:
            results.append(
                {"model_id": info.model_id, "name": info.name, "vram_gb": None, "error": str(e)}
            )

    if json_output:
        print_json_response("config update-model-sizes", {"dry_run": dry_run, "models": results})
        if dry_run:
            return
    else:
        from rich.table import Table

        table = Table(title="Model VRAM Measurements")
        table.add_column("Model ID")
        table.add_column("Name")
        table.add_column("VRAM (GB)", justify="right")
        table.add_column("Status")

        for r in results:
            if r["error"]:
                table.add_row(r["model_id"], r["name"], "-", f"[red]{r['error']}[/red]")
            else:
                table.add_row(r["model_id"], r["name"], f"{r['vram_gb']:.2f}", "[green]OK[/green]")

        console.print(table)

        if dry_run:
            console.print("[dim]Dry run — config not modified.[/dim]")
            return

    # Update config file with tomlkit (preserves comments)
    from pathlib import Path

    import tomlkit

    from kris.config.schema import default_config_path

    cfg_path = Path(config_path) if config_path else default_config_path()
    doc = tomlkit.parse(cfg_path.read_text(encoding="utf-8"))

    updated = False
    models_table = doc.get("models")
    for r in results:
        if r["vram_gb"] is None:
            continue
        model_type = r["model_id"]  # "embedding" or "llm"
        if models_table is not None and model_type in models_table:
            models_table[model_type]["vram_gb"] = r["vram_gb"]
            updated = True

    if updated:
        cfg_path.write_text(tomlkit.dumps(doc), encoding="utf-8")
        if not json_output:
            console.print(f"[green]Updated {cfg_path}[/green]")
    elif not json_output:
        console.print("[yellow]No models to update in config.[/yellow]")
