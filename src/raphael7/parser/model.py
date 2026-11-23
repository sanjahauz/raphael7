"""Parsed message model.

Values are kept raw (still escaped) in plain nested tuples, so parsing is
cheap and serializing gives back the original text:

    Field       = tuple[Repetition, ...]   (at least one)
    Repetition  = tuple[Component, ...]    (at least one)
    Component   = tuple[str, ...]          (subcomponents, at least one)

Fields are numbered from 1 as in the spec. For header segments (MSH, FHS,
BHS) field 1 is the field separator and field 2 the encoding characters.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum

from raphael7.parser.encoding import DEFAULT_ENCODING, Encoding
from raphael7.parser.escape import unescape

type Component = tuple[str, ...]
type Repetition = tuple[Component, ...]
type Field = tuple[Repetition, ...]


class Severity(StrEnum):
    ERROR = "error"  # malformed structure: strict mode raises
    WARNING = "warning"  # off-spec but parsed unambiguously: recorded in both modes


@dataclass(frozen=True, slots=True)
class ParseIssue:
    code: str
    message: str
    severity: Severity = Severity.WARNING
    line: int | None = None  # 1-based segment line in the input
    location: str | None = None  # e.g. "PID-5[1].1.1"

    def __str__(self) -> str:
        where = " ".join(
            p
            for p in (
                f"line {self.line}" if self.line else "",
                self.location or "",
            )
            if p
        )
        return f"{self.severity}: {self.code}: {self.message}" + (f" ({where})" if where else "")


class ParseError(ValueError):
    """Raised in strict mode on the first error-level issue."""

    def __init__(self, issue: ParseIssue):
        super().__init__(str(issue))
        self.issue = issue


@dataclass(frozen=True, slots=True)
class Segment:
    id: str
    fields: tuple[Field, ...] = ()

    def field(self, n: int) -> Field | None:
        """Field ``n`` (1-based), or None if the segment is shorter."""
        if n < 1 or n > len(self.fields):
            return None
        return self.fields[n - 1]


_PATH = re.compile(
    r"^(?P<seg>[A-Z][A-Z0-9]{2})(?:\((?P<occ>\d+)\))?"
    r"-(?P<field>\d+)(?:\[(?P<rep>\d+)\])?"
    r"(?:\.(?P<comp>\d+)(?:\.(?P<sub>\d+))?)?$"
)


@dataclass(frozen=True, slots=True)
class Message:
    segments: tuple[Segment, ...]
    encoding: Encoding = DEFAULT_ENCODING
    issues: tuple[ParseIssue, ...] = field(default=(), compare=False)

    # --- lookup -----------------------------------------------------------

    def segment(self, seg_id: str, occurrence: int = 1) -> Segment | None:
        """The ``occurrence``-th segment with this ID (1-based), or None."""
        seen = 0
        for seg in self.segments:
            if seg.id == seg_id:
                seen += 1
                if seen == occurrence:
                    return seg
        return None

    def get(self, path: str) -> str | None:
        """Raw value at a path such as ``PID-5``, ``PID-3[2].1`` or ``OBX(2)-5.1.2``.

        Without ``[n]`` the first repetition is used. Returns None when the
        position does not exist, ``""`` when it exists but is empty.
        """
        m = _PATH.match(path)
        if not m:
            raise ValueError(f"invalid path {path!r}")
        seg = self.segment(m["seg"], int(m["occ"] or 1))
        if seg is None:
            return None
        fld = seg.field(int(m["field"]))
        if fld is None:
            return None
        rep_i = int(m["rep"] or 1)
        if rep_i < 1 or rep_i > len(fld):
            return None
        rep = fld[rep_i - 1]
        enc = self.encoding
        if m["comp"] is None:
            return _join_repetition(rep, enc)
        comp_i = int(m["comp"])
        if comp_i < 1 or comp_i > len(rep):
            return None
        comp = rep[comp_i - 1]
        if m["sub"] is None:
            return _join_component(comp, enc)
        sub_i = int(m["sub"])
        if sub_i < 1 or sub_i > len(comp):
            return None
        return comp[sub_i - 1]

    def value(self, path: str) -> str | None:
        """Like :meth:`get`, with escape sequences decoded."""
        raw = self.get(path)
        return None if raw is None else unescape(raw, self.encoding)

    # --- common header fields ----------------------------------------------

    @property
    def message_type(self) -> str | None:
        """MSH-9 type and trigger, e.g. ``ADT^A01`` (None if MSH-9 is empty)."""
        code, trigger = self.get("MSH-9.1"), self.get("MSH-9.2")
        if not code:
            return None
        return f"{code}^{trigger}" if trigger else code

    @property
    def version(self) -> str | None:
        """MSH-12.1, e.g. ``2.5.1``."""
        return self.get("MSH-12.1") or None

    @property
    def control_id(self) -> str | None:
        """MSH-10."""
        return self.get("MSH-10") or None


def _join_component(comp: Component, enc: Encoding) -> str:
    return comp[0] if len(comp) == 1 else (enc.subcomponent or "").join(comp)


def _join_repetition(rep: Repetition, enc: Encoding) -> str:
    return enc.component.join(_join_component(c, enc) for c in rep)


def join_field(fld: Field, enc: Encoding) -> str:
    """Serialize one field back to raw text."""
    return (enc.repetition or "").join(_join_repetition(r, enc) for r in fld)
