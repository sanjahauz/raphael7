"""The structural signature of a message: its shape, without its values.

Two messages with the same signature were built the same way by the same
sender (MSH-3 application at MSH-4 facility): same MSH-9 type and trigger,
same MSH-12 version, same segments in the same order, and the same fields
filled in. Values are ignored, so two different
patients admitted by the same system share a signature.

The signature is small and built from one message at a time, so a large
feed can be scanned in a stream (or in several processes) without keeping
the messages themselves.
"""

from dataclasses import dataclass

from raphael7.parser import Field, Message


@dataclass(frozen=True, slots=True)
class Position:
    """A field position such as PID-3: segment ID and field number (1-based)."""

    segment: str
    field: int

    def __str__(self) -> str:
        return f"{self.segment}-{self.field}"


@dataclass(frozen=True, slots=True)
class Sender:
    """The sending system: MSH-3 application at MSH-4 facility, raw values.

    One sending system is one application at one facility, so a hospital
    group with three sites on the same EHR shows up as three senders.
    Decided 25 Nov, see docs/ROADMAP.md.
    """

    application: str  # MSH-3, "" when empty
    facility: str  # MSH-4, "" when empty

    def __str__(self) -> str:
        return f"{self.application or '?'} at {self.facility or '?'}"


@dataclass(frozen=True, slots=True)
class Signature:
    sender: Sender
    message_type: str | None  # MSH-9 type^trigger, e.g. ADT^A01 (MSH-9.3 left out)
    version: str | None  # MSH-12, e.g. 2.5
    segments: tuple[str, ...]  # segment IDs in order, a run of the same ID kept once
    populated: tuple[Position, ...]  # sorted by segment ID, then field number


def signature(msg: Message) -> Signature:
    """Build the signature of one message."""
    return Signature(
        sender=sender_of(msg),
        message_type=msg.message_type,
        version=msg.version,
        segments=segment_order(msg),
        populated=populated_positions(msg),
    )


def sender_of(msg: Message) -> Sender:
    """MSH-3 and MSH-4 as sent (first repetition, components kept)."""
    return Sender(application=msg.get("MSH-3") or "", facility=msg.get("MSH-4") or "")


def segment_order(msg: Message) -> tuple[str, ...]:
    """Segment IDs in order, with a run of the same ID collapsed to one.

    An ORU with 8 OBX results and one with 12 have the same shape
    (OBR OBX), so the count of a repeating segment is not part of it.
    A segment that comes back later (OBR OBX OBR OBX, two orders in one
    message) is kept each time, since that is a different shape.
    """
    order = []
    for seg in msg.segments:
        if not order or order[-1] != seg.id:
            order.append(seg.id)
    return tuple(order)


def populated_positions(msg: Message) -> tuple[Position, ...]:
    """Every SEG-n position that holds a value in at least one occurrence of SEG.

    Occurrences are merged: if OBX-8 is filled in one OBX out of ten, OBX-8
    is populated. A field holding only "" (the HL7 null, "delete the
    stored value") counts as populated: the sender chose to put it there.
    Decided 24 Nov, see docs/ROADMAP.md.
    """
    found = set()
    for seg in msg.segments:
        for number, fld in enumerate(seg.fields, start=1):
            if _is_populated(fld):
                found.add(Position(seg.id, number))
    return tuple(sorted(found, key=_position_key))


def _is_populated(fld: Field) -> bool:
    """True if any repetition, component or subcomponent is not empty."""
    for repetition in fld:
        for component in repetition:
            for subcomponent in component:
                if subcomponent:
                    return True
    return False


def _position_key(position: Position) -> tuple[str, int]:
    # Sort PID-2 before PID-10, which a plain string sort would not.
    return (position.segment, position.field)
