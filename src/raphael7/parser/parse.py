"""Turn HL7 v2 text into :class:`~raphael7.parser.model.Message` objects.

The input can be one message, several messages back to back, a batch file
(FHS/BHS ... BTS/FTS) or MLLP-framed data. :func:`parse` works in steps:

1. decode bytes to text (charset from MSH-18, else UTF-8, else Latin-1)
2. remove MLLP framing characters
3. split into lines (segments may end with \\r, \\n or \\r\\n)
4. group the lines into messages: each MSH starts a new one; batch
   envelope segments (FHS, BHS, BTS, FTS) are kept apart
5. for each message, read its delimiters from MSH, then split every
   segment into fields, repetitions, components and subcomponents

Two modes:

* **tolerant** (default): every problem is recorded as a ParseIssue and
  parsing carries on. This is what scanning a whole feed needs.
* **strict**: the first error-level issue raises ParseError. Warnings
  (\\n line endings, unknown escapes, ...) never raise.
"""

import codecs
import re
from dataclasses import dataclass, field
from pathlib import Path

from raphael7.parser.encoding import (
    DEFAULT_ENCODING,
    HEADER_SEGMENTS,
    Encoding,
    read_header_encoding,
)
from raphael7.parser.escape import escape_problems
from raphael7.parser.issues import IssueLog, ParseError, ParseIssue, Severity
from raphael7.parser.model import Field, Message, Segment, first_value

# Batch envelope: file header/trailer (FHS/FTS) and batch header/trailer (BHS/BTS).
ENVELOPE_SEGMENTS = frozenset({"FHS", "BHS", "BTS", "FTS"})

# MLLP wraps each message as <VT> message <FS><CR> when sent over TCP.
_MLLP_START = "\x0b"
_MLLP_END = "\x1c"

# Segment IDs are 3 characters: an uppercase letter, then letters or digits (Z01, PID).
_SEGMENT_ID = re.compile(r"[A-Z][A-Z0-9]{2}")

# MSH-18 values (HL7 table 0211) and the Python codec for each.
_CHARSETS = {
    "ASCII": "ascii",
    "8859/1": "iso-8859-1",
    "8859/2": "iso-8859-2",
    "8859/5": "iso-8859-5",
    "8859/6": "iso-8859-6",
    "8859/7": "iso-8859-7",
    "8859/8": "iso-8859-8",  # Hebrew
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


@dataclass(frozen=True, slots=True)
class DecodedText:
    """The result of :func:`decode`."""

    text: str
    warning: ParseIssue | None = None  # set when some characters may be wrong


@dataclass(frozen=True, slots=True)
class Line:
    """One segment line of the input."""

    number: int  # 1-based, counting blank lines too, so it matches an editor
    text: str
    terminator: str  # "\r", "\n", "\r\n", or "" for a last line without one


def parse(data: str | bytes, *, strict: bool = False) -> ParseResult:
    """Parse any HL7 v2 input into messages (see the module docstring for the steps)."""
    log = IssueLog(strict)

    if isinstance(data, bytes):
        decoded = decode(data)
        text = decoded.text
        if decoded.warning:
            log.add(decoded.warning)
    else:
        text = data.removeprefix("﻿")  # byte order mark

    text = _remove_mllp_framing(text, log)
    lines = _split_lines(text)
    if not lines:
        log.error("empty", "no segments found")
        return ParseResult(issues=log.issues)

    result = _group_into_messages(lines, log)
    if not result.messages:
        log.error("no-msh", "no MSH segment found")
    result.issues = log.issues
    return result


def parse_message(data: str | bytes, *, strict: bool = False) -> Message:
    """Parse input that should hold exactly one message.

    Raises ParseError if no message can be read at all (in both modes).
    More than one message is an error: strict mode raises, tolerant mode
    returns the first one with the issue recorded on it.
    """
    result = parse(data, strict=strict)
    if not result.messages:
        raise ParseError(result.issues[-1])

    first = result.messages[0]
    extra_issues = list(result.issues)
    if len(result.messages) > 1:
        issue = ParseIssue(
            "multiple-messages",
            f"expected one message, found {len(result.messages)}",
            Severity.ERROR,
        )
        if strict:
            raise ParseError(issue)
        extra_issues.append(issue)

    # Input-level issues belong to this message too (skip ones it already has).
    new_issues = [i for i in extra_issues if i not in first.issues]
    if not new_issues:
        return first
    return Message(first.segments, first.encoding, first.issues + tuple(new_issues))


def parse_file(path: str | Path, *, strict: bool = False) -> ParseResult:
    """Parse a file of one or more messages, read as bytes so MSH-18 can pick the charset."""
    return parse(Path(path).read_bytes(), strict=strict)


def decode(data: bytes) -> DecodedText:
    """Decode bytes to text, honouring the charset declared in MSH-18.

    Order: UTF-8 byte order mark, then the MSH-18 charset, then UTF-8, then
    Latin-1 (which accepts any bytes, so decoding never fails). Comes with a
    warning when some characters may be wrong.
    """
    if data.startswith(codecs.BOM_UTF8):
        return DecodedText(data[len(codecs.BOM_UTF8) :].decode("utf-8", "replace"))

    declared = _declared_charset(data)
    codec = _codec_for(declared) if declared else None
    if codec:
        text = data.decode(codec, "replace")
        if "�" in text:  # a byte the declared charset doesn't have
            warning = ParseIssue("decode", f"bytes not valid in MSH-18 charset {declared!r}")
            return DecodedText(text, warning)
        return DecodedText(text)

    try:
        return DecodedText(data.decode("utf-8"))
    except UnicodeDecodeError:
        warning = ParseIssue(
            "decode", "not valid UTF-8 and MSH-18 names no known charset; decoded as Latin-1"
        )
        return DecodedText(data.decode("latin-1"), warning)


def _declared_charset(data: bytes) -> str | None:
    """MSH-18 (character set) read straight from the bytes, before decoding.

    The delimiters are plain ASCII, so the MSH line can be split as bytes.
    """
    head = data.lstrip(b"\x0b\xef\xbb\xbf \t\r\n")
    if not head.startswith(b"MSH") or len(head) < 4:
        return None
    msh_line = re.split(rb"[\r\n\x1c]", head, maxsplit=1)[0]
    field_sep = head[3:4]
    parts = msh_line.split(field_sep)  # parts[0] is "MSH", parts[n - 1] is MSH-n
    if len(parts) < 18:
        return None
    msh18 = parts[17].split(b"^")[0]  # first component only
    return msh18.decode("ascii", "replace").strip() or None


def _codec_for(charset: str) -> str | None:
    """The Python codec for an MSH-18 value: HL7 names first, then Python's own."""
    codec = _CHARSETS.get(charset.upper())
    if codec:
        return codec
    try:
        return codecs.lookup(charset).name
    except LookupError:
        return None


def _remove_mllp_framing(text: str, log: IssueLog) -> str:
    """Remove MLLP start/end characters; each frame end also ends a segment."""
    if _MLLP_START not in text and _MLLP_END not in text:
        return text
    if text.count(_MLLP_START) != text.count(_MLLP_END):
        log.warning("mllp", "unbalanced MLLP framing (start/end block characters)")
    return text.replace(_MLLP_START, "").replace(_MLLP_END, "\r")


_LINE = re.compile(r"([^\r\n]*)(\r\n|\r|\n|$)")

# How terminators are written in issue messages.
_TERMINATOR_NAMES = {"\r": "\\r", "\n": "\\n", "\r\n": "\\r\\n"}


def _split_lines(text: str) -> list[Line]:
    """Split on \\r, \\n or \\r\\n, remembering each line's terminator. Blank lines are dropped."""
    lines = []
    for number, match in enumerate(_LINE.finditer(text), start=1):
        line_text, terminator = match.group(1), match.group(2)
        if line_text == "" and terminator == "":  # end of input
            break
        if line_text.strip():
            lines.append(Line(number, line_text, terminator))
    return lines


def _group_into_messages(lines: list[Line], log: IssueLog) -> ParseResult:
    """Cut the lines into messages: each MSH starts one, envelope segments end one."""
    grouper = _MessageGrouper(log)
    for line in lines:
        grouper.add(line)
    return grouper.finish()


class _MessageGrouper:
    """Collects lines into messages, one line at a time.

    A message runs from its MSH to the next MSH or batch envelope segment.
    Envelope segments (FHS, BHS, BTS, FTS) belong to no message and are kept
    apart. Lines before the first MSH are an error.
    """

    def __init__(self, log: IssueLog):
        self.log = log
        self.result = ParseResult()
        # A charset warning applies to every message's content, so each one gets a copy.
        self.decode_issues = [issue for issue in log.issues if issue.code == "decode"]
        self.message_lines: list[Line] = []  # lines of the message being collected
        self.envelope_encoding = DEFAULT_ENCODING  # from the latest FHS or BHS
        self.open_batches: list[int] = []  # message count per BHS whose BTS hasn't come yet

    def add(self, line: Line) -> None:
        seg_id = line.text[:3]
        if seg_id == "MSH":
            self._close_message()
            self.message_lines.append(line)
        elif seg_id in ENVELOPE_SEGMENTS:
            self._close_message()
            self._add_envelope_segment(line)
        elif self.message_lines:
            self.message_lines.append(line)
        else:
            self.log.error(
                "text-before-msh",
                f"segment {line.text[:20]!r} is outside any message (no MSH before it)",
                line=line.number,
            )

    def finish(self) -> ParseResult:
        self._close_message()
        return self.result

    def _close_message(self) -> None:
        if not self.message_lines:
            return
        message = _build_message(self.message_lines, self.decode_issues, self.log.strict)
        self.result.messages.append(message)
        if self.open_batches:
            self.open_batches[-1] += 1
        self.message_lines = []

    def _add_envelope_segment(self, line: Line) -> None:
        """FHS and BHS declare delimiters like MSH; BTS and FTS use the latest ones."""
        seg_id = line.text[:3]
        if seg_id in HEADER_SEGMENTS:
            header = read_header_encoding(line.text)
            self.envelope_encoding = header.encoding
            for issue in header.issues:
                self.log.add(_at_line(issue, line.number))

        segment = _parse_segment(line, self.envelope_encoding, self.log)
        self.result.envelope.append(segment)

        if seg_id == "BHS":
            self.open_batches.append(0)
        elif seg_id == "BTS":
            messages_in_batch = self.open_batches.pop() if self.open_batches else 0
            _check_batch_count(segment, messages_in_batch, line, self.log)


def _check_batch_count(bts: Segment, actual: int, line: Line, log: IssueLog) -> None:
    """BTS-1 (optional) is the number of messages in the batch: warn if it is wrong.

    A wrong count usually means messages were lost or added when the batch
    file was put together.
    """
    declared = first_value(bts.field(1)).strip()
    if declared == "":
        return
    if not declared.isdigit():
        log.warning("batch-count", f"BTS-1 is not a number: {declared!r}", line=line.number)
    elif int(declared) != actual:
        log.warning(
            "batch-count",
            f"BTS-1 says {declared} messages but the batch has {actual}",
            line=line.number,
            location="BTS-1",
        )


def _build_message(lines: list[Line], decode_issues: list[ParseIssue], strict: bool) -> Message:
    """Read the delimiters from the MSH line, then split every segment with them."""
    log = IssueLog(strict)
    msh = lines[0]

    header = read_header_encoding(msh.text)
    for issue in header.issues:
        log.add(_at_line(issue, msh.number))

    _check_terminators(lines, log)

    segments = tuple(_parse_segment(line, header.encoding, log) for line in lines)
    return Message(segments, header.encoding, tuple(decode_issues) + tuple(log.issues))


def _check_terminators(lines: list[Line], log: IssueLog) -> None:
    r"""The spec ends segments with \r; flag \n, \r\n, or a mix."""
    used = {line.terminator for line in lines if line.terminator}
    names = sorted(_TERMINATOR_NAMES[t] for t in used)
    first_line = lines[0].number
    if len(used) > 1:
        log.warning(
            "mixed-terminators",
            f"segments end with mixed terminators: {', '.join(names)}",
            line=first_line,
        )
    elif used and used != {"\r"}:
        log.warning("terminator", f"segments end with {names[0]} instead of \\r", line=first_line)


def _parse_segment(line: Line, enc: Encoding, log: IssueLog) -> Segment:
    """Split one segment line into its ID and fields."""
    text = line.text
    is_header = text[:3] in HEADER_SEGMENTS and len(text) > 3 and text[3] == enc.field

    if is_header:
        # MSH|^~\&|SENDER|... : field 1 is the separator itself and field 2
        # the encoding characters, which must not be split.
        seg_id = text[:3]
        end_of_msh2 = text.find(enc.field, 4)
        if end_of_msh2 == -1:
            encoding_chars = text[4:]
            field_texts = []
        else:
            encoding_chars = text[4:end_of_msh2]
            field_texts = text[end_of_msh2 + 1 :].split(enc.field)
        fields: list[Field] = [_single_value(enc.field), _single_value(encoding_chars)]
        first_field_number = 3
    else:
        # PID|1||123^^^HOSP : the ID, then fields 1, 2, 3 ...
        seg_id, has_fields, rest = text.partition(enc.field)
        field_texts = rest.split(enc.field) if has_fields else []
        fields = []
        first_field_number = 1
        if not _SEGMENT_ID.fullmatch(seg_id):
            log.error("bad-segment-id", f"invalid segment ID {seg_id[:20]!r}", line=line.number)

    for number, field_text in enumerate(field_texts, start=first_field_number):
        fields.append(_split_field(field_text, enc))
        for problem in escape_problems(field_text, enc):
            log.warning("bad-escape", problem, line=line.number, location=f"{seg_id}-{number}")

    return Segment(seg_id, tuple(fields))


def _split_field(text: str, enc: Encoding) -> Field:
    """Split one field into repetitions (~), then components (^), then subcomponents (&)."""
    repetitions = []
    for repetition_text in _split(text, enc.repetition):
        components = []
        for component_text in repetition_text.split(enc.component):
            subcomponents = tuple(_split(component_text, enc.subcomponent))
            components.append(subcomponents)
        repetitions.append(tuple(components))
    return tuple(repetitions)


def _split(text: str, separator: str | None) -> list[str]:
    """Split on a delimiter, or not at all when MSH-2 doesn't declare it."""
    if separator is None:
        return [text]
    return text.split(separator)


def _single_value(text: str) -> Field:
    """A field holding one unsplit value (used for MSH-1 and MSH-2)."""
    return (((text,),),)


def _at_line(issue: ParseIssue, line_number: int) -> ParseIssue:
    """The same issue, with the input line it was found on."""
    return ParseIssue(issue.code, issue.message, issue.severity, line_number, issue.location)
