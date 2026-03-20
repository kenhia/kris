"""kris CLI — main application entry point."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
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


def setup_logging(verbose: int) -> None:
    """Configure structured logging with rotating log file."""
    from kris.config.schema import default_data_dir

    # Map verbosity to log levels: 0=WARNING, 1=INFO, 2=DEBUG, 3+=DEBUG
    level_map = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    level = level_map.get(min(verbose, 2), logging.DEBUG)

    log_dir = default_data_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "kris.log"

    fmt = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S"

    # File handler — always logs at DEBUG for diagnostics
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    # Stderr handler — respects verbosity
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(level)
    stderr_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(stderr_handler)


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
    setup_logging(verbose)


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
import kris.cli.cleanup  # noqa: E402
import kris.cli.config_cmd  # noqa: E402
import kris.cli.duplicates  # noqa: E402
import kris.cli.index  # noqa: E402
import kris.cli.query  # noqa: E402
import kris.cli.status  # noqa: E402, F401
