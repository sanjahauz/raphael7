"""Structural signatures: shape counts, values do not."""

from pathlib import Path

from raphael7.parser import parse_message
from raphael7.scan.files import scan_files
from raphael7.scan.signature import Position, Sender, segment_order, signature

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def msg(*segments: str):
    return parse_message("\r".join(segments) + "\r")


MSH = "MSH|^~\\&|APP|FAC|||20261124||ADT^A01^ADT_A01|1|P|2.5"


def positions(sig, segment: str) -> list[str]:
    found = []
    for position in sig.populated:
        if position.segment == segment:
            found.append(str(position))
    return found


def test_values_do_not_change_the_signature():
    a = msg(MSH, "PID|1||111^^^HOSP^MR||COHEN^DANA")
    b = msg(MSH.replace("|1|P|", "|2|P|"), "PID|1||222^^^HOSP^MR||LEVI^NOA")
    assert signature(a) == signature(b)


def test_type_trigger_version_and_order():
    sig = signature(msg(MSH, "EVN|A01", "PID|1"))
    assert sig.sender == Sender("APP", "FAC")
    assert str(sig.sender) == "APP at FAC"
    assert sig.message_type == "ADT^A01"  # MSH-9.3 is not part of it
    assert sig.version == "2.5"
    assert sig.segments == ("MSH", "EVN", "PID")


def test_msh_fields_are_numbered_as_in_the_spec():
    sig = signature(msg(MSH))
    found = positions(sig, "MSH")
    assert found[:3] == ["MSH-1", "MSH-2", "MSH-3"]
    assert "MSH-9" in found
    assert "MSH-12" in found
    assert "MSH-5" not in found  # receiving application is empty


def test_a_run_of_one_segment_is_kept_once():
    few = msg(MSH, "OBR|1", "OBX|1", "OBX|2")
    many = msg(MSH, "OBR|1", "OBX|1", "OBX|2", "OBX|3", "OBX|4")
    assert segment_order(few) == ("MSH", "OBR", "OBX")
    assert signature(few) == signature(many)


def test_a_segment_that_comes_back_later_is_kept_each_time():
    two_orders = msg(MSH, "OBR|1", "OBX|1", "OBR|2", "OBX|1")
    assert segment_order(two_orders) == ("MSH", "OBR", "OBX", "OBR", "OBX")


def test_positions_are_merged_across_occurrences():
    sig = signature(msg(MSH, "OBX|1|NM|||||", "OBX|2|NM||||||N"))
    assert positions(sig, "OBX") == ["OBX-1", "OBX-2", "OBX-8"]


def test_positions_sort_by_number_not_text():
    sig = signature(msg(MSH, "PID|1|2" + "|" * 16 + "18"))
    assert positions(sig, "PID") == ["PID-1", "PID-2", "PID-18"]


def test_hl7_null_counts_as_populated():
    sig = signature(msg(MSH, 'PID|1||123||""'))
    assert Position("PID", 5) in sig.populated


def test_empty_components_are_not_populated():
    sig = signature(msg(MSH, "PID|1||123|^^~^"))
    assert Position("PID", 4) not in sig.populated


def test_vendor_b_version_drift_gives_two_signatures():
    """Vendor B says 2.3.1, but every 7th message says 2.5 (see samples/MANIFEST.md)."""
    versions = set()
    for scanned in scan_files(SAMPLES / "vendor-b"):
        for message in scanned.messages:
            versions.add(signature(message).version)
    assert versions == {"2.3.1", "2.5"}


def test_another_sender_is_another_signature():
    a = msg(MSH, "PID|1||111")
    b = msg(MSH.replace("|APP|FAC|", "|APP|FAC_NORTH|"), "PID|1||111")
    assert signature(a) != signature(b)
    assert str(signature(b).sender) == "APP at FAC_NORTH"
