"""Feeds and shapes: senders never mixed, data-driven fields counted, not split."""

from pathlib import Path

from raphael7.scan.cluster import cluster_by_signature
from raphael7.scan.files import scan_files
from raphael7.scan.shapes import Feed, group_into_feeds

SAMPLES = Path(__file__).resolve().parent.parent / "samples"

MSH = "MSH|^~\\&|LAB|{fac}|||20261124||ORU^R01|{id}|P|{ver}\r"
OBR = "OBR|1|ORD1||CBC^CBC^L\r"


def feeds_of(folder: Path) -> list[Feed]:
    return group_into_feeds(cluster_by_signature(scan_files(folder)).clusters)


def write(folder: Path, name: str, text: str) -> None:
    (folder / name).write_text(text)


def test_abnormal_flag_is_one_shape_with_a_count(tmp_path):
    flagged = OBR + "OBX|1|NM|WBC||4.3|10*3/uL|4.5-11.0|L\r"
    normal = OBR + "OBX|1|NM|WBC||9.5|10*3/uL|4.5-11.0|\r"
    write(tmp_path, "1.hl7", MSH.format(fac="H", id=1, ver="2.5") + flagged)
    write(tmp_path, "2.hl7", MSH.format(fac="H", id=2, ver="2.5") + flagged)
    write(tmp_path, "3.hl7", MSH.format(fac="H", id=3, ver="2.5") + normal)

    feeds = feeds_of(tmp_path)
    assert len(feeds) == 1
    assert len(feeds[0].shapes) == 1
    shape = feeds[0].shapes[0]
    assert len(shape.clusters) == 2  # exact clusters are kept inside
    sometimes = []
    for usage in shape.sometimes_filled():
        sometimes.append(f"{usage.position} {usage.filled}/{usage.total}")
    assert sometimes == ["OBX-8 2/3"]


def test_senders_are_never_mixed(tmp_path):
    write(tmp_path, "1.hl7", MSH.format(fac="NORTH", id=1, ver="2.5") + OBR)
    write(tmp_path, "2.hl7", MSH.format(fac="SOUTH", id=2, ver="2.5") + OBR)
    feeds = feeds_of(tmp_path)
    facilities = []
    for feed in feeds:
        facilities.append(feed.sender.facility)
    assert facilities == ["NORTH", "SOUTH"]


def test_another_version_is_another_shape_of_the_same_feed(tmp_path):
    write(tmp_path, "1.hl7", MSH.format(fac="H", id=1, ver="2.3.1") + OBR)
    write(tmp_path, "2.hl7", MSH.format(fac="H", id=2, ver="2.3.1") + OBR)
    write(tmp_path, "3.hl7", MSH.format(fac="H", id=3, ver="2.5") + OBR)
    feeds = feeds_of(tmp_path)
    assert len(feeds) == 1
    assert feeds[0].versions() == ["2.3.1", "2.5"]
    counts = []
    for shape in feeds[0].shapes:
        counts.append((shape.version, shape.message_count))
    assert counts == [("2.3.1", 2), ("2.5", 1)]


def test_samples_vendor_b_results_cbc_and_bmp_are_two_shapes():
    for feed in feeds_of(SAMPLES):
        if feed.sender.application == "MEDIX" and feed.message_type == "ORU^R01":
            break
    shapes = []
    for shape in feed.shapes:
        shapes.append((shape.version, "NTE" in shape.segments, shape.message_count))
    assert shapes == [("2.3.1", False, 10), ("2.3.1", True, 8), ("2.5", True, 2)]
    assert feed.versions() == ["2.3.1", "2.5"]
