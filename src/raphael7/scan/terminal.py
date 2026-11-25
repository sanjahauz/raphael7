"""The scan report for people, in the terminal (Rich).

Read top to bottom, it answers in order: what is in this folder (senders,
their feeds and shapes), what to open first (odd ones out), and what is
true of a whole feed (habits, Z-segments).
"""

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from raphael7.scan.json_report import example_message
from raphael7.scan.neighbours import Neighbour
from raphael7.scan.report import ScanReport
from raphael7.scan.shapes import Feed, Shape
from raphael7.scan.signature import Sender

# Beyond this many "sometimes filled" fields per shape, show a count instead.
MAX_SOMETIMES_SHOWN = 5


def print_report(report: ScanReport, console: Console) -> None:
    flagged = set()
    for outlier in report.outliers:
        flagged.add(outlier.where)

    _print_summary(report, console)
    _print_senders(report, flagged, console)
    _print_outliers(report, console)
    _print_habits(report, console)
    _print_z_segments(report, console)


def _print_summary(report: ScanReport, console: Console) -> None:
    console.print(
        f"[bold]raphael7 scan[/] {escape(report.folder)}: "
        f"{report.file_count} files, {report.message_count} messages, "
        f"{len(report.feeds)} feeds, "
        f"[bold]{len(report.outliers)} odd ones out[/]"
    )


def _print_senders(report: ScanReport, flagged: set[str], console: Console) -> None:
    feeds_by_sender: dict[Sender, list[Feed]] = {}
    for feed in report.feeds:
        feeds_by_sender.setdefault(feed.sender, []).append(feed)

    neighbour_by_feed: dict[int, Neighbour] = {}
    for neighbour in report.neighbours:
        neighbour_by_feed[id(neighbour.feed)] = neighbour

    for sender, feeds in feeds_by_sender.items():
        console.print()
        console.print(f"[bold cyan]{escape(str(sender))}[/]")
        for feed in feeds:
            _print_feed(feed, flagged, neighbour_by_feed.get(id(feed)), console)


def _print_feed(
    feed: Feed, flagged: set[str], neighbour: Neighbour | None, console: Console
) -> None:
    versions = ", ".join(_text(version) for version in feed.versions())
    console.print(
        f"  [bold]{escape(_text(feed.message_type))}[/]  "
        f"{feed.message_count} messages, version {escape(versions)}"
    )
    show_version = len(feed.versions()) > 1
    for shape in feed.shapes:
        _print_shape(shape, flagged, show_version, console)
    if neighbour is not None:
        console.print(f"    [dim]{escape(_neighbour_text(neighbour))}[/]")


def _print_shape(shape: Shape, flagged: set[str], show_version: bool, console: Console) -> None:
    """One line per shape; the version only when the feed has more than one."""
    example = example_message(shape, flagged)
    version = f"version {_text(shape.version)}, " if show_version else ""
    console.print(
        f"    {shape.message_count:>5}  {escape(' '.join(shape.segments))}"
        f"  [dim]{escape(version)}e.g. {escape(str(example))}[/]"
    )
    sometimes = shape.sometimes_filled()
    if not sometimes:
        return
    parts = []
    for usage in sometimes[:MAX_SOMETIMES_SHOWN]:
        parts.append(f"{usage.position} {usage.filled}/{usage.total}")
    hidden = len(sometimes) - MAX_SOMETIMES_SHOWN
    if hidden > 0:
        parts.append(f"+{hidden} more")
    console.print(f"           [dim]sometimes filled: {escape(', '.join(parts))}[/]")


def _neighbour_text(neighbour: Neighbour) -> str:
    """E.g. "closest: OLDHIS at HOSP_EAST, 94% same fields; they also fill MSH-18, PV1-20"."""
    percent = round(neighbour.score * 100)
    text = f"closest: {neighbour.other.sender}, {percent}% same fields"
    if neighbour.only_here:
        text += "; this feed also fills " + _position_list(neighbour.only_here)
    if neighbour.only_there:
        text += "; they also fill " + _position_list(neighbour.only_there)
    return text


def _print_outliers(report: ScanReport, console: Console) -> None:
    console.print()
    if not report.outliers:
        console.print("[bold green]No odd ones out.[/]")
        return
    table = Table(title=f"Odd ones out ({len(report.outliers)})", title_justify="left")
    table.add_column("Message or file", overflow="fold")
    table.add_column("Reason")
    table.add_column("Details", overflow="fold")
    for outlier in report.outliers:
        for index, reason in enumerate(outlier.reasons):
            where = outlier.where if index == 0 else ""
            table.add_row(escape(where), reason.code, escape(reason.text))
    console.print(table)


def _print_habits(report: ScanReport, console: Console) -> None:
    """One line per sender and issue, summed over that sender's feeds."""
    if not report.habits:
        return
    messages: dict[tuple[Sender, str], int] = {}
    feeds: dict[tuple[Sender, str], int] = {}
    for habit in report.habits:
        key = (habit.feed.sender, habit.code)
        messages[key] = messages.get(key, 0) + habit.count
        feeds[key] = feeds.get(key, 0) + 1
    console.print()
    console.print("[bold]Habits[/] (in at least half of a feed, so not counted as odd)")
    for key, count in messages.items():
        sender, code = key
        console.print(f"  {escape(str(sender))}: {code} in {count} messages, {feeds[key]} feeds")


def _print_z_segments(report: ScanReport, console: Console) -> None:
    console.print()
    if not report.z_segments:
        console.print("[bold]Z-segments[/]: none")
        return
    console.print("[bold]Z-segments[/]")
    for use in report.z_segments:
        types = ", ".join(use.message_types)
        console.print(
            f"  {escape(str(use.sender))}: {use.segment} in {use.messages} messages ({types})"
        )


def _position_list(positions) -> str:
    names = []
    for position in positions:
        names.append(str(position))
    return ", ".join(names)


def _text(value: str | None) -> str:
    return value if value else "?"
