"""Near neighbours: the same message type from another sender.

Shows how close vendor A's ORM is to vendor C's, say, so an integrator who
already maps one feed sees how much of that work carries over. Within one
sender, shapes and field counts say more than a score (decided 25 Nov), so
neighbours are only looked for across senders.

Closeness is the Jaccard index of the populated positions of the two feeds'
main shapes: shared positions divided by all positions either one fills.
1.0 means the same fields are filled; 0.5 means half of them are shared.
"""

from dataclasses import dataclass

from raphael7.scan.shapes import Feed
from raphael7.scan.signature import Position


@dataclass(frozen=True, slots=True)
class Neighbour:
    feed: Feed
    other: Feed  # same message type, another sender
    score: float  # Jaccard index, 0.0 to 1.0
    only_here: tuple[Position, ...]  # filled by feed's main shape, not by other's
    only_there: tuple[Position, ...]  # filled by other's main shape, not by feed's


def nearest_neighbours(feeds: list[Feed]) -> list[Neighbour]:
    """For each feed, the closest feed of the same message type from another sender."""
    neighbours = []
    for feed in feeds:
        best = None
        for other in feeds:
            if other is feed or other.message_type != feed.message_type:
                continue
            candidate = compare(feed, other)
            if best is None or candidate.score > best.score:
                best = candidate
        if best is not None:
            neighbours.append(best)
    return neighbours


def compare(feed: Feed, other: Feed) -> Neighbour:
    here = main_positions(feed)
    there = main_positions(other)
    shared = here & there
    either = here | there
    score = len(shared) / len(either) if either else 1.0
    return Neighbour(
        feed=feed,
        other=other,
        score=score,
        only_here=_sorted(here - there),
        only_there=_sorted(there - here),
    )


def main_positions(feed: Feed) -> set[Position]:
    """Positions filled in at least one message of the feed's main (biggest) shape."""
    positions = set()
    for usage in feed.shapes[0].field_usage():
        positions.add(usage.position)
    return positions


def _sorted(positions: set[Position]) -> tuple[Position, ...]:
    ordered = []
    for position in positions:
        ordered.append(position)
    ordered.sort(key=_position_key)
    return tuple(ordered)


def _position_key(position: Position) -> tuple[str, int]:
    return (position.segment, position.field)
