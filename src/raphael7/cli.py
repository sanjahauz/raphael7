"""Command-line interface."""

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from raphael7 import __version__
from raphael7.scan.json_report import report_to_dict
from raphael7.scan.report import scan_folder
from raphael7.scan.terminal import print_report

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
    """Group a folder of messages by sender and shape, and flag the odd ones out.

    Exits with 1 when there are odd ones out, so a CI job fails on a new one.
    """
    report = scan_folder(folder)
    if json_output:
        typer.echo(json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
    else:
        print_report(report, Console())
    if report.outliers:
        raise typer.Exit(code=1)
