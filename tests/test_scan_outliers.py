"""Odd ones out: every broken sample is flagged, normal messages are not."""

from pathlib import Path

from raphael7.scan.cluster import cluster_by_signature
from raphael7.scan.files import scan_files
from raphael7.scan.outliers import OutlierReport, find_outliers
from raphael7.scan.shapes import group_into_feeds

SAMPLES = Path(__file__).resolve().parent.parent / "samples"

MSH = "MSH|^~\\&|LAB|HOSP|||20261124||ORU^R01|{id}|P|{ver}\r"
OBR = "OBR|1|ORD1||CBC^CBC^L\r"
OBX_FULL = "OBX|1|NM|WBC||9.5|10*3/uL|4.5-11.0|N|||F\r"


def report_for(folder: Path) -> OutlierReport:
    grouping = cluster_by_signature(scan_files(folder))
    return find_outliers(grouping, group_into_feeds(grouping.clusters))


def reasons_by_place(report: OutlierReport) -> dict[str, list[str]]:
    found = {}
    for outlier in report.outliers:
        codes = []
        for reason in outlier.reasons:
            codes.append(reason.code)
        found[outlier.where] = codes
    return found


def write_messages(folder: Path, count: int, body: str, ver: str = "2.5", start: int = 1) -> None:
    for n in range(start, start + count):
        (folder / f"{n:03}.hl7").write_text(MSH.format(id=n, ver=ver) + body)


def test_a_clean_feed_has_no_outliers(tmp_path):
    write_messages(tmp_path, 5, OBR + OBX_FULL)
    report = report_for(tmp_path)
    assert report.outliers == []
    assert report.habits == []


def test_message_cut_short_is_missing_fields(tmp_path):
    write_messages(tmp_path, 5, OBR + OBX_FULL)
    (tmp_path / "cut.hl7").write_text(MSH.format(id=99, ver="2.5") + OBR + "OBX|1|NM|WBC\r")
    assert reasons_by_place(report_for(tmp_path)) == {"cut.hl7#1": ["missing-fields"]}


def test_one_missing_field_is_not_enough(tmp_path):
    """A normal result may leave OBX-8 empty where the others say N, H or L."""
    write_messages(tmp_path, 5, OBR + OBX_FULL)
    normal = OBX_FULL.replace("|N|", "||")
    (tmp_path / "normal.hl7").write_text(MSH.format(id=99, ver="2.5") + OBR + normal)
    assert report_for(tmp_path).outliers == []


def test_other_version_and_rare_segments(tmp_path):
    write_messages(tmp_path, 9, OBR + OBX_FULL, ver="2.3.1")
    write_messages(tmp_path, 1, OBR + OBX_FULL, ver="2.5", start=10)
    write_messages(tmp_path, 1, OBR + OBX_FULL + "ZXX|1\r", ver="2.3.1", start=11)
    found = reasons_by_place(report_for(tmp_path))
    assert found == {"010.hl7#1": ["other-version"], "011.hl7#1": ["rare-segments"]}


def test_an_issue_in_most_of_a_feed_is_a_habit(tmp_path):
    lf_body = (OBR + OBX_FULL).replace("\r", "\n")
    for n in range(1, 6):
        (tmp_path / f"{n}.hl7").write_text(
            (MSH.format(id=n, ver="2.5")).replace("\r", "\n") + lf_body
        )
    report = report_for(tmp_path)
    assert report.outliers == []
    habits = []
    for habit in report.habits:
        habits.append((habit.code, habit.count))
    assert habits == [("terminator", 5)]


def test_every_broken_sample_is_flagged():
    found = reasons_by_place(report_for(SAMPLES))
    flagged_files = set()
    for where in found:
        flagged_files.add(where.partition("#")[0])
    broken = set()
    for path in sorted((SAMPLES / "broken").iterdir()):
        broken.add(f"broken/{path.name}")
    assert broken <= flagged_files


def test_vendor_b_drift_is_flagged_and_nothing_else_from_vendors():
    """Vendor B says 2.5 in every 7th message; vendor A and C are clean."""
    flagged = []
    for where in reasons_by_place(report_for(SAMPLES)):
        if where.startswith("vendor-"):
            flagged.append(where)
    expected = []
    for n in range(7, 61, 7):
        matches = sorted((SAMPLES / "vendor-b").glob(f"{n:04}-*.hl7"))
        expected.append(f"vendor-b/{matches[0].name}#1")
    assert flagged == expected
