"""kris CLI — main application entry point."""

import typer

app = typer.Typer(
    name="kris",
    help="Personal data intelligence — index, analyze, and query your files.",
    no_args_is_help=True,
)
