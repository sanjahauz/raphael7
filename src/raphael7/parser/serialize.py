"""Turn parsed messages back into HL7 v2 text."""

from raphael7.parser.encoding import HEADER_SEGMENTS, Encoding
from raphael7.parser.model import Message, Segment, join_field


def serialize_segment(seg: Segment, enc: Encoding) -> str:
    fs = enc.field
    if seg.id in HEADER_SEGMENTS and len(seg.fields) >= 2:
        # Field 1 is the separator itself; field 2 (encoding chars) is never split.
        msh2 = seg.fields[1][0][0][0]
        rest = "".join(fs + join_field(f, enc) for f in seg.fields[2:])
        return f"{seg.id}{fs}{msh2}{rest}"
    return seg.id + "".join(fs + join_field(f, enc) for f in seg.fields)


def serialize(msg: Message, terminator: str = "\r") -> str:
    """Serialize a message; every segment ends with ``terminator`` (``\\r`` per the spec)."""
    return "".join(serialize_segment(s, msg.encoding) + terminator for s in msg.segments)
