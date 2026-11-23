"""Command-line interface."""

from pathlib import Path
from typing import Annotated

import typer

from raphael7 import __version__

app = typer.Typer(
    name="raphael7",
    help="Scan messy HL7 v2 feeds, test parsing and check v2 → FHIR output.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"raphael7 {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """Raphael7 command-line tool."""


@app.command()
def scan(
    folder: Annotated[
        Path, typer.Argument(exists=True, file_okay=False, help="Folder of HL7 v2 messages.")
    ],
    json_output: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
) -> None:
    """Group a folder of messages by structure and flag outliers."""
    typer.echo("scan is not implemented yet.", err=True)
    raise typer.Exit(code=1)
