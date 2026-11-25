"""Group exact clusters into feeds and shapes.

- A **feed** is what one sender sends for one message type: vendor B's
  ORU^R01, say. Senders are never mixed (MSH-3 + MSH-4, decided 25 Nov).
- A **shape** is one way that feed is built: one MSH-12 version and one
  segment order. Vendor B's CBC results (no NTE) and BMP results (with NTE)
  are two shapes of one feed.
- Inside a shape, fields are counted, not compared: "OBX-8 filled in 8 of
  10" is one shape, because whether a result is abnormal depends on the
  patient, not on how the vendor built the feed (decided 25 Nov).

Exact clusters are kept inside each shape, so nothing found earlier is lost.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from raphael7.scan.cluster import Cluster
from raphael7.scan.signature import Position, Sender


@dataclass(frozen=True, slots=True)
class FieldUsage:
    """How many messages of a shape fill one position."""

    position: Position
    filled: int
    total: int

    @property
    def always(self) -> bool:
        return self.filled == self.total


@dataclass(slots=True)
class Shape:
    sender: Sender
    message_type: str | None
    version: str | None
    segments: tuple[str, ...]
    clusters: list[Cluster] = field(default_factory=list)  # biggest first

    @property
    def message_count(self) -> int:
        count = 0
        for cluster in self.clusters:
            count += len(cluster.members)
        return count

    def field_usage(self) -> list[FieldUsage]:
        """Each position filled in at least one message, sorted like a signature."""
        filled: dict[Position, int] = {}
        for cluster in self.clusters:
            for position in cluster.signature.populated:
                filled[position] = filled.get(position, 0) + len(cluster.members)
        total = self.message_count
        usage = []
        for position in sorted(filled, key=_position_key):
            usage.append(FieldUsage(position, filled[position], total))
        return usage

    def sometimes_filled(self) -> list[FieldUsage]:
        """Positions filled in some messages of this shape but not all (e.g. OBX-8)."""
        found = []
        for usage in self.field_usage():
            if not usage.always:
                found.append(usage)
        return found


@dataclass(slots=True)
class Feed:
    sender: Sender
    message_type: str | None
    shapes: list[Shape] = field(default_factory=list)  # biggest first

    @property
    def message_count(self) -> int:
        count = 0
        for shape in self.shapes:
            count += shape.message_count
        return count

    def versions(self) -> list[str | None]:
        """MSH-12 values in this feed, most used first. More than one is drift."""
        counts: dict[str | None, int] = {}
        for shape in self.shapes:
            counts[shape.version] = counts.get(shape.version, 0) + shape.message_count
        return sorted(counts, key=counts.__getitem__, reverse=True)


def group_into_feeds(clusters: Iterable[Cluster]) -> list[Feed]:
    """Put each exact cluster in its shape, and each shape in its feed.

    Biggest first at every level; a tie keeps the order first seen, so the
    same folder always gives the same report.
    """
    shapes: dict[tuple, Shape] = {}
    for cluster in clusters:
        sig = cluster.signature
        key = (sig.sender, sig.message_type, sig.version, sig.segments)
        if key not in shapes:
            shapes[key] = Shape(sig.sender, sig.message_type, sig.version, sig.segments)
        shapes[key].clusters.append(cluster)

    feeds: dict[tuple, Feed] = {}
    for shape in shapes.values():
        shape.clusters.sort(key=_cluster_size, reverse=True)
        key = (shape.sender, shape.message_type)
        if key not in feeds:
            feeds[key] = Feed(shape.sender, shape.message_type)
        feeds[key].shapes.append(shape)

    for feed in feeds.values():
        feed.shapes.sort(key=_shape_size, reverse=True)
    return sorted(feeds.values(), key=_feed_size, reverse=True)


def _cluster_size(cluster: Cluster) -> int:
    return len(cluster.members)


def _shape_size(shape: Shape) -> int:
    return shape.message_count


def _feed_size(feed: Feed) -> int:
    return feed.message_count


def _position_key(position: Position) -> tuple[str, int]:
    return (position.segment, position.field)
