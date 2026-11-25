"""Group messages whose signatures are exactly the same.

Each group (cluster) is one shape the sender uses, e.g. "vendor A's
ADT^A01 on 2.5 with these segments and fields". Near neighbours (shapes
that are almost the same) come later, on top of these clusters.

Only signatures and references are kept, not the messages, so memory grows
with the number of shapes and messages referenced, not with message size.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from raphael7.parser import ParseIssue
from raphael7.scan.files import MessageRef, ScannedFile
from raphael7.scan.signature import Signature, signature


@dataclass(slots=True)
class Cluster:
    signature: Signature
    members: list[MessageRef] = field(default_factory=list)  # in folder order


@dataclass(slots=True)
class Grouping:
    """The exact clusters of a folder, plus the files that held no message."""

    clusters: list[Cluster]  # biggest first; a tie goes to the one seen first
    files_without_messages: list[ScannedFile]  # kept with their issues, never dropped
    # Issues are kept only where there are some, so memory stays small on a clean feed.
    message_issues: dict[MessageRef, tuple[ParseIssue, ...]] = field(default_factory=dict)
    # Issues of files that did hold messages, e.g. mllp, batch-count, decode.
    file_issues: dict[str, tuple[ParseIssue, ...]] = field(default_factory=dict)
    file_count: int = 0  # every file read, with or without messages


def cluster_by_signature(files: Iterable[ScannedFile]) -> Grouping:
    """Put each message in the cluster of its signature."""
    by_signature: dict[Signature, Cluster] = {}
    files_without_messages = []
    message_issues = {}
    file_issues = {}
    file_count = 0

    for scanned in files:
        file_count += 1
        if not scanned.messages:
            files_without_messages.append(scanned)
            continue
        if scanned.issues:
            file_issues[scanned.path] = scanned.issues
        for ref, message in zip(scanned.refs(), scanned.messages, strict=True):
            if message.issues:
                message_issues[ref] = message.issues
            sig = signature(message)
            if sig not in by_signature:
                by_signature[sig] = Cluster(sig)
            by_signature[sig].members.append(ref)

    # dict keeps insertion order, so a stable sort on size alone leaves ties
    # in the order they were first seen: the same folder gives the same report.
    clusters = sorted(by_signature.values(), key=_size, reverse=True)
    return Grouping(clusters, files_without_messages, message_issues, file_issues, file_count)


def _size(cluster: Cluster) -> int:
    return len(cluster.members)
