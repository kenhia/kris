"""kris CLI — main application entry point."""

from __future__ import annotations

import sys
from typing import Annotated

import typer
from rich.console import Console

app = typer.Typer(
    name="kris",
    help="Personal data intelligence — index, analyze, and query your files.",
    no_args_is_help=True,
)

console = Console(stderr=True)
out_console = Console()

# Global state shared across commands
_json_output: bool = False
_verbose: int = 0


def is_json_output() -> bool:
    return _json_output


def verbosity() -> int:
    return _verbose


@app.callback()
def main(
    json_output: Annotated[bool, typer.Option("--json", help="Output in JSON format")] = False,
    verbose: Annotated[
        int,
        typer.Option("--verbose", "-v", count=True, help="Increase verbosity (-v, -vv, -vvv)"),
    ] = 0,
) -> None:
    """kris — personal data intelligence."""
    global _json_output, _verbose
    _json_output = json_output
    _verbose = verbose


def print_error(message: str) -> None:
    """Print an error message to stderr."""
    if _json_output:
        import json

        sys.stderr.write(json.dumps({"status": "error", "error": {"message": message}}) + "\n")
    else:
        console.print(f"[red]Error:[/red] {message}")


def print_json_response(command: str, data: dict) -> None:
    """Print a structured JSON response to stdout."""
    import json

    out_console.print_json(json.dumps({"status": "ok", "command": command, "data": data}))


# Import subcommand modules to register them with the app
import kris.cli.index  # noqa: F401, E402
