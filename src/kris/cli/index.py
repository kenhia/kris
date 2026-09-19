"""kris index CLI command — scan, plan, extract, chunk, embed."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated

import typer
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from kris.catalog.db import get_connection
from kris.catalog.tasks import count_tasks_by_status
from kris.cli.app import app, console, is_json_output, print_error, print_json_response
from kris.config.schema import get_effective_excludes, load_config
from kris.models.manager import ModelManager
from kris.models.registry import ModelRegistry
from kris.planner.planner import plan_pending_content
from kris.processing.worker import run_worker
from kris.scanner import ScannerError, run_scanner


@app.command()
def index(
    config_path: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to kris config file"),
    ] = None,
    source: Annotated[
        str | None,
        typer.Option("--source", "-s", help="Index only this source ID"),
    ] = None,
) -> None:
    """Scan, extract, chunk, and embed files from configured sources."""
    try:
        config = load_config(config_path)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1) from None

    sources = config.sources
    if source:
        if source not in sources:
            print_error(f"Source '{source}' not found in config")
            raise typer.Exit(1) from None
        sources = {source: sources[source]}

    if not sources:
        print_error("No sources configured")
        raise typer.Exit(1) from None

    db_path = config.db_path
    data_dir = Path(config.data_dir)

    conn = get_connection(db_path)

    # Set up model registry and manager
    registry = ModelRegistry()
    registry.load_from_config(config)
    model_manager = ModelManager()

    total_scan = {"files_found": 0, "files_new": 0, "errors": 0}
    total_tasks = {"completed": 0, "failed": 0}

    json_output = is_json_output()

    try:
        # Phase 1: Scan all sources
        if not json_output:
            console.print("[bold]Scanning sources...[/bold]")

        for source_id, source_cfg in sources.items():
            _ensure_source_exists(conn, source_id, source_cfg)

            if not json_output:
                console.print(f"  Scanning {source_cfg.name} ({source_cfg.base_path})")

            try:
                result = run_scanner(
                    db_path=db_path,
                    source_id=source_id,
                    base_path=Path(source_cfg.base_path),
                    exclude_patterns=get_effective_excludes(source_cfg),
                    follow_symlinks=False,
                )
                total_scan["files_found"] += result.files_found
                total_scan["files_new"] += result.files_new
                total_scan["errors"] += result.errors

                if not json_output:
                    console.print(f"    Found {result.files_found} files ({result.files_new} new)")
            except ScannerError as e:
                total_scan["errors"] += 1
                if not json_output:
                    console.print(f"    [red]Scanner error:[/red] {e}")

        # Phase 2: Plan tasks
        planned = plan_pending_content(conn)
        if not json_output:
            console.print(f"\n[bold]Planned {planned} content items for processing[/bold]")

        # Phase 3: Execute tasks with progress
        if planned > 0:
            queued_total = count_tasks_by_status(conn, "queued")
            if not json_output:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("{task.completed}/{task.total}"),
                    TimeElapsedColumn(),
                    console=console,
                ) as progress:
                    task_id = progress.add_task("Processing...", total=queued_total)

                    def on_progress(completed: int, failed: int) -> None:
                        progress.update(task_id, completed=completed + failed)

                    completed, failed = run_worker(
                        conn,
                        data_dir,
                        config,
                        model_manager,
                        registry,
                        on_progress=on_progress,
                    )
                    total_tasks["completed"] = completed
                    total_tasks["failed"] = failed
            else:
                completed, failed = run_worker(conn, data_dir, config, model_manager, registry)
                total_tasks["completed"] = completed
                total_tasks["failed"] = failed

        # Output
        if json_output:
            print_json_response(
                "index",
                {
                    "scan": total_scan,
                    "tasks": total_tasks,
                },
            )
        else:
            console.print("\n[bold green]Index complete.[/bold green]")
            console.print(f"  Files scanned: {total_scan['files_found']}")
            console.print(f"  New files: {total_scan['files_new']}")
            console.print(f"  Tasks completed: {total_tasks['completed']}")
            if total_tasks["failed"]:
                console.print(f"  [red]Tasks failed: {total_tasks['failed']}[/red]")
            if total_scan["errors"]:
                console.print(f"  [yellow]Scan errors: {total_scan['errors']}[/yellow]")

    finally:
        model_manager.unload()
        conn.close()


def _ensure_source_exists(
    conn: sqlite3.Connection,
    source_id: str,
    source_cfg,
) -> None:
    """Insert the source record if it doesn't exist."""
    existing = conn.execute("SELECT id FROM source WHERE id = ?", (source_id,)).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO source (id, name, source_type, base_path) VALUES (?, ?, ?, ?)",
            (source_id, source_cfg.name, source_cfg.source_type, source_cfg.base_path),
        )
        conn.commit()
