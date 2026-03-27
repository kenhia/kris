"""kris diagnose — show failure/skip breakdowns and suggested excludes."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from kris.catalog.db import get_connection
from kris.catalog.files import (
    get_failed_by_extension,
    get_failure_path_prefixes,
    get_skipped_by_kind,
)
from kris.cli.app import app, console, is_json_output, print_error, print_json_response
from kris.config.schema import load_config


@app.command()
def diagnose(
    config_path: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to kris config file"),
    ] = None,
    source: Annotated[
        str | None,
        typer.Option("--source", "-s", help="Filter to this source ID"),
    ] = None,
    min_count: Annotated[
        int,
        typer.Option("--min-count", help="Minimum failure count for path prefix report"),
    ] = 5,
) -> None:
    """Show failure and skip diagnostics with suggested exclude patterns."""
    try:
        config = load_config(config_path)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1) from None

    conn = get_connection(config.db_path)
    json_output = is_json_output()

    try:
        failed_ext = get_failed_by_extension(conn, source)
        skipped = get_skipped_by_kind(conn, source)
        path_prefixes = get_failure_path_prefixes(conn, min_count, source)

        if json_output:
            print_json_response(
                "diagnose",
                {
                    "failed_by_extension": failed_ext,
                    "skipped_by_kind": skipped,
                    "failure_path_prefixes": path_prefixes,
                },
            )
            return

        # Failed by extension
        if failed_ext:
            table = Table(title="Failed Files by Extension")
            table.add_column("Extension", style="red")
            table.add_column("File Kind")
            table.add_column("Count", justify="right")
            for row in failed_ext:
                table.add_row(row["extension"], row["file_kind"], str(row["count"]))
            console.print(table)
            console.print()
        else:
            console.print("[green]No failed files.[/green]")
            console.print()

        # Skipped by kind
        if skipped:
            table = Table(title="Skipped Files by Kind")
            table.add_column("File Kind", style="yellow")
            table.add_column("Count", justify="right")
            for row in skipped:
                table.add_row(row["file_kind"], str(row["count"]))
            console.print(table)
            console.print()
        else:
            console.print("[green]No skipped files.[/green]")
            console.print()

        # Path prefixes with high failure count
        if path_prefixes:
            table = Table(title=f"Failure Hot Spots (>= {min_count} failures)")
            table.add_column("Directory Prefix", style="red")
            table.add_column("Failed Count", justify="right")
            for row in path_prefixes:
                table.add_row(row["top_dir"], str(row["failed_count"]))
            console.print(table)
            console.print()
            console.print(
                "[dim]Tip: Consider adding high-failure directories to exclude_patterns.[/dim]"
            )
        else:
            console.print(f"[green]No directory prefixes with >= {min_count} failures.[/green]")

    finally:
        conn.close()
