"""Tokenize HL7 v2 text into :class:`~raphael7.parser.model.Message` objects.

Input can be one message, many messages back to back, a batch file
(FHS/BHS ... BTS/FTS) or MLLP-framed data. Segments may end with ``\\r``,
``\\n`` or ``\\r\\n``.

Two modes:

* **tolerant** (default): every problem is recorded as a :class:`ParseIssue`
  and parsing continues as best it can. This is what corpus scanning uses.
* **strict**: the first error-level issue raises :class:`ParseError`.
  Warnings (non-standard terminators, unknown escapes, ...) never raise.
"""

import codecs
import re
from dataclasses import dataclass, field
from pathlib import Path

from raphael7.parser.encoding import DEFAULT_ENCODING, HEADER_SEGMENTS, read_header_encoding
from raphael7.parser.escape import escape_problems
from raphael7.parser.model import (
    Field,
    Message,
    ParseError,
    ParseIssue,
    Segment,
    Severity,
)

ENVELOPE_SEGMENTS = frozenset({"FHS", "BHS", "BTS", "FTS"})
_SEGMENT_ID = re.compile(r"[A-Z][A-Z0-9]{2}")
_LINE = re.compile(r"([^\r\n]*)(\r\n|\r|\n|$)")
_TERMINATOR_NAMES = {"\r": "\\r", "\n": "\\n", "\r\n": "\\r\\n"}

# MSH-18 values (HL7 table 0211) mapped to Python codecs.
_CHARSETS = {
    "ASCII": "ascii",
    "8859/1": "iso-8859-1",
    "8859/2": "iso-8859-2",
    "8859/5": "iso-8859-5",
    "8859/6": "iso-8859-6",
    "8859/7": "iso-8859-7",
    "8859/8": "iso-8859-8",
    "8859/9": "iso-8859-9",
    "8859/15": "iso-8859-15",
    "UNICODE UTF-8": "utf-8",
    "UNICODE UTF-16": "utf-16",
    "UNICODE": "utf-8",
}


@dataclass(slots=True)
class ParseResult:
    """Everything read from one input (a file, a batch, an MLLP stream)."""

    messages: list[Message] = field(default_factory=list)
    envelope: list[Segment] = field(default_factory=list)  # FHS/BHS/BTS/FTS
    issues: list[ParseIssue] = field(default_factory=list)  # not tied to one message


class _Collector:
    def __init__(self, strict: bool):
        self.strict = strict
        self.issues: list[ParseIssue] = []

    def add(self, code, message, severity=Severity.WARNING, line=None, location=None):
        issue = ParseIssue(code, message, Severity(severity), line, location)
        if self.strict and issue.severity is Severity.ERROR:
            raise ParseError(issue)
        self.issues.append(issue)


# --- decoding and framing --------------------------------------------------


def _msh18(data: bytes) -> str | None:
    head = data.lstrip(b"\x0b\xef\xbb\xbf \t\r\n")
    if not head.startswith(b"MSH") or len(head) < 4:
        return None
    first = re.split(rb"[\r\n\x1c]", head, maxsplit=1)[0]
    parts = first.split(head[3:4])
    if len(parts) < 18:
        return None
    return parts[17].split(b"^")[0].decode("ascii", "replace").strip() or None


def decode(data: bytes) -> tuple[str, ParseIssue | None]:
    """Decode bytes, honouring MSH-18 when it names a known character set."""
    if data.startswith(codecs.BOM_UTF8):
        return data[3:].decode("utf-8", "replace"), None
    declared = _msh18(data)
    codec = _CHARSETS.get(declared.upper()) if declared else None
    if codec is None and declared:
        try:
            codec = codecs.lookup(declared).name
        except LookupError:
            codec = None
    if codec:
        text = data.decode(codec, "replace")
        if "�" in text:
            return text, ParseIssue(
                "decode", f"bytes not valid in MSH-18 charset {declared!r}; replaced"
            )
        return text, None
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return data.decode("latin-1"), ParseIssue(
            "decode", "not valid UTF-8 and MSH-18 names no known charset; decoded as Latin-1"
        )


def _strip_mllp(text: str, issues: _Collector) -> str:
    if "\x0b" not in text and "\x1c" not in text:
        return text
    if text.count("\x0b") != text.count("\x1c"):
        issues.add("mllp", "unbalanced MLLP framing (start/end block characters)")
    # A frame boundary is also a segment boundary.
    return text.replace("\x0b", "").replace("\x1c", "\r")


def _lines(text: str) -> list[tuple[int, str, str]]:
    """Split into (line_no, segment_text, terminator), dropping blank lines."""
    out = []
    for n, m in enumerate(_LINE.finditer(text), start=1):
        seg, term = m.group(1), m.group(2)
        if not seg and not term:
            break
        if seg.strip():
            out.append((n, seg, term))
    return out


# --- tokenizing ------------------------------------------------------------


def _split_field(raw: str, rep: str | None, comp: str, sub: str | None) -> Field:
    reps = raw.split(rep) if rep else [raw]
    if sub:
        return tuple(tuple(tuple(c.split(sub)) for c in r.split(comp)) for r in reps)
    return tuple(tuple((c,) for c in r.split(comp)) for r in reps)


def _parse_segment(line_no, line, enc, issues: _Collector) -> Segment:
    fs = enc.field
    seg_id = line[:3]
    if seg_id in HEADER_SEGMENTS and len(line) > 3 and line[3] == fs:
        end = line.find(fs, 4)
        msh2 = line[4:] if end == -1 else line[4:end]
        rest = [] if end == -1 else line[end + 1 :].split(fs)
        head: list[Field] = [(((fs,),),), (((msh2,),),)]
        start = 3
    else:
        seg_id, _, rest_str = line.partition(fs)
        rest = rest_str.split(fs) if _ else []
        head = []
        start = 1
        if not _SEGMENT_ID.fullmatch(seg_id):
            issues.add(
                "bad-segment-id", f"invalid segment ID {seg_id[:20]!r}", Severity.ERROR, line_no
            )

    rep, comp, sub, esc = enc.repetition, enc.component, enc.subcomponent, enc.escape
    fields = head
    for i, raw in enumerate(rest, start=start):
        fields.append(_split_field(raw, rep, comp, sub))
        if esc and esc in raw:
            for problem in escape_problems(raw, enc):
                issues.add("bad-escape", problem, Severity.WARNING, line_no, f"{seg_id}-{i}")
    return Segment(seg_id, tuple(fields))


def _build_message(lines, file_issues: _Collector, strict: bool) -> Message:
    issues = _Collector(strict)
    first_no, first, _ = lines[0]
    enc, _msh2, problems = read_header_encoding(first)
    for code, sev, msg in problems:
        issues.add(code, msg, sev, first_no, "MSH-2")

    terms = {t for _, _, t in lines if t}
    odd = sorted(_TERMINATOR_NAMES[t] for t in terms if t != "\r")
    if len(terms) > 1:
        issues.add(
            "mixed-terminators",
            "segments end with mixed terminators: "
            + ", ".join(sorted(_TERMINATOR_NAMES[t] for t in terms)),
            line=first_no,
        )
    elif odd:
        issues.add("terminator", f"segments end with {odd[0]} instead of \\r", line=first_no)

    segments = tuple(_parse_segment(n, line, enc, issues) for n, line, _ in lines)
    # File-level warnings (e.g. decoding) affect every message's content.
    return Message(segments, enc, tuple(file_issues.issues) + tuple(issues.issues))


def parse(data: str | bytes, *, strict: bool = False) -> ParseResult:
    """Parse any HL7 v2 input into messages (see module docstring)."""
    issues = _Collector(strict)
    if isinstance(data, bytes):
        text, problem = decode(data)
        if problem:
            issues.add(problem.code, problem.message, problem.severity)
    else:
        text = data.removeprefix("﻿")

    text = _strip_mllp(text, issues)
    lines = _lines(text)
    result = ParseResult()
    if not lines:
        issues.add("empty", "no segments found", Severity.ERROR)
        result.issues = issues.issues
        return result

    decode_issues = _Collector(strict)
    decode_issues.issues = [i for i in issues.issues if i.code == "decode"]

    current: list[tuple[int, str, str]] = []
    envelope_enc = DEFAULT_ENCODING
    batch_counts: list[int] = []  # messages per BHS..BTS batch
    file_messages = 0

    def flush():
        nonlocal file_messages
        if current:
            result.messages.append(_build_message(current, decode_issues, strict))
            file_messages += 1
            if batch_counts:
                batch_counts[-1] += 1
            current.clear()

    for line_no, line, term in lines:
        seg_id = line[:3]
        if seg_id == "MSH":
            flush()
            current.append((line_no, line, term))
        elif seg_id in ENVELOPE_SEGMENTS:
            flush()
            if seg_id in HEADER_SEGMENTS:
                envelope_enc, _, problems = read_header_encoding(line)
                for code, sev, msg in problems:
                    issues.add(code, msg, sev, line_no, f"{seg_id}-2")
            seg = _parse_segment(line_no, line, envelope_enc, issues)
            result.envelope.append(seg)
            if seg_id == "BHS":
                batch_counts.append(0)
            elif seg_id == "BTS":
                _check_count(
                    seg, "BTS-1", batch_counts.pop() if batch_counts else 0, issues, line_no
                )
        elif current:
            current.append((line_no, line, term))
        else:
            issues.add(
                "text-before-msh",
                f"segment {line[:20]!r} is outside any message (no MSH before it)",
                Severity.ERROR,
                line_no,
            )
    flush()

    if not result.messages:
        issues.add("no-msh", "no MSH segment found", Severity.ERROR)
    result.issues = issues.issues
    return result


def _check_count(seg: Segment, label: str, actual: int, issues: _Collector, line_no):
    """BTS-1 is the number of messages in the batch."""
    fld = seg.field(1)
    declared = fld[0][0][0].strip() if fld else ""
    if not declared:
        return
    if not declared.isdigit():
        issues.add("batch-count", f"{label} is not a number: {declared!r}", line=line_no)
    elif int(declared) != actual:
        issues.add(
            "batch-count",
            f"{label} says {declared} messages but the batch has {actual}",
            line=line_no,
            location=label,
        )


def parse_message(data: str | bytes, *, strict: bool = False) -> Message:
    """Parse input that should hold exactly one message.

    Raises :class:`ParseError` if no message can be read at all (in both
    modes). Extra messages are an error: strict mode raises, tolerant mode
    returns the first and records the issue on it.
    """
    result = parse(data, strict=strict)
    if not result.messages:
        raise ParseError(result.issues[-1])
    first = result.messages[0]
    extra = list(result.issues)
    if len(result.messages) > 1:
        issue = ParseIssue(
            "multiple-messages",
            f"expected one message, found {len(result.messages)}",
            Severity.ERROR,
        )
        if strict:
            raise ParseError(issue)
        extra.append(issue)
    if not extra:
        return first
    known = set(first.issues)
    merged = first.issues + tuple(i for i in extra if i not in known)
    return Message(first.segments, first.encoding, merged)


def parse_file(path: str | Path, *, strict: bool = False) -> ParseResult:
    """Parse a file of one or more messages (raw bytes; charset from MSH-18)."""
    return parse(Path(path).read_bytes(), strict=strict)
