"""The parsed message: what the parser produces.

A field is split three levels deep, and every level is a plain tuple:

    field         PID-3   "123^^^HOSP^MR~987^^^MOH^NI"
    repetitions           ("123^^^HOSP^MR", "987^^^MOH^NI")     split on ~
    components            ("123", "", "", "HOSP", "MR")          split on ^
    subcomponents         ("HOSP",) or ("HOSP", "1.2.3", "ISO")  split on &

So a ``Field`` is a tuple of repetitions, a repetition a tuple of components,
and a component a tuple of subcomponent strings. Each level has at least one
item, even when the value is empty.

Values are kept raw (still escaped); use :meth:`Message.value` for the
decoded text. Fields are numbered from 1 as in the spec. In MSH (and FHS,
BHS) field 1 is the field separator itself and field 2 the encoding
characters, so MSH-3 is the sending application, just as in the spec.
"""

import re
from dataclasses import dataclass, field

from raphael7.parser.encoding import DEFAULT_ENCODING, Encoding
from raphael7.parser.escape import unescape
from raphael7.parser.issues import ParseIssue

type Component = tuple[str, ...]
type Repetition = tuple[Component, ...]
type Field = tuple[Repetition, ...]


@dataclass(frozen=True, slots=True)
class Segment:
    id: str
    fields: tuple[Field, ...] = ()

    def field(self, n: int) -> Field | None:
        """Field ``n`` (1-based), or None if the segment is shorter."""
        return _nth(self.fields, n)


@dataclass(frozen=True, slots=True)
class Message:
    segments: tuple[Segment, ...]
    encoding: Encoding = DEFAULT_ENCODING
    # Issues do not count when comparing messages: same content means equal.
    issues: tuple[ParseIssue, ...] = field(default=(), compare=False)

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

        Path parts: segment, ``(n)`` which occurrence of the segment,
        ``-n`` field, ``[n]`` repetition, ``.n`` component, ``.n`` subcomponent.
        Without ``[n]`` the first repetition is used, as is usual in HL7 tools.

        Returns None when the position does not exist, and ``""`` when it
        exists but is empty.
        """
        p = _parse_path(path)
        seg = self.segment(p.segment, p.occurrence)
        if seg is None:
            return None
        fld = seg.field(p.field)
        if fld is None:
            return None
        repetition = _nth(fld, p.repetition)
        if repetition is None:
            return None
        if p.component is None:
            return join_repetition(repetition, self.encoding)
        component = _nth(repetition, p.component)
        if component is None:
            return None
        if p.subcomponent is None:
            return join_component(component, self.encoding)
        return _nth(component, p.subcomponent)

    def value(self, path: str) -> str | None:
        """Like :meth:`get`, with escape sequences decoded."""
        raw = self.get(path)
        if raw is None:
            return None
        return unescape(raw, self.encoding)

    @property
    def message_type(self) -> str | None:
        """MSH-9 type and trigger event, e.g. ``ADT^A01`` (None if MSH-9 is empty)."""
        code = self.get("MSH-9.1")
        trigger = self.get("MSH-9.2")
        if not code:
            return None
        if trigger:
            return f"{code}^{trigger}"
        return code

    @property
    def version(self) -> str | None:
        """MSH-12, the HL7 version, e.g. ``2.5.1``."""
        return self.get("MSH-12.1") or None

    @property
    def control_id(self) -> str | None:
        """MSH-10, the sender's unique ID for this message."""
        return self.get("MSH-10") or None


# --- joining split values back into raw text --------------------------------


def join_component(component: Component, enc: Encoding) -> str:
    return (enc.subcomponent or "").join(component)


def join_repetition(repetition: Repetition, enc: Encoding) -> str:
    return enc.component.join(join_component(c, enc) for c in repetition)


def join_field(fld: Field, enc: Encoding) -> str:
    return (enc.repetition or "").join(join_repetition(r, enc) for r in fld)


# --- paths --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Path:
    segment: str
    occurrence: int
    field: int
    repetition: int
    component: int | None
    subcomponent: int | None


_PATH = re.compile(
    r"^(?P<segment>[A-Z][A-Z0-9]{2})"
    r"(?:\((?P<occurrence>\d+)\))?"
    r"-(?P<field>\d+)"
    r"(?:\[(?P<repetition>\d+)\])?"
    r"(?:\.(?P<component>\d+)(?:\.(?P<subcomponent>\d+))?)?$"
)


def _parse_path(path: str) -> _Path:
    m = _PATH.match(path)
    if not m:
        raise ValueError(f"invalid path {path!r}")
    return _Path(
        segment=m["segment"],
        occurrence=int(m["occurrence"] or 1),
        field=int(m["field"]),
        repetition=int(m["repetition"] or 1),
        component=int(m["component"]) if m["component"] else None,
        subcomponent=int(m["subcomponent"]) if m["subcomponent"] else None,
    )


def _nth[T](items: tuple[T, ...], n: int) -> T | None:
    """Item ``n`` counting from 1, or None if there is no such item."""
    if 1 <= n <= len(items):
        return items[n - 1]
    return None
