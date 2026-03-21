"""kris init / config validate CLI commands."""

from __future__ import annotations

from typing import Annotated

import typer

from kris.cli.app import app, console, is_json_output, print_error, print_json_response
from kris.config.defaults import generate_default_config
from kris.config.schema import ConfigError, load_config, validate_config

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
