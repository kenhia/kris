"""kris cleanup CLI command — remove artifacts for missing/archived files."""

from __future__ import annotations

import re
from typing import Annotated

import typer
from rich.table import Table

from kris.catalog.db import get_connection
from kris.catalog.files import cleanup_missing_files
from kris.cli.app import (
    app,
    console,
    is_json_output,
    out_console,
    print_error,
    print_json_response,
)
from kris.config.schema import load_config
from kris.processing.embed import delete_points


def _parse_duration(duration_str: str) -> int:
    """Parse a duration string like '30d', '1w', '2m' to days."""
    match = re.match(r"^(\d+)\s*([dwm])$", duration_str.strip().lower())
    if not match:
        msg = f"Invalid duration format: '{duration_str}'. Use e.g. '30d', '4w', '2m'."
        raise typer.BadParameter(msg)
    value = int(match.group(1))
    unit = match.group(2)
    if unit == "d":
        return value
    if unit == "w":
        return value * 7
    # 'm' = months, approximate as 30 days
    return value * 30


@app.command()
def cleanup(
    config_path: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to kris config file"),
    ] = None,
    older_than: Annotated[
        str | None,
        typer.Option(
            "--older-than", help="Only files missing for longer than this (e.g., 30d, 1w)"
        ),
    ] = None,
    path: Annotated[
        str | None,
        typer.Option("--path", help="Only files matching this path pattern (SQL LIKE)"),
    ] = None,
    source: Annotated[
        str | None,
        typer.Option("--source", "-s", help="Only files from this source"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be removed without doing it"),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Remove artifacts for missing/archived files."""
    try:
        config = load_config(config_path)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1) from None

    older_than_days = _parse_duration(older_than) if older_than else None

    conn = get_connection(config.db_path)
    try:
        # First do a dry run to show what would be removed
        preview = cleanup_missing_files(
            conn,
            older_than_days=older_than_days,
            source_id=source,
            path_pattern=path,
            dry_run=True,
        )

        if preview["files_removed"] == 0:
            if is_json_output():
                print_json_response("cleanup", preview)
            else:
                console.print("[green]No missing files to clean up.[/green]")
            return

        if is_json_output():
            if not dry_run:
                result = cleanup_missing_files(
                    conn,
                    older_than_days=older_than_days,
                    source_id=source,
                    path_pattern=path,
                )
                # Delete Qdrant points
                qdrant_path = config.db_path.parent / "qdrant"
                if result["qdrant_point_ids"]:
                    delete_points(qdrant_path, result["qdrant_point_ids"])
                print_json_response("cleanup", result)
            else:
                print_json_response("cleanup", {**preview, "dry_run": True})
            return

        # Show preview
        table = Table(title="Cleanup Preview" if dry_run else "Files to Remove")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right")
        table.add_row("Files", str(preview["files_removed"]))
        table.add_row("Chunks", str(preview["chunks_removed"]))
        table.add_row("Embeddings", str(preview["embeddings_removed"]))
        table.add_row("Qdrant points", str(len(preview["qdrant_point_ids"])))
        out_console.print(table)

        if dry_run:
            console.print("[yellow]Dry run — no changes made.[/yellow]")
            return

        # Confirm unless --yes
        if not yes:
            confirm = typer.confirm("Proceed with cleanup?")
            if not confirm:
                console.print("[yellow]Aborted.[/yellow]")
                return

        # Execute cleanup
        result = cleanup_missing_files(
            conn,
            older_than_days=older_than_days,
            source_id=source,
            path_pattern=path,
        )

        # Delete Qdrant points
        qdrant_path = config.db_path.parent / "qdrant"
        if result["qdrant_point_ids"]:
            delete_points(qdrant_path, result["qdrant_point_ids"])

        console.print(
            f"[green]Removed {result['files_removed']} files, "
            f"{result['chunks_removed']} chunks, "
            f"{result['embeddings_removed']} embeddings.[/green]"
        )

    finally:
        conn.close()
