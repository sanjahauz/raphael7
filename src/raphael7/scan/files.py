"""Read every file in a folder and parse it, one file at a time.

Scan works on messages, not files: a batch file (FHS/BHS ... BTS/FTS) holds
many messages, and an empty or broken file holds none. A file with no
message is still yielded, with its issues, so that scan can report it
instead of losing it.

Files are read in sorted path order so that two runs give the same report.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from raphael7.parser import Message, ParseIssue, parse_file


@dataclass(frozen=True, slots=True)
class MessageRef:
    """Where a message came from: its file and its position in that file."""

    file: str  # path relative to the scanned folder, with / separators
    index: int  # 1-based: the n-th message in the file

    def __str__(self) -> str:
        return f"{self.file}#{self.index}"


@dataclass(frozen=True, slots=True)
class ScannedFile:
    """One parsed file: its messages and the issues not tied to one message."""

    path: str  # relative to the scanned folder, with / separators
    messages: tuple[Message, ...]
    issues: tuple[ParseIssue, ...]  # e.g. empty, no-msh, mllp, batch-count

    def refs(self) -> list[MessageRef]:
        """A reference for each message, in file order."""
        refs = []
        for index in range(1, len(self.messages) + 1):
            refs.append(MessageRef(self.path, index))
        return refs


def message_files(folder: Path) -> list[Path]:
    """Every file under ``folder``, sorted; hidden files and folders are skipped.

    No extension filter: real feeds arrive as .hl7, .txt, .dat or with no
    extension at all. A file that is not HL7 shows up as ``no-msh``.
    Hidden ones (.DS_Store, .git) are never messages.
    """
    files = []
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder)
        if _is_hidden(relative):
            continue
        if path.is_file():
            files.append(path)
    return files


def scan_files(folder: Path) -> Iterator[ScannedFile]:
    """Parse each file in tolerant mode, yielding one result per file."""
    for path in message_files(folder):
        result = parse_file(path)
        yield ScannedFile(
            path=path.relative_to(folder).as_posix(),
            messages=tuple(result.messages),
            issues=tuple(result.issues),
        )


def _is_hidden(relative: Path) -> bool:
    return any(part.startswith(".") for part in relative.parts)
