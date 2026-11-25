"""Z-segments per sender."""

from pathlib import Path

from raphael7.scan.cluster import cluster_by_signature
from raphael7.scan.files import scan_files
from raphael7.scan.shapes import group_into_feeds
from raphael7.scan.zsegments import z_segments

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def uses_of(folder: Path):
    grouping = cluster_by_signature(scan_files(folder))
    return z_segments(group_into_feeds(grouping.clusters))


def test_counts_messages_and_types(tmp_path):
    msh = "MSH|^~\\&|APP|HOSP|||20261124||{type}|{id}|P|2.5\r"
    (tmp_path / "1.hl7").write_text(msh.format(type="ADT^A01", id=1) + "ZPI|1\rZXX|1\r")
    (tmp_path / "2.hl7").write_text(msh.format(type="ADT^A08", id=2) + "ZPI|1\r")
    (tmp_path / "3.hl7").write_text(msh.format(type="ADT^A08", id=3) + "PID|1\r")
    found = []
    for use in uses_of(tmp_path):
        found.append((use.segment, use.messages, use.message_types))
    assert found == [("ZPI", 2, ("ADT^A01", "ADT^A08")), ("ZXX", 1, ("ADT^A01",))]


def test_samples_only_vendor_b_sends_zpi_in_adt():
    found = []
    for use in uses_of(SAMPLES):
        found.append((use.sender.application, use.segment, use.messages))
    # 12 A01 + 9 A08; vendor B's discharges (A03) carry no ZPI.
    assert found == [("MEDIX", "ZPI", 21)]
