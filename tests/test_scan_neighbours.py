"""Near neighbours across senders, with the fields that differ."""

from pathlib import Path

from raphael7.scan.cluster import cluster_by_signature
from raphael7.scan.files import scan_files
from raphael7.scan.neighbours import nearest_neighbours
from raphael7.scan.shapes import group_into_feeds

SAMPLES = Path(__file__).resolve().parent.parent / "samples"

MSH = "MSH|^~\\&|{app}|HOSP|||20261124||{type}|{id}|P|2.5\r"


def neighbours_of(folder: Path):
    grouping = cluster_by_signature(scan_files(folder))
    return nearest_neighbours(group_into_feeds(grouping.clusters))


def names(positions) -> list[str]:
    found = []
    for position in positions:
        found.append(str(position))
    return found


def test_score_and_differences(tmp_path):
    (tmp_path / "a.hl7").write_text(MSH.format(app="A", type="ADT^A01", id=1) + "PID|1||1||X\r")
    (tmp_path / "b.hl7").write_text(MSH.format(app="B", type="ADT^A01", id=2) + "PID|1|9|1\r")
    neighbours = neighbours_of(tmp_path)
    assert len(neighbours) == 2
    a_to_b = neighbours[0]
    assert a_to_b.feed.sender.application == "A"
    assert names(a_to_b.only_here) == ["PID-5"]
    assert names(a_to_b.only_there) == ["PID-2"]
    # Positions, not values: MSH-3 is filled in both, so it is shared.
    # Shared: MSH-1 2 3 4 7 9 10 11 12 and PID-1 3 (11); either: 13.
    assert a_to_b.score == 11 / 13


def test_other_message_types_and_lone_feeds_have_no_neighbour(tmp_path):
    (tmp_path / "a.hl7").write_text(MSH.format(app="A", type="ADT^A01", id=1))
    (tmp_path / "b.hl7").write_text(MSH.format(app="B", type="ORU^R01", id=2))
    assert neighbours_of(tmp_path) == []


def test_samples_vendor_a_and_c_orders_are_close():
    for neighbour in neighbours_of(SAMPLES):
        if neighbour.feed.sender.application == "ADMITPRO" and (
            neighbour.feed.message_type == "ORM^O01"
        ):
            break
    assert neighbour.other.sender.application == "OLDHIS"
    assert neighbour.score > 0.9
    # Vendor C sends the charset (MSH-18) and the HMO in PV1-20.
    assert names(neighbour.only_there) == ["MSH-18", "PV1-20"]
