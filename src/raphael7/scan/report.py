"""Run a whole scan: read the folder once, then apply every step to the result.

The steps, in order: parse each file (``files``), group messages by exact
signature (``cluster``), group clusters into feeds and shapes (``shapes``),
then find odd ones out, neighbours and Z-segments on top of the feeds.
"""

from dataclasses import dataclass
from pathlib import Path

from raphael7.scan.cluster import cluster_by_signature
from raphael7.scan.files import scan_files
from raphael7.scan.neighbours import Neighbour, nearest_neighbours
from raphael7.scan.outliers import FeedHabit, Outlier, find_outliers
from raphael7.scan.shapes import Feed, group_into_feeds
from raphael7.scan.zsegments import ZSegmentUse, z_segments


@dataclass(slots=True)
class ScanReport:
    folder: str
    file_count: int
    message_count: int
    feeds: list[Feed]  # biggest first
    outliers: list[Outlier]  # in folder order
    habits: list[FeedHabit]
    neighbours: list[Neighbour]
    z_segments: list[ZSegmentUse]


def scan_folder(folder: Path) -> ScanReport:
    grouping = cluster_by_signature(scan_files(folder))
    feeds = group_into_feeds(grouping.clusters)
    found = find_outliers(grouping, feeds)

    message_count = 0
    for feed in feeds:
        message_count += feed.message_count

    return ScanReport(
        folder=str(folder),
        file_count=grouping.file_count,
        message_count=message_count,
        feeds=feeds,
        outliers=found.outliers,
        habits=found.habits,
        neighbours=nearest_neighbours(feeds),
        z_segments=z_segments(feeds),
    )
