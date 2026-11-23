"""The delimiters ("encoding characters") a message declares in MSH-1 and MSH-2.

HL7 v2 does not fix the delimiters: every message says which ones it uses.
The 4th character of the MSH line is the field separator (MSH-1), and the
characters up to the next field separator are MSH-2:

    MSH|^~\\&|SENDER|...
       ^ ^^^^
       | MSH-2: component ^, repetition ~, escape \\, subcomponent &
       MSH-1: field separator |

v2.7 added an optional 5th MSH-2 character, the truncation character (#).
FHS and BHS (batch headers) declare delimiters the same way.
"""

from dataclasses import dataclass

from raphael7.parser.issues import ParseIssue, Severity

# Segments whose field 1 is the field separator and field 2 the encoding characters.
HEADER_SEGMENTS = frozenset({"MSH", "FHS", "BHS"})


@dataclass(frozen=True, slots=True)
class Encoding:
    """The delimiters one message uses.

    A delimiter MSH-2 does not declare is ``None``, and the parser then does
    not split on it.
    """

    field: str = "|"
    component: str = "^"
    repetition: str | None = "~"
    escape: str | None = "\\"
    subcomponent: str | None = "&"
    truncation: str | None = None

    @property
    def msh2(self) -> str:
        """MSH-2 as it would be written for this encoding, e.g. ``^~\\&``."""
        text = self.component
        for char in (self.repetition, self.escape, self.subcomponent, self.truncation):
            if char is None:
                break
            text += char
        return text

    @property
    def delimiters(self) -> tuple[str, ...]:
        """Every declared delimiter, including the escape and truncation characters."""
        all_chars = (
            self.field,
            self.component,
            self.repetition,
            self.escape,
            self.subcomponent,
            self.truncation,
        )
        return tuple(char for char in all_chars if char is not None)


DEFAULT_ENCODING = Encoding()


@dataclass(frozen=True, slots=True)
class HeaderEncoding:
    """What :func:`read_header_encoding` found in a header segment."""

    encoding: Encoding
    issues: list[ParseIssue]


def read_header_encoding(line: str) -> HeaderEncoding:
    """Read the delimiters from a header segment line (MSH, FHS or BHS).

    If the header is unusable, the result uses as much of it as is valid and
    falls back to the defaults for the rest, with an error-level issue, so
    tolerant parsing can go on.
    """
    seg_id = line[:3]

    if len(line) < 4:
        return _unusable(DEFAULT_ENCODING, f"{seg_id} has no field separator")

    field_sep = line[3]
    if field_sep.isalnum() or field_sep.isspace():
        return _unusable(DEFAULT_ENCODING, f"invalid field separator {field_sep!r} in {seg_id}-1")

    end = line.find(field_sep, 4)
    msh2 = line[4:] if end == -1 else line[4:end]
    fallback = Encoding(field=field_sep)

    if msh2 == "":
        return _unusable(fallback, f"{seg_id}-2 (encoding characters) is empty")
    if len(msh2) > 5:
        return _unusable(fallback, f"{seg_id}-2 has {len(msh2)} characters (at most 5 expected)")
    if any(char.isalnum() or char.isspace() for char in msh2):
        return _unusable(fallback, f"invalid encoding characters {msh2!r} in {seg_id}-2")
    all_delimiters = field_sep + msh2
    if len(set(all_delimiters)) != len(all_delimiters):
        return _unusable(fallback, f"{seg_id}-1/{seg_id}-2 repeat a delimiter: {all_delimiters!r}")

    encoding = Encoding(
        field=field_sep,
        component=msh2[0],
        repetition=_char_at(msh2, 1),
        escape=_char_at(msh2, 2),
        subcomponent=_char_at(msh2, 3),
        truncation=_char_at(msh2, 4),
    )

    issues = []
    if len(msh2) < 4:
        issues.append(
            ParseIssue(
                "short-encoding",
                f"{seg_id}-2 declares only {len(msh2)} encoding characters ({msh2!r})",
                Severity.WARNING,
                location=f"{seg_id}-2",
            )
        )
    return HeaderEncoding(encoding, issues)


def _char_at(text: str, index: int) -> str | None:
    """The character at ``index``, or None when MSH-2 is shorter than that."""
    return text[index] if index < len(text) else None


def _unusable(fallback: Encoding, message: str) -> HeaderEncoding:
    issue = ParseIssue("bad-encoding", message, Severity.ERROR, location="MSH-2")
    return HeaderEncoding(fallback, [issue])
