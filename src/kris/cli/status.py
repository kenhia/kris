"""kris status CLI command — show index statistics."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from kris.catalog.db import get_connection
from kris.catalog.files import get_failed_files, get_status_summary
from kris.cli.app import (
    app,
    console,
    is_json_output,
    out_console,
    print_error,
    print_json_response,
)
from kris.config.schema import load_config


@app.command()
def status(
    config_path: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to kris config file"),
    ] = None,
    source: Annotated[
        str | None,
        typer.Option("--source", "-s", help="Show status for a specific source"),
    ] = None,
    show_failed: Annotated[
        bool,
        typer.Option("--show-failed", "-f", help="Show full failed-files table"),
    ] = False,
) -> None:
    """Show index statistics."""
    try:
        config = load_config(config_path)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1) from None

    conn = get_connection(config.db_path)
    json_output = is_json_output()

    try:
        summary = get_status_summary(conn, source_id=source)
        failed = get_failed_files(conn, source_id=source)

        if json_output:
            print_json_response(
                "status",
                {
                    "sources": [
                        {
                            "source_id": s["source_id"],
                            "source_name": s["source_name"],
                            "last_scan": s["last_scan"],
                            "total_files": s["total_files"],
                            "by_kind": s["by_kind"],
                            "by_status": s["by_status"],
                            "total_chunks": s["total_chunks"],
                            "total_embeddings": s["total_embeddings"],
                        }
                        for s in summary
                    ],
                    "failed_files": [
                        {
                            "path": f["path"],
                            "source_id": f["source_id"],
                            "error": f["error"],
                        }
                        for f in failed
                    ],
                },
            )
            return

        if not summary:
            console.print("[yellow]No sources found.[/yellow]")
            return

        # Summary table
        table = Table(title="Index Status")
        table.add_column("Source", style="cyan")
        table.add_column("Files", justify="right")
        table.add_column("By Kind")
        table.add_column("By Status")
        table.add_column("Chunks", justify="right")
        table.add_column("Embeddings", justify="right")
        table.add_column("Last Scan")

        for s in summary:
            kind_str = ", ".join(f"{k}: {v}" for k, v in sorted(s["by_kind"].items()))
            status_str = ", ".join(f"{k}: {v}" for k, v in sorted(s["by_status"].items()))
            table.add_row(
                f"{s['source_name']} ({s['source_id']})",
                str(s["total_files"]),
                kind_str,
                status_str,
                str(s["total_chunks"]),
                str(s["total_embeddings"]),
                s["last_scan"] or "never",
            )

        out_console.print(table)

        # Failed files section
        if failed and show_failed:
            out_console.print()
            fail_table = Table(title="Failed Files", style="red")
            fail_table.add_column("Source", style="dim")
            fail_table.add_column("Path", style="cyan")
            fail_table.add_column("Error")

            for f in failed:
                fail_table.add_row(f["source_id"], f["path"], f["error"] or "Unknown")

            out_console.print(fail_table)
        elif failed:
            msg = f"{len(failed)} failed file(s). Use --show-failed to see details."
            out_console.print(f"\n[yellow]{msg}[/yellow]")

    finally:
        conn.close()
