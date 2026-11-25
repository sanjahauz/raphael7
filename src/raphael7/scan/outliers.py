"""Find the odd ones out: what an integrator should open first.

A message or file is an outlier for one or more reasons, each with a stable
code:

- ``no-message``: the file held no message at all (empty, not HL7, no MSH).
- ``file-issue``: the file parsed, but with a problem around the messages
  (MLLP framing, BTS count, charset).
- ``parse-issue``: the message has a parse issue that is rare in its feed.
  An issue found in at least half of a feed (vendor B's ``\\n`` line
  endings) is a habit of that feed, reported once as a :class:`FeedHabit`,
  not as 60 outliers.
- ``other-version``: MSH-12 is not the version most of its feed uses, the
  sign of a vendor upgrade or a second system sending under the same name.
- ``rare-segments``: the message's segment order is used by few messages of
  its feed, e.g. a ``Pid`` segment or an unexpected NTE.
- ``missing-fields``: the message leaves empty several fields that every
  other message of its shape fills, as a message cut off mid-way does.
  A single missing field is not enough: a normal result leaves OBX-8 empty
  where an abnormal one has ``H`` or ``L`` (decided 25 Nov).
"""

from dataclasses import dataclass, field

from raphael7.parser import ParseIssue
from raphael7.scan.cluster import Cluster, Grouping
from raphael7.scan.files import MessageRef
from raphael7.scan.shapes import Feed, Shape
from raphael7.scan.signature import Position

# A segment order is rare when at most this share of its feed's messages use it.
RARE_SEGMENTS_SHARE = 0.2
# An issue in at least this share of a feed's messages is a habit of the feed.
HABIT_SHARE = 0.5
# missing-fields needs this many fields that all other messages fill...
MIN_MISSING_FIELDS = 2
# ...and at least this many other messages in the shape to compare with.
MIN_OTHER_MESSAGES = 3


@dataclass(frozen=True, slots=True)
class Reason:
    code: str  # no-message, file-issue, parse-issue, other-version, rare-segments, missing-fields
    text: str  # for people, e.g. "OBX-5, OBX-6 empty; filled in all 24 others"


@dataclass(slots=True)
class Outlier:
    where: str  # "file#n" for a message, or a file path
    reasons: list[Reason] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FeedHabit:
    """A parse issue found in most messages of one feed."""

    feed: Feed
    code: str
    count: int


@dataclass(slots=True)
class OutlierReport:
    outliers: list[Outlier]  # in folder order
    habits: list[FeedHabit]


def find_outliers(grouping: Grouping, feeds: list[Feed]) -> OutlierReport:
    """Apply every rule and gather the reasons per message or file."""
    found: dict[str, Outlier] = {}
    habits = []

    for scanned in grouping.files_without_messages:
        _add(found, scanned.path, Reason("no-message", _codes_text(scanned.issues)))

    for path, issues in grouping.file_issues.items():
        _add(found, path, Reason("file-issue", _codes_text(issues)))

    for feed in feeds:
        habits.extend(_parse_issue_outliers(feed, grouping, found))
        _other_version_outliers(feed, found)
        _rare_segments_outliers(feed, found)
        for shape in feed.shapes:
            _missing_field_outliers(shape, found)

    outliers = sorted(found.values(), key=_folder_order)
    return OutlierReport(outliers, habits)


def _parse_issue_outliers(
    feed: Feed, grouping: Grouping, found: dict[str, Outlier]
) -> list[FeedHabit]:
    """Flag messages with rare parse issues; return the feed's habits."""
    issues_by_ref: dict[MessageRef, tuple[ParseIssue, ...]] = {}
    count_by_code: dict[str, int] = {}
    for ref in _feed_members(feed):
        issues = grouping.message_issues.get(ref, ())
        if not issues:
            continue
        issues_by_ref[ref] = issues
        for code in _unique_codes(issues):
            count_by_code[code] = count_by_code.get(code, 0) + 1

    habit_codes = set()
    habits = []
    for code, count in count_by_code.items():
        if count >= HABIT_SHARE * feed.message_count:
            habit_codes.add(code)
            habits.append(FeedHabit(feed, code, count))

    for ref, issues in issues_by_ref.items():
        rare_codes = []
        for code in _unique_codes(issues):
            if code not in habit_codes:
                rare_codes.append(code)
        if rare_codes:
            _add(found, str(ref), Reason("parse-issue", ", ".join(rare_codes)))
    return habits


def _other_version_outliers(feed: Feed, found: dict[str, Outlier]) -> None:
    versions = feed.versions()
    main = versions[0]
    for version in versions[1:]:
        shapes = []
        for shape in feed.shapes:
            if shape.version == version:
                shapes.append(shape)
        count = _message_count(shapes)
        text = f"version {version} in {count} of {feed.message_count}; feed mostly {main}"
        _add_members(found, shapes, Reason("other-version", text))


def _rare_segments_outliers(feed: Feed, found: dict[str, Outlier]) -> None:
    """Flag segment orders few messages use, across all versions of the feed.

    Versions are left out here so that vendor B's BMP results (with NTE),
    common on 2.3.1, are not called rare on 2.5 too; ``other-version``
    already covers the version.
    """
    shapes_by_order: dict[tuple[str, ...], list[Shape]] = {}
    for shape in feed.shapes:
        shapes_by_order.setdefault(shape.segments, []).append(shape)
    if len(shapes_by_order) == 1:
        return

    main_order = _most_used_order(shapes_by_order)
    for order, shapes in shapes_by_order.items():
        count = _message_count(shapes)
        if count > RARE_SEGMENTS_SHARE * feed.message_count:
            continue
        text = (
            f"segments {' '.join(order)} in {count} of {feed.message_count}; "
            f"feed mostly {' '.join(main_order)}"
        )
        _add_members(found, shapes, Reason("rare-segments", text))


def _missing_field_outliers(shape: Shape, found: dict[str, Outlier]) -> None:
    """Flag a cluster that leaves empty fields every other message of the shape fills."""
    total = shape.message_count
    for cluster in shape.clusters:
        others = total - len(cluster.members)
        if others < MIN_OTHER_MESSAGES:
            continue
        missing = _filled_by_all_others(shape, cluster, others)
        if len(missing) < MIN_MISSING_FIELDS:
            continue
        names = []
        for position in missing:
            names.append(str(position))
        text = f"{', '.join(names)} empty; filled in all {others} others"
        for ref in cluster.members:
            _add(found, str(ref), Reason("missing-fields", text))


def _filled_by_all_others(shape: Shape, cluster: Cluster, others: int) -> list[Position]:
    own = set(cluster.signature.populated)
    missing = []
    for usage in shape.field_usage():
        if usage.position not in own and usage.filled == others:
            missing.append(usage.position)
    return missing


def _most_used_order(shapes_by_order: dict[tuple[str, ...], list[Shape]]) -> tuple[str, ...]:
    """The segment order with the most messages; a tie goes to the one seen first."""
    best_order: tuple[str, ...] = ()
    best_count = -1
    for order, shapes in shapes_by_order.items():
        count = _message_count(shapes)
        if count > best_count:
            best_order = order
            best_count = count
    return best_order


def _message_count(shapes: list[Shape]) -> int:
    count = 0
    for shape in shapes:
        count += shape.message_count
    return count


def _add_members(found: dict[str, Outlier], shapes: list[Shape], reason: Reason) -> None:
    for shape in shapes:
        for cluster in shape.clusters:
            for ref in cluster.members:
                _add(found, str(ref), reason)


def _feed_members(feed: Feed) -> list[MessageRef]:
    refs = []
    for shape in feed.shapes:
        for cluster in shape.clusters:
            refs.extend(cluster.members)
    return refs


def _unique_codes(issues: tuple[ParseIssue, ...]) -> list[str]:
    codes = []
    for issue in issues:
        if issue.code not in codes:
            codes.append(issue.code)
    return codes


def _codes_text(issues: tuple[ParseIssue, ...]) -> str:
    return ", ".join(_unique_codes(issues))


def _add(found: dict[str, Outlier], where: str, reason: Reason) -> None:
    if where not in found:
        found[where] = Outlier(where)
    found[where].reasons.append(reason)


def _folder_order(outlier: Outlier) -> tuple[str, int]:
    """Sort by file, then by message number (so file#10 comes after file#2)."""
    path, _, index = outlier.where.partition("#")
    return (path, int(index) if index else 0)
