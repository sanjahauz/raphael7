"""Turn parsed messages back into HL7 v2 text (the reverse of parsing)."""

from raphael7.parser.encoding import HEADER_SEGMENTS, Encoding
from raphael7.parser.model import Message, Segment, join_field


def serialize(msg: Message, terminator: str = "\r") -> str:
    """Write a message as text. Every segment ends with ``terminator`` (``\\r`` in the spec)."""
    return "".join(serialize_segment(seg, msg.encoding) + terminator for seg in msg.segments)


def serialize_segment(seg: Segment, enc: Encoding) -> str:
    """Write one segment: its ID, then each field preceded by the field separator.

    MSH (and FHS, BHS) is special. Field 1 *is* the field separator, so it is
    not written a second time, and field 2 (the encoding characters) is
    written as-is because it was never split.
    """
    if seg.id in HEADER_SEGMENTS and len(seg.fields) >= 2:
        encoding_chars = seg.fields[1][0][0][0]  # field 2 holds one unsplit value
        text = seg.id + enc.field + encoding_chars
        other_fields = seg.fields[2:]
    else:
        text = seg.id
        other_fields = seg.fields

    for fld in other_fields:
        text += enc.field + join_field(fld, enc)
    return text
