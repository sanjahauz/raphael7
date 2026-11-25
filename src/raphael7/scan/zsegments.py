"""Which Z-segments each sender uses.

Z-segments are a site's own additions (any segment ID starting with Z): the
spec says nothing about their content, so every one is mapping work for an
integrator. Vendor B, for example, sends the HMO (kupat holim) in ZPI
instead of IN1.
"""

from dataclasses import dataclass

from raphael7.scan.shapes import Feed
from raphael7.scan.signature import Sender


@dataclass(frozen=True, slots=True)
class ZSegmentUse:
    sender: Sender
    segment: str  # e.g. ZPI
    message_types: tuple[str, ...]  # sorted, e.g. ("ADT^A01", "ADT^A08")
    messages: int  # how many of the sender's messages contain it


def z_segments(feeds: list[Feed]) -> list[ZSegmentUse]:
    """Every Z-segment per sender, sorted by sender, then segment ID."""
    types: dict[tuple[Sender, str], set[str]] = {}
    counts: dict[tuple[Sender, str], int] = {}
    for feed in feeds:
        for shape in feed.shapes:
            for segment in _z_ids(shape.segments):
                key = (feed.sender, segment)
                counts[key] = counts.get(key, 0) + shape.message_count
                types.setdefault(key, set()).add(feed.message_type or "?")

    uses = []
    for key in sorted(counts, key=_sort_key):
        sender, segment = key
        uses.append(ZSegmentUse(sender, segment, tuple(sorted(types[key])), counts[key]))
    return uses


def _z_ids(segments: tuple[str, ...]) -> list[str]:
    """Z-segment IDs in a segment order, each once (ZPI ZPI after a collapse is one)."""
    found = []
    for segment in segments:
        if segment.startswith("Z") and segment not in found:
            found.append(segment)
    return found


def _sort_key(key: tuple[Sender, str]) -> tuple[str, str, str]:
    sender, segment = key
    return (sender.application, sender.facility, segment)
