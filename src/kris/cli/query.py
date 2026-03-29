"""kris query / retrieve CLI commands — semantic search and LLM synthesis."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from kris.catalog.db import get_connection
from kris.cli.app import app, is_json_output, print_error, print_json_response
from kris.config.schema import load_config
from kris.models.manager import ModelManager
from kris.models.registry import ModelRegistry
from kris.query.engine import query as run_query
from kris.query.synthesizer import format_sources


@app.command()
def query(
    question: Annotated[str, typer.Argument(help="Natural language question")],
    config_path: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to kris config file"),
    ] = None,
    show_sources: Annotated[
        bool,
        typer.Option("--show-sources", help="Display source chunks alongside the answer"),
    ] = False,
    top_k: Annotated[
        int,
        typer.Option("--top-k", "-k", help="Number of chunks to retrieve"),
    ] = 10,
    source: Annotated[
        str | None,
        typer.Option("--source", "-s", help="Limit search to a specific source"),
    ] = None,
    kind: Annotated[
        str | None,
        typer.Option("--kind", help="Limit search to a specific file kind"),
    ] = None,
) -> None:
    """Ask a question and get an LLM-synthesized answer with source citations."""
    try:
        config = load_config(config_path)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1) from None

    conn = get_connection(config.db_path)
    registry = ModelRegistry()
    registry.load_from_config(config)
    model_manager = ModelManager()

    json_output = is_json_output()

    try:
        result = run_query(
            question=question,
            conn=conn,
            model_manager=model_manager,
            registry=registry,
            config=config,
            top_k=top_k,
            source_filter=source,
            kind_filter=kind,
            retrieval_only=False,
        )

        if json_output:
            print_json_response(
                "query",
                {
                    "question": result.question,
                    "answer": result.answer,
                    "sources": [
                        {
                            "file_path": r.file_path,
                            "source_id": r.source_id,
                            "file_kind": r.file_kind,
                            "score": r.score,
                            "chunk_text": r.chunk_text,
                        }
                        for r in result.results
                    ],
                },
            )
        else:
            out = Console()
            out.print()
            out.print(Panel(result.answer or "", title="Answer", border_style="green"))

            if show_sources and result.results:
                out.print()
                out.print(format_sources(result.results))

    except RuntimeError as e:
        print_error(str(e))
        raise typer.Exit(1) from None
    finally:
        model_manager.unload()
        conn.close()


@app.command()
def retrieve(
    query_text: Annotated[str, typer.Argument(help="Search query", metavar="QUERY")],
    config_path: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to kris config file"),
    ] = None,
    top_k: Annotated[
        int,
        typer.Option("--top-k", "-k", help="Number of chunks to return"),
    ] = 10,
    source: Annotated[
        str | None,
        typer.Option("--source", "-s", help="Limit search to a specific source"),
    ] = None,
    kind: Annotated[
        str | None,
        typer.Option("--kind", help="Limit search to a specific file kind"),
    ] = None,
) -> None:
    """Retrieve relevant chunks without LLM synthesis."""
    try:
        config = load_config(config_path)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1) from None

    conn = get_connection(config.db_path)
    registry = ModelRegistry()
    registry.load_from_config(config)
    model_manager = ModelManager()

    json_output = is_json_output()

    try:
        result = run_query(
            question=query_text,
            conn=conn,
            model_manager=model_manager,
            registry=registry,
            config=config,
            top_k=top_k,
            source_filter=source,
            kind_filter=kind,
            retrieval_only=True,
        )

        if json_output:
            print_json_response(
                "retrieve",
                {
                    "query": result.question,
                    "results": [
                        {
                            "file_path": r.file_path,
                            "source_id": r.source_id,
                            "source_name": r.source_name,
                            "file_kind": r.file_kind,
                            "chunk_index": r.chunk_index,
                            "score": r.score,
                            "chunk_text": r.chunk_text,
                        }
                        for r in result.results
                    ],
                },
            )
        else:
            out = Console()
            if not result.results:
                out.print("[yellow]No relevant chunks found.[/yellow]")
                return

            table = Table(title=f"Results for: {result.question}")
            table.add_column("#", style="dim", width=3)
            table.add_column("Score", width=6)
            table.add_column("File", style="cyan")
            table.add_column("Kind", width=8)
            table.add_column("Chunk", max_width=60)

            for i, r in enumerate(result.results, 1):
                preview = r.chunk_text[:100].replace("\n", " ")
                if len(r.chunk_text) > 100:
                    preview += "..."
                table.add_row(
                    str(i),
                    f"{r.score:.2f}",
                    r.file_path,
                    r.file_kind,
                    preview,
                )

            out.print(table)

    except RuntimeError as e:
        print_error(str(e))
        raise typer.Exit(1) from None
    finally:
        model_manager.unload()
        conn.close()
