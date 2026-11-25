"""The scan report as plain JSON data, for scripts and snapshot tests.

The order is stable (the same folder always gives the same JSON), and the
shape of the data has a version number, so a script can tell when it
changes. Message lists are not included, so the JSON stays small on a
large feed: each shape names one example message to open.
"""

from raphael7.scan.files import MessageRef
from raphael7.scan.report import ScanReport
from raphael7.scan.shapes import Feed, Shape
from raphael7.scan.signature import Position, Sender

FORMAT_VERSION = 1


def report_to_dict(report: ScanReport) -> dict:
    flagged = set()
    for outlier in report.outliers:
        flagged.add(outlier.where)

    feeds = []
    for feed in report.feeds:
        feeds.append(_feed(feed, flagged))

    outliers = []
    for outlier in report.outliers:
        reasons = []
        for reason in outlier.reasons:
            reasons.append({"code": reason.code, "text": reason.text})
        outliers.append({"where": outlier.where, "reasons": reasons})

    habits = []
    for habit in report.habits:
        habits.append(
            {
                "sender": _sender(habit.feed.sender),
                "message_type": habit.feed.message_type,
                "code": habit.code,
                "messages": habit.count,
            }
        )

    neighbours = []
    for neighbour in report.neighbours:
        neighbours.append(
            {
                "sender": _sender(neighbour.feed.sender),
                "message_type": neighbour.feed.message_type,
                "nearest_sender": _sender(neighbour.other.sender),
                "score": round(neighbour.score, 3),
                "only_here": _positions(neighbour.only_here),
                "only_there": _positions(neighbour.only_there),
            }
        )

    z_segments = []
    for use in report.z_segments:
        z_segments.append(
            {
                "sender": _sender(use.sender),
                "segment": use.segment,
                "message_types": list(use.message_types),
                "messages": use.messages,
            }
        )

    return {
        "format_version": FORMAT_VERSION,
        "folder": report.folder,
        "files": report.file_count,
        "messages": report.message_count,
        "feeds": feeds,
        "outliers": outliers,
        "habits": habits,
        "neighbours": neighbours,
        "z_segments": z_segments,
    }


def _feed(feed: Feed, flagged: set[str]) -> dict:
    shapes = []
    for shape in feed.shapes:
        shapes.append(_shape(shape, flagged))
    return {
        "sender": _sender(feed.sender),
        "message_type": feed.message_type,
        "messages": feed.message_count,
        "versions": feed.versions(),
        "shapes": shapes,
    }


def _shape(shape: Shape, flagged: set[str]) -> dict:
    sometimes = []
    for usage in shape.sometimes_filled():
        sometimes.append(
            {"position": str(usage.position), "filled": usage.filled, "of": usage.total}
        )
    return {
        "version": shape.version,
        "segments": list(shape.segments),
        "messages": shape.message_count,
        "example": str(example_message(shape, flagged)),
        "sometimes_filled": sometimes,
    }


def example_message(shape: Shape, flagged: set[str]) -> MessageRef:
    """The first message of the shape that is not an odd one out, else the first.

    A message counts as flagged when it is, or when its whole file is (an
    unbalanced MLLP frame is reported on the file, not on the message).
    """
    for cluster in shape.clusters:
        for ref in cluster.members:
            if str(ref) not in flagged and ref.file not in flagged:
                return ref
    return shape.clusters[0].members[0]


def _sender(sender: Sender) -> dict:
    return {"application": sender.application, "facility": sender.facility}


def _positions(positions: tuple[Position, ...]) -> list[str]:
    names = []
    for position in positions:
        names.append(str(position))
    return names
