"""kris duplicates CLI command — list groups of files with identical content."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from kris.catalog.content import get_duplicate_groups
from kris.catalog.db import get_connection
from kris.cli.app import (
    app,
    console,
    is_json_output,
    out_console,
    print_error,
    print_json_response,
)
from kris.config.schema import load_config


def _parse_size(size_str: str) -> int:
    """Parse a human-readable size string (e.g. '1KB', '10MB') to bytes."""
    size_str = size_str.strip().upper()
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
    for suffix, mult in sorted(multipliers.items(), key=lambda x: -len(x[0])):
        if size_str.endswith(suffix):
            return int(float(size_str[: -len(suffix)].strip()) * mult)
    return int(size_str)


@app.command()
def duplicates(
    config_path: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to kris config file"),
    ] = None,
    source: Annotated[
        str | None,
        typer.Option("--source", "-s", help="Limit to a specific source"),
    ] = None,
    min_size: Annotated[
        str | None,
        typer.Option("--min-size", help="Minimum file size to report (e.g., 1KB, 1MB)"),
    ] = None,
) -> None:
    """List groups of files with identical content."""
    try:
        config = load_config(config_path)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1) from None

    min_size_bytes = _parse_size(min_size) if min_size else None

    conn = get_connection(config.db_path)
    try:
        groups = get_duplicate_groups(conn, source_id=source, min_size=min_size_bytes)

        if is_json_output():
            print_json_response("duplicates", {"groups": groups})
            return

        if not groups:
            console.print("[green]No duplicate files found.[/green]")
            return

        for group in groups:
            table = Table(
                title=f"Duplicate group: {group['content_hash'][:12]}… ({group['count']} files)",
            )
            table.add_column("Source", style="dim")
            table.add_column("Path", style="cyan")
            table.add_column("Size", justify="right")

            for f in group["files"]:
                table.add_row(f["source_id"], f["path"], _format_size(f["size"]))

            out_console.print(table)
            out_console.print()

    finally:
        conn.close()


def _format_size(size: int) -> str:
    """Format bytes as human-readable size."""
    s = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if s < 1024:
            return f"{s:.0f} {unit}" if unit == "B" else f"{s:.1f} {unit}"
        s /= 1024
    return f"{s:.1f} TB"
